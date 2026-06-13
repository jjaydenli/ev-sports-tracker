"""End-to-end refresh: Betr + DraftKings scrape → normalize → EV scan."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

from loguru import logger

from core.ev_pipeline import (
    BETR_NORMALIZED,
    DK_NORMALIZED,
    load_comparison_inputs,
    persist_match_diagnostics,
    run_ev_scan,
)
from core.pipeline_timing import PipelineTimer
from parsers.normalize import normalize_all
from scrapers.dfs.betr.betr_auth import BetrAuthError, ensure_betr_token, validate_betr_token_or_raise
from scrapers.dfs.betr.betr_engine import run_betr_scrape
from scrapers.sportsbooks.dk_engine import run_dk_scrape
from scrapers.sportsbooks.fd_engine import run_fd_scrape

DEFAULT_DATA_DIR = "data/processed"
DEFAULT_LEAGUE = "NBA"

# Betr GraphQL League enum → DraftKings slate key in dk_subcategories.DK_LEAGUE_SLATES
_BETR_TO_DK_LEAGUE = {
    "NBA": "nba",
    "MLB": "mlb",
}


def _normalize_betr_league(league: str) -> str:
    """Betr GraphQL League enum is uppercase (MLB, NBA); DK slate keys stay lowercase."""
    return league.upper()


def _dk_league_key(league: str) -> str:
    """Map pipeline --league (Betr enum) to DraftKings slate key."""
    return _BETR_TO_DK_LEAGUE.get(league.upper(), league.lower())


def _is_mlb_league(league: str) -> bool:
    return league.upper() == "MLB"


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _preflight_betr_auth(*, skip_expiry_check: bool) -> None:
    """Validate or obtain a Betr token before scraping."""
    if skip_expiry_check:
        return

    try:
        token = asyncio.run(ensure_betr_token())
    except BetrAuthError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc

    validate_betr_token_or_raise(token)


async def _scrape_betr(league: str) -> int:
    return await run_betr_scrape(league=league)


async def _scrape_dk(league: str) -> int:
    return await run_dk_scrape(league=_dk_league_key(league))


async def _scrape_fd() -> int:
    return await run_fd_scrape()


async def _timed_scrape(label: str, coro, timer: PipelineTimer) -> int:
    if not timer.enabled:
        return await coro
    started = time.perf_counter()
    try:
        return await coro
    finally:
        timer.record(f"scrape {label}", time.perf_counter() - started)


async def _run_selected_scrapes(
    *,
    run_betr: bool,
    run_dk: bool,
    run_fd: bool,
    league: str,
    timer: PipelineTimer,
) -> dict[str, int]:
    """Run enabled scrapers in parallel; keys are betr, dk, fd."""
    labels: list[str] = []
    coros = []
    if run_betr:
        labels.append("betr")
        coros.append(_timed_scrape("betr", _scrape_betr(league), timer))
    if run_dk:
        labels.append("dk")
        coros.append(_timed_scrape("dk", _scrape_dk(league), timer))
    if run_fd:
        labels.append("fd")
        coros.append(_timed_scrape("fd", _scrape_fd(), timer))
    if not coros:
        return {}
    if timer.enabled:
        wall_start = time.perf_counter()
        counts = await asyncio.gather(*coros)
        timer.record("scrapes (parallel wall)", time.perf_counter() - wall_start)
    else:
        counts = await asyncio.gather(*coros)
    return dict(zip(labels, counts, strict=True))


def run_refresh(
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    skip_scrape: bool = False,
    betr_only: bool = False,
    dk_only: bool = False,
    skip_betr: bool = False,
    skip_dk: bool = False,
    skip_fd: bool = False,
    league: str = DEFAULT_LEAGUE,
    min_ev: float = 0.0,
    top_n: int = 15,
    skip_expiry_check: bool = False,
    include_flat_lines: bool = False,
    plus_ev_only: bool = False,
    timing: bool = False,
) -> int:
    """
    Run scrape → normalize → EV pipeline.

    Returns process exit code (0 success, 1 failure).
    """
    timer = PipelineTimer() if timing else PipelineTimer.disabled()
    data_path = Path(data_dir)
    run_betr = not dk_only and not skip_betr
    run_dk = not betr_only and not skip_dk
    league = _normalize_betr_league(league)

    skip_fd_for_league = skip_fd or _is_mlb_league(league)
    run_fd = not betr_only and not dk_only and not skip_fd_for_league
    if _is_mlb_league(league) and not skip_fd:
        logger.info("skipping FanDuel scrape for MLB (no comparable props)")

    try:
        if run_betr and not skip_scrape:
            with timer.stage("betr auth"):
                _preflight_betr_auth(skip_expiry_check=skip_expiry_check)

        if not skip_scrape:
            try:
                counts = asyncio.run(
                    _run_selected_scrapes(
                        run_betr=run_betr,
                        run_dk=run_dk,
                        run_fd=run_fd,
                        league=league,
                        timer=timer,
                    )
                )
            except Exception as exc:
                logger.error(f"scrape failed: {exc}")
                return 1
            if counts:
                summary = " ".join(f"{name}={count}" for name, count in counts.items())
                logger.info(f"scrapes complete: {summary}")
        else:
            logger.info("skipping scrape — using existing master boards")

        if run_betr or run_dk or run_fd:
            with timer.stage("normalize"):
                normalize_all(data_path)
        elif not skip_scrape:
            with timer.stage("normalize"):
                normalize_all(data_path)

        if betr_only or dk_only:
            logger.info("skipping EV scan (--betr-only or --dk-only)")
            return 0

        filter_min_ev = plus_ev_only or min_ev > 0

        betr_path = data_path / BETR_NORMALIZED
        dk_path = data_path / DK_NORMALIZED
        if not betr_path.exists() and not dk_path.exists():
            logger.error(f"no normalized boards in {data_path}; run scrape first")
            return 1

        with timer.stage("load comparison inputs"):
            betr_props, dk_props, fd_props = load_comparison_inputs(data_path)
        if not betr_props or not dk_props:
            logger.error("missing betr or draftkings normalized props for EV scan")
            return 1

        with timer.stage("match diagnostics"):
            stats = persist_match_diagnostics(
                data_path,
                betr_props,
                dk_props,
                fd_props=fd_props or None,
                include_flat_lines=include_flat_lines,
            )
        with timer.stage("ev scan"):
            opportunities = run_ev_scan(
                data_path,
                normalize_first=False,
                min_ev=min_ev,
                top_n=top_n,
                include_flat_lines=include_flat_lines,
                filter_min_ev=filter_min_ev,
            )
        plus_ev_count = sum(1 for row in opportunities if row.get("plus_ev"))

        logger.success(
            "refresh summary: "
            f"betr={stats['betr_props']} dk={stats['dk_props']} fd={stats.get('fd_props', 0)} "
            f"matched={stats['matched_keys']} ({stats['betr_match_rate_pct']}%) "
            f"unmatched_betr={stats['unmatched_betr']} unmatched_dk={stats['unmatched_dk']} "
            f"top={len(opportunities)} plus_ev={plus_ev_count} "
            f"(min_ev={min_ev}, top_n={top_n})"
        )
        return 0
    finally:
        timer.log_summary()


def build_parser() -> argparse.ArgumentParser:
    """CLI argument parser for run_refresh."""
    parser = argparse.ArgumentParser(
        description="Refresh Betr/DK boards, normalize, and run EV scan."
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Reuse existing master boards; only normalize and EV scan",
    )
    parser.add_argument(
        "--betr-only",
        action="store_true",
        help="Scrape/normalize Betr only (no DK scrape, no EV scan)",
    )
    parser.add_argument(
        "--dk-only",
        action="store_true",
        help="Scrape/normalize DraftKings only (no Betr scrape, no EV scan)",
    )
    parser.add_argument(
        "--skip-betr",
        action="store_true",
        help="Skip Betr scrape and JWT pre-flight (use existing betr_normalized.json for EV)",
    )
    parser.add_argument(
        "--skip-dk",
        action="store_true",
        help="Skip DraftKings scrape (use existing dk_normalized.json for EV)",
    )
    parser.add_argument(
        "--skip-fd",
        action="store_true",
        help="Skip FanDuel scrape (use existing fd_normalized.json for EV)",
    )
    parser.add_argument(
        "--league",
        type=str.upper,
        default=DEFAULT_LEAGUE,
        help=(
            f"Betr league for LeagueUpcomingEvents and DK slate key "
            f"(default: {DEFAULT_LEAGUE}; MLB auto-skips FanDuel; case-insensitive)"
        ),
    )
    parser.add_argument(
        "--min-ev",
        type=float,
        default=0.0,
        help="Edge threshold: plus_ev when ev > value; also filters output when > 0 (see --plus-ev-only)",
    )
    parser.add_argument(
        "--plus-ev-only",
        action="store_true",
        help="Only include rows with ev > --min-ev in output (use --min-ev 0 for positive-EV only)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=15,
        help="Maximum ranked plays written to ev_opportunities.json (default: 15)",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help="Processed data directory (default: data/processed)",
    )
    parser.add_argument(
        "--skip-expiry-check",
        action="store_true",
        help="Skip JWT expiry pre-flight (not recommended)",
    )
    parser.add_argument(
        "--include-flat-lines",
        action="store_true",
        help="Include Betr integer lines (push risk) in EV scan with adjusted breakeven",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Print wall-clock timing for each pipeline stage at the end",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    os.chdir(_backend_root())
    args = build_parser().parse_args(argv)

    if args.betr_only and args.dk_only:
        logger.error("use at most one of --betr-only and --dk-only")
        raise SystemExit(1)
    if args.betr_only and args.skip_betr:
        logger.error("--betr-only conflicts with --skip-betr")
        raise SystemExit(1)
    if args.dk_only and args.skip_dk:
        logger.error("--dk-only conflicts with --skip-dk")
        raise SystemExit(1)

    code = run_refresh(
        data_dir=args.data_dir,
        skip_scrape=args.skip_scrape,
        betr_only=args.betr_only,
        dk_only=args.dk_only,
        skip_betr=args.skip_betr,
        skip_dk=args.skip_dk,
        skip_fd=args.skip_fd,
        league=args.league,
        min_ev=args.min_ev,
        top_n=args.top_n,
        skip_expiry_check=args.skip_expiry_check,
        include_flat_lines=args.include_flat_lines,
        plus_ev_only=args.plus_ev_only,
        timing=args.timing,
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
