"""Load normalized boards, run EV comparison, and persist opportunities."""

from __future__ import annotations

import json
import os
from pathlib import Path

from loguru import logger

from core.engine import compare_betr_vs_draftkings
from parsers.normalize import normalize_all, save_props

EV_OUTPUT_FILENAME = "ev_opportunities.json"
BETR_NORMALIZED = "betr_normalized.json"
DK_NORMALIZED = "dk_normalized.json"


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


def split_normalized_by_sportsbook(unified_props: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a unified board into Betr and DraftKings lists."""
    betr_props = [
        prop for prop in unified_props if prop.get("sportsbook") == "Betr"
    ]
    dk_props = [
        prop for prop in unified_props if prop.get("sportsbook") == "DraftKings"
    ]
    return betr_props, dk_props


def load_comparison_inputs(data_dir: Path) -> tuple[list[dict], list[dict]]:
    """Load normalized Betr and DraftKings props from disk."""
    betr_path = data_dir / BETR_NORMALIZED
    dk_path = data_dir / DK_NORMALIZED

    betr_props = load_json_list(betr_path)
    dk_props = load_json_list(dk_path)

    if betr_props and dk_props:
        return betr_props, dk_props

    unified_path = data_dir / "unified_master_board.json"
    if unified_path.exists():
        unified = load_json_list(unified_path)
        betr_from_unified, dk_from_unified = split_normalized_by_sportsbook(unified)
        betr_props = betr_props or betr_from_unified
        dk_props = dk_props or dk_from_unified

    return betr_props, dk_props


def run_ev_scan(
    data_dir: str | Path = "data/processed",
    *,
    min_ev: float = 0.0,
    normalize_first: bool = True,
) -> list[dict]:
    """Run the Betr vs DraftKings EV scan and optionally persist results."""
    data_path = Path(data_dir)

    if normalize_first:
        normalize_all(data_path)

    betr_props, dk_props = load_comparison_inputs(data_path)
    if not betr_props:
        logger.error(f"no betr props found in {data_path}")
        return []
    if not dk_props:
        logger.error(f"no draftkings props found in {data_path}")
        return []

    logger.info(
        f"comparing {len(betr_props)} betr props against {len(dk_props)} draftkings props"
    )
    opportunities = compare_betr_vs_draftkings(
        betr_props, dk_props, min_ev=min_ev
    )

    output_path = data_path / EV_OUTPUT_FILENAME
    save_props(opportunities, output_path)
    logger.success(
        f"found {len(opportunities)} +EV opportunities (min_ev={min_ev}) -> {output_path}"
    )

    for row in opportunities[:5]:
        logger.info(
            f"  {row['player']} {row['market']} {row['line']} {row['side'].upper()} "
            f"EV={row['ev_pct']:+.2f}% "
            f"no-vig={row['no_vig_implied_pct']:.2f}% ({row['no_vig_favored_side']}) "
            f"betr={row['betr_implied_pct']:.2f}% "
            f"DK O{row['dk_over_odds']:+d} U{row['dk_under_odds']:+d}"
        )

    return opportunities


def main() -> None:
    """CLI entrypoint for EV comparison."""
    backend_root = Path(__file__).resolve().parent.parent
    os.chdir(backend_root)
    run_ev_scan()


if __name__ == "__main__":
    main()
