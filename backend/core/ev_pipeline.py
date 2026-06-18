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
from core.pipeline_artifacts import (
    BETR_NORMALIZED,
    DK_NORMALIZED,
    EV_OUTPUT_FILENAME,
    FD_NORMALIZED,
    MATCH_REPORT_FILENAME,
    UNMATCHED_BETR_FILENAME,
    UNMATCHED_DK_FILENAME,
    load_wrapped_board,
    save_wrapped_board,
)
from parsers.normalize import UNIFIED_OUTPUT_FILENAME, normalize_all


def load_json_list(path: Path) -> list[dict]:
    """Load a JSON file containing props (wrapped board or legacy list)."""
    _, props = load_wrapped_board(path)
    return props


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


_NORMALIZED_BY_SOURCE: dict[str, str] = {
    "betr": BETR_NORMALIZED,
    "dk": DK_NORMALIZED,
    "fd": FD_NORMALIZED,
}


def load_comparison_inputs(
    data_dir: Path,
    *,
    expected_run_id: str | None = None,
    active_sources: tuple[str, ...] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Load normalized Betr, DraftKings, and FanDuel props from disk.

    When ``active_sources`` is set (partial scrape runs), only those sources are
    loaded and run_id-checked; inactive sources return empty lists so stale
    on-disk boards from a prior run are not mixed in.
    """
    data_dir = Path(data_dir)

    def _source_active(source: str) -> bool:
        return active_sources is None or source in active_sources

    def _load_source(source: str) -> list[dict]:
        if not _source_active(source):
            return []
        path = data_dir / _NORMALIZED_BY_SOURCE[source]
        if expected_run_id:
            run_id, props = load_wrapped_board(path)
            if run_id != expected_run_id:
                raise ValueError(
                    f"{source} normalized run_id mismatch: "
                    f"{run_id!r} != {expected_run_id!r}"
                )
            return props
        return load_json_list(path)

    betr_props = _load_source("betr")
    dk_props = _load_source("dk")
    fd_props = _load_source("fd")

    unified_path = data_dir / UNIFIED_OUTPUT_FILENAME
    need_betr = not betr_props and _source_active("betr")
    need_dk = not dk_props and _source_active("dk")
    need_fd = not fd_props and _source_active("fd")
    if unified_path.exists() and (need_betr or need_dk or need_fd):
        unified = load_json_list(unified_path)
        betr_from_unified, dk_from_unified, fd_from_unified = (
            split_normalized_by_sportsbook(unified)
        )
        betr_props = betr_props or betr_from_unified
        dk_props = dk_props or dk_from_unified
        fd_props = fd_props or fd_from_unified

    return betr_props, dk_props, fd_props


def _league_key(prop: dict) -> str:
    league = prop.get("league")
    if league:
        return str(league).upper()
    return "UNKNOWN"


def compute_by_league_match_stats(
    betr_props: list[dict],
    dk_props: list[dict],
    *,
    fd_props: list[dict] | None = None,
    include_flat_lines: bool = False,
) -> dict[str, dict]:
    """Per-league match diagnostics derived from normalized props."""
    leagues = sorted(
        {
            _league_key(prop)
            for prop in betr_props + dk_props + (fd_props or [])
        }
    )
    by_league: dict[str, dict] = {}
    for league in leagues:
        betr_subset = [p for p in betr_props if _league_key(p) == league]
        dk_subset = [p for p in dk_props if _league_key(p) == league]
        fd_subset = (
            [p for p in (fd_props or []) if _league_key(p) == league]
            if fd_props
            else None
        )
        if not betr_subset and not dk_subset and not fd_subset:
            continue
        if not betr_subset and not dk_subset:
            by_league[league] = {
                "status": "books_only",
                "fd_props": len(fd_subset or []),
            }
            continue
        stats = compute_match_stats(
            betr_subset,
            dk_subset,
            fanduel_props=fd_subset,
            include_flat_lines=include_flat_lines,
        )
        by_league[league] = dict(stats)
        if not betr_subset and not dk_subset:
            by_league[league]["status"] = "no_events"
    return by_league


def persist_match_diagnostics(
    data_dir: str | Path,
    betr_props: list[dict],
    dk_props: list[dict],
    *,
    fd_props: list[dict] | None = None,
    include_flat_lines: bool = False,
) -> dict[str, int | float | dict]:
    """Write match stats and unmatched prop lists for scrape/match efficacy checks."""
    data_path = Path(data_dir)
    stats = compute_match_stats(
        betr_props,
        dk_props,
        fanduel_props=fd_props,
        include_flat_lines=include_flat_lines,
    )
    by_league = compute_by_league_match_stats(
        betr_props,
        dk_props,
        fd_props=fd_props,
        include_flat_lines=include_flat_lines,
    )
    report: dict[str, int | float | dict | str] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **stats,
        "by_league": by_league,
    }

    report_path = data_path / MATCH_REPORT_FILENAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=4)

    from parsers.normalize import save_props

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
    expected_run_id: str | None = None,
    active_sources: tuple[str, ...] | None = None,
    previous_run_id: str | None = None,
) -> list[dict]:
    """Run the Betr vs sharp-book EV scan and optionally persist results."""
    data_path = Path(data_dir)

    if normalize_first:
        normalize_all(data_path)

    betr_props, dk_props, fd_props = load_comparison_inputs(
        data_path,
        expected_run_id=expected_run_id,
        active_sources=active_sources,
    )
    if not betr_props:
        logger.error(f"no betr props found in {data_path}")
        return []
    if not dk_props and not fd_props:
        logger.error(
            f"no sharp book props found in {data_path} (need draftkings and/or fanduel)"
        )
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

    previous_rows, prior_run_id = rotate_ev_opportunities_file(data_path)
    output_path = data_path / EV_OUTPUT_FILENAME
    effective_previous_run_id = previous_run_id or prior_run_id
    save_wrapped_board(
        output_path,
        run_id=expected_run_id or "unknown",
        props=opportunities,
    )
    if effective_previous_run_id and expected_run_id:
        with output_path.open(encoding="utf-8") as file:
            payload = json.load(file)
        payload["previous_run_id"] = effective_previous_run_id
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4)

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
