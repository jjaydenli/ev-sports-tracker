"""End-to-end refresh: Betr + DraftKings scrape → normalize → EV scan."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from loguru import logger

from core.ev_pipeline import (
    BETR_NORMALIZED,
    DK_NORMALIZED,
    load_comparison_inputs,
    persist_match_diagnostics,
    run_ev_scan,
)
from parsers.normalize import normalize_all
from scrapers.dfs.betr.betr_auth import BetrAuthError, ensure_betr_token, validate_betr_token_or_raise
from scrapers.dfs.betr.betr_engine import run_betr_scrape
from scrapers.sportsbooks.dk_engine import run_dk_scrape

DEFAULT_DATA_DIR = "data/processed"
DEFAULT_LEAGUE = "NBA"


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


async def _scrape_dk() -> int:
    return await run_dk_scrape()


def run_refresh(
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    skip_scrape: bool = False,
    betr_only: bool = False,
    dk_only: bool = False,
    league: str = DEFAULT_LEAGUE,
    min_ev: float = 0.0,
    top_n: int = 15,
    skip_expiry_check: bool = False,
) -> int:
    """
    Run scrape → normalize → EV pipeline.

    Returns process exit code (0 success, 1 failure).
    """
    data_path = Path(data_dir)
    run_betr = not dk_only
    run_dk = not betr_only

    if run_betr and not skip_scrape:
        _preflight_betr_auth(skip_expiry_check=skip_expiry_check)

    if not skip_scrape:
        if run_betr and run_dk:
            async def _both() -> tuple[int, int]:
                betr_count, dk_count = await asyncio.gather(
                    _scrape_betr(league),
                    _scrape_dk(),
                )
                return betr_count, dk_count

            try:
                betr_count, dk_count = asyncio.run(_both())
            except Exception as exc:
                logger.error(f"scrape failed: {exc}")
                return 1
            logger.info(f"scrapes complete: betr={betr_count} dk={dk_count}")
        elif run_betr:
            try:
                betr_count = asyncio.run(_scrape_betr(league))
            except Exception as exc:
                logger.error(f"betr scrape failed: {exc}")
                return 1
            logger.info(f"betr scrape complete: {betr_count} props")
        elif run_dk:
            try:
                dk_count = asyncio.run(_scrape_dk())
            except Exception as exc:
                logger.error(f"draftkings scrape failed: {exc}")
                return 1
            logger.info(f"draftkings scrape complete: {dk_count} props")
    else:
        logger.info("skipping scrape — using existing master boards")

    if run_betr or run_dk:
        normalize_all(data_path)
    elif not skip_scrape:
        normalize_all(data_path)

    if betr_only or dk_only:
        logger.info("skipping EV scan (--betr-only or --dk-only)")
        return 0

    betr_path = data_path / BETR_NORMALIZED
    dk_path = data_path / DK_NORMALIZED
    if not betr_path.exists() and not dk_path.exists():
        logger.error(f"no normalized boards in {data_path}; run scrape first")
        return 1

    betr_props, dk_props = load_comparison_inputs(data_path)
    if not betr_props or not dk_props:
        logger.error("missing betr or draftkings normalized props for EV scan")
        return 1

    stats = persist_match_diagnostics(data_path, betr_props, dk_props)
    opportunities = run_ev_scan(
        data_path, normalize_first=False, min_ev=min_ev, top_n=top_n
    )
    plus_ev_count = sum(1 for row in opportunities if row.get("plus_ev"))

    logger.success(
        "refresh summary: "
        f"betr={stats['betr_props']} dk={stats['dk_props']} "
        f"matched={stats['matched_keys']} ({stats['betr_match_rate_pct']}%) "
        f"unmatched_betr={stats['unmatched_betr']} unmatched_dk={stats['unmatched_dk']} "
        f"top={len(opportunities)} plus_ev={plus_ev_count} "
        f"(min_ev={min_ev}, top_n={top_n})"
    )
    return 0


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
        "--league",
        default=DEFAULT_LEAGUE,
        help=f"Betr league for LeagueUpcomingEvents (default: {DEFAULT_LEAGUE})",
    )
    parser.add_argument(
        "--min-ev",
        type=float,
        default=0.0,
        help="Edge threshold for plus_ev flag (rows below still appear in top-N)",
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
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    os.chdir(_backend_root())
    args = build_parser().parse_args(argv)

    if args.betr_only and args.dk_only:
        logger.error("use at most one of --betr-only and --dk-only")
        raise SystemExit(1)

    code = run_refresh(
        data_dir=args.data_dir,
        skip_scrape=args.skip_scrape,
        betr_only=args.betr_only,
        dk_only=args.dk_only,
        league=args.league,
        min_ev=args.min_ev,
        top_n=args.top_n,
        skip_expiry_check=args.skip_expiry_check,
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
