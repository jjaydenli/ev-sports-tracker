"""Load master boards, normalize per platform, and merge into a unified board."""

import json
import os
from pathlib import Path

from loguru import logger

from parsers.betr_parser import parse_betr_props
from parsers.dk_parser import parse_dk_props
from parsers.fd_parser import parse_fd_props

# Active platforms included in normalize_all(). Dabble is archived under archive/dabble/.
PLATFORM_CONFIG = {
    "betr": ("betr_master_board.json", "betr_normalized.json", parse_betr_props),
    "draftkings": ("dk_master_board.json", "dk_normalized.json", parse_dk_props),
    "fanduel": ("fd_master_board.json", "fd_normalized.json", parse_fd_props),
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
    """Load a master board JSON file."""
    path = Path(input_path)
    if not path.exists():
        return []

    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        logger.warning(f"expected list in {path}, got {type(data).__name__}")
        return []

    return data


def save_props(props: list[dict], output_path: str | Path) -> None:
    """Persist normalized props to disk."""
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


def normalize_all(output_dir: str | Path = "data/processed") -> list[dict]:
    """Normalize all available master boards and write per-platform + unified files."""
    output_path = Path(output_dir)
    platform_results: list[list[dict]] = []

    for platform, (input_filename, output_filename, _) in PLATFORM_CONFIG.items():
        input_path = output_path / input_filename
        if not input_path.exists():
            logger.warning(f"skipping {platform}: master board not found at {input_path}")
            continue

        props = load_master_board(input_path)
        if not props:
            logger.warning(f"skipping {platform}: empty master board at {input_path}")
            continue

        normalized = normalize_platform(platform, props)
        save_props(normalized, output_path / output_filename)
        logger.success(
            f"{platform}: normalized {len(normalized)} props -> {output_path / output_filename}"
        )
        platform_results.append(normalized)

    unified = merge_normalized(platform_results)
    unified_path = output_path / UNIFIED_OUTPUT_FILENAME
    save_props(unified, unified_path)
    logger.success(f"unified board: {len(unified)} props -> {unified_path}")
    return unified


def main() -> None:
    """CLI entrypoint for post-scrape normalization."""
    backend_root = Path(__file__).resolve().parent.parent
    os.chdir(backend_root)
    normalize_all()


if __name__ == "__main__":
    main()
