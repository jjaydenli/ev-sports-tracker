"""Load normalized boards, run EV comparison, and persist opportunities."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from core.engine import (
    compare_betr_vs_draftkings,
    compute_match_stats,
    list_unmatched_betr_props,
    list_unmatched_dk_props,
)
from core.ev_display import format_ev_opportunities_table
from core.ev_run_diff import (
    EV_DIFF_FILENAME,
    compute_run_diff,
    format_run_diff_summary,
    rotate_ev_opportunities_file,
    write_run_diff_json,
)
from parsers.normalize import normalize_all, save_props

EV_OUTPUT_FILENAME = "ev_opportunities.json"
MATCH_REPORT_FILENAME = "match_report.json"
UNMATCHED_BETR_FILENAME = "unmatched_betr.json"
UNMATCHED_DK_FILENAME = "unmatched_dk.json"
BETR_NORMALIZED = "betr_normalized.json"
DK_NORMALIZED = "dk_normalized.json"
FD_NORMALIZED = "fd_normalized.json"


def load_json_list(path: Path) -> list[dict]:
    """Load a JSON file containing a list of prop dicts."""
    if not path.exists():
        return []

    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        logger.warning(f"expected list in {path}, got {type(data).__name__}")
        return []

    return data


def split_normalized_by_sportsbook(
    unified_props: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split a unified board into Betr, DraftKings, and FanDuel lists."""
    betr_props = [
        prop for prop in unified_props if prop.get("sportsbook") == "Betr"
    ]
    dk_props = [
        prop for prop in unified_props if prop.get("sportsbook") == "DraftKings"
    ]
    fd_props = [
        prop for prop in unified_props if prop.get("sportsbook") == "FanDuel"
    ]
    return betr_props, dk_props, fd_props


def load_comparison_inputs(data_dir: Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Load normalized Betr, DraftKings, and FanDuel props from disk."""
    betr_props = load_json_list(data_dir / BETR_NORMALIZED)
    dk_props = load_json_list(data_dir / DK_NORMALIZED)
    fd_props = load_json_list(data_dir / FD_NORMALIZED)

    unified_path = data_dir / "unified_master_board.json"
    if unified_path.exists() and (not betr_props or not dk_props):
        unified = load_json_list(unified_path)
        betr_from_unified, dk_from_unified, fd_from_unified = (
            split_normalized_by_sportsbook(unified)
        )
        betr_props = betr_props or betr_from_unified
        dk_props = dk_props or dk_from_unified
        fd_props = fd_props or fd_from_unified

    return betr_props, dk_props, fd_props


def persist_match_diagnostics(
    data_dir: str | Path,
    betr_props: list[dict],
    dk_props: list[dict],
    *,
    fd_props: list[dict] | None = None,
    include_flat_lines: bool = False,
) -> dict[str, int | float]:
    """Write match stats and unmatched prop lists for scrape/match efficacy checks."""
    data_path = Path(data_dir)
    stats = compute_match_stats(
        betr_props,
        dk_props,
        fanduel_props=fd_props,
        include_flat_lines=include_flat_lines,
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **stats,
    }

    report_path = data_path / MATCH_REPORT_FILENAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)
    save_props(
        list_unmatched_betr_props(
            betr_props,
            dk_props,
            fanduel_props=fd_props,
            include_flat_lines=include_flat_lines,
        ),
        data_path / UNMATCHED_BETR_FILENAME,
    )
    save_props(
        list_unmatched_dk_props(betr_props, dk_props),
        data_path / UNMATCHED_DK_FILENAME,
    )

    logger.info(
        "match diagnostics: "
        f"betr={stats['betr_props']} dk={stats['dk_props']} fd={stats.get('fd_props', 0)} "
        f"matched={stats['matched_keys']} "
        f"({stats['betr_match_rate_pct']}%) "
        f"unmatched_betr={stats['unmatched_betr']} "
        f"(no_dk_market={stats['unmatched_betr_no_dk_market']} "
        f"no_exact_sharp={stats['unmatched_betr_no_exact_sharp_line']} "
        f"line_mismatch={stats['unmatched_betr_line_mismatch']} "
        f"flat_skipped={stats['unmatched_betr_flat_line_skipped']}) "
        f"unmatched_dk={stats['unmatched_dk']}"
    )
    return stats


def run_ev_scan(
    data_dir: str | Path = "data/processed",
    *,
    min_ev: float = 0.0,
    top_n: int = 15,
    normalize_first: bool = True,
    include_flat_lines: bool = False,
    filter_min_ev: bool = False,
) -> list[dict]:
    """Run the Betr vs DraftKings EV scan and optionally persist results."""
    data_path = Path(data_dir)

    if normalize_first:
        normalize_all(data_path)

    betr_props, dk_props, fd_props = load_comparison_inputs(data_path)
    if not betr_props:
        logger.error(f"no betr props found in {data_path}")
        return []
    if not dk_props:
        logger.error(f"no draftkings props found in {data_path}")
        return []

    logger.info(
        f"comparing {len(betr_props)} betr props against "
        f"{len(dk_props)} draftkings + {len(fd_props)} fanduel props"
    )
    opportunities = compare_betr_vs_draftkings(
        betr_props,
        dk_props,
        fanduel_props=fd_props or None,
        min_ev=min_ev,
        top_n=top_n,
        include_flat_lines=include_flat_lines,
        filter_min_ev=filter_min_ev,
    )
    plus_ev_count = sum(1 for row in opportunities if row.get("plus_ev"))

    previous_rows = rotate_ev_opportunities_file(data_path)
    output_path = data_path / EV_OUTPUT_FILENAME
    save_props(opportunities, output_path)

    diff = None
    if previous_rows:
        diff = compute_run_diff(previous_rows, opportunities)
        write_run_diff_json(diff, data_path / EV_DIFF_FILENAME)

    logger.success(
        f"top={len(opportunities)} plus_ev={plus_ev_count} "
        f"(min_ev={min_ev}, top_n={top_n}) -> {output_path}"
    )

    if opportunities:
        logger.info("ranked plays:\n" + format_ev_opportunities_table(opportunities))
    if diff is not None:
        summary = format_run_diff_summary(diff)
        if summary:
            logger.info(summary)

    return opportunities


def main() -> None:
    """CLI entrypoint for EV comparison."""
    backend_root = Path(__file__).resolve().parent.parent
    os.chdir(backend_root)
    run_ev_scan()


if __name__ == "__main__":
    main()
