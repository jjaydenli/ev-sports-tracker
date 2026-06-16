"""Load master boards, normalize per platform, and merge into a unified board."""

from __future__ import annotations

import json
import os
from pathlib import Path

from loguru import logger

from config.pipeline_sources import SOURCE_TO_PLATFORM
from core.pipeline_artifacts import load_wrapped_board, save_wrapped_board
from parsers.betr_parser import parse_betr_props
from parsers.dk_parser import parse_dk_props
from parsers.fd_parser import parse_fd_props

# Active platforms included in normalize_all(). Dabble is archived under archive/dabble/.
PLATFORM_CONFIG = {
    "betr": ("betr_master_board.json", "betr_normalized.json", parse_betr_props),
    "draftkings": ("dk_master_board.json", "dk_normalized.json", parse_dk_props),
    "fanduel": ("fd_master_board.json", "fd_normalized.json", parse_fd_props),
}

SOURCE_TO_NORMALIZED: dict[str, str] = {
    "betr": "betr_normalized.json",
    "dk": "dk_normalized.json",
    "fd": "fd_normalized.json",
}

SOURCE_TO_MASTER: dict[str, str] = {
    "betr": "betr_master_board.json",
    "dk": "dk_master_board.json",
    "fd": "fd_master_board.json",
}

UNIFIED_OUTPUT_FILENAME = "unified_master_board.json"

PARSER_BY_PLATFORM = {
    platform: config[2] for platform, config in PLATFORM_CONFIG.items()
}


def normalize_platform(platform: str, props: list[dict]) -> list[dict]:
    """Dispatch raw props to the platform-specific normalizer."""
    parser = PARSER_BY_PLATFORM.get(platform)
    if not parser:
        raise ValueError(f"Unknown platform: {platform}")
    return parser(props)


def load_master_board(input_path: str | Path) -> list[dict]:
    """Load a master board JSON file (wrapped or legacy list)."""
    _, props = load_wrapped_board(Path(input_path))
    return props


def load_normalized_board(input_path: str | Path) -> tuple[str | None, list[dict]]:
    """Load normalized board with optional run_id."""
    return load_wrapped_board(Path(input_path))


def save_props(props: list[dict], output_path: str | Path) -> None:
    """Persist a bare list of props (legacy / unmatched exports)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(props, file, indent=4)


def load_and_normalize(
    platform: str,
    input_path: str | Path,
    output_dir: str | Path | None = None,
) -> list[dict]:
    """Load a master board and return normalized props."""
    props = load_master_board(input_path)
    if not props:
        logger.warning(f"skipping {platform}: empty or missing input at {input_path}")
        return []

    normalized = normalize_platform(platform, props)
    logger.info(f"normalized {len(normalized)} props for {platform}")

    if output_dir is not None:
        _, output_filename, _ = PLATFORM_CONFIG[platform]
        output_path = Path(output_dir) / output_filename
        save_props(normalized, output_path)
        logger.success(f"saved {len(normalized)} props to {output_path}")

    return normalized


def merge_normalized(all_props: list[list[dict]]) -> list[dict]:
    """Concatenate normalized prop lists from multiple platforms."""
    merged: list[dict] = []
    for props in all_props:
        merged.extend(props)
    return merged


def persist_source_boards(
    output_dir: Path,
    *,
    run_id: str,
    source: str,
    raw_props: list[dict],
) -> list[dict]:
    """Normalize in memory and write master + normalized wrapped boards."""
    platform = SOURCE_TO_PLATFORM[source]
    master_name = SOURCE_TO_MASTER[source]
    normalized_name = SOURCE_TO_NORMALIZED[source]

    save_wrapped_board(output_dir / master_name, run_id=run_id, props=raw_props)
    normalized = normalize_platform(platform, raw_props)
    save_wrapped_board(output_dir / normalized_name, run_id=run_id, props=normalized)
    logger.success(
        f"{source}: {len(raw_props)} raw -> {len(normalized)} normalized "
        f"({normalized_name})"
    )
    return normalized


def persist_unified_board(
    output_dir: Path,
    *,
    run_id: str,
    normalized_chunks: list[list[dict]],
) -> list[dict]:
    """Write unified normalized board from per-source chunks."""
    unified = merge_normalized(normalized_chunks)
    save_wrapped_board(
        output_dir / UNIFIED_OUTPUT_FILENAME,
        run_id=run_id,
        props=unified,
    )
    logger.success(f"unified board: {len(unified)} props -> {UNIFIED_OUTPUT_FILENAME}")
    return unified


def normalize_all(
    output_dir: str | Path = "data/processed",
    *,
    required_sources: tuple[str, ...] | None = None,
    run_id: str | None = None,
) -> list[dict]:
    """
    Normalize master boards from disk (``--skip-scrape`` path).

    When ``required_sources`` is set, missing or empty masters raise ValueError.
    """
    output_path = Path(output_dir)
    platform_results: list[list[dict]] = []
    effective_run_id = run_id or "skip-scrape"

    for platform, (input_filename, output_filename, _) in PLATFORM_CONFIG.items():
        input_path = output_path / input_filename
        source_keys = [
            key for key, mapped in SOURCE_TO_PLATFORM.items() if mapped == platform
        ]
        is_required = required_sources is not None and any(
            key in required_sources for key in source_keys
        )

        if not input_path.exists():
            if is_required:
                raise ValueError(f"required master board missing: {input_path}")
            logger.warning(f"skipping {platform}: master board not found at {input_path}")
            continue

        props = load_master_board(input_path)
        if not props:
            if is_required:
                raise ValueError(f"required master board empty: {input_path}")
            logger.warning(f"skipping {platform}: empty master board at {input_path}")
            continue

        normalized = normalize_platform(platform, props)
        save_wrapped_board(
            output_path / output_filename,
            run_id=effective_run_id,
            props=normalized,
        )
        logger.success(
            f"{platform}: normalized {len(normalized)} props -> {output_path / output_filename}"
        )
        platform_results.append(normalized)

    return persist_unified_board(
        output_path,
        run_id=effective_run_id,
        normalized_chunks=platform_results,
    )


def main() -> None:
    """CLI entrypoint for post-scrape normalization."""
    backend_root = Path(__file__).resolve().parent.parent
    os.chdir(backend_root)
    normalize_all()


if __name__ == "__main__":
    main()
