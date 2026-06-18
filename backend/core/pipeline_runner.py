"""End-to-end refresh: scrape all leagues → normalize → EV scan."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import uuid
import warnings
from pathlib import Path

from loguru import logger

from config.pipeline_sources import (
    BOOK_SOURCES,
    DFS_SOURCES,
    PIPELINE_LEAGUES,
    parse_csv_sources,
    parse_leagues,
)
from core.ev_pipeline import (
    load_comparison_inputs,
    persist_match_diagnostics,
    run_ev_scan,
)
from core.pipeline_artifacts import (
    BETR_NORMALIZED,
    DK_NORMALIZED,
    SCRAPE_COVERAGE_FILENAME,
    all_pipeline_artifacts,
    artifacts_for_sources,
    load_wrapped_board,
    write_scrape_coverage,
    wipe_files,
)
from core.pipeline_scrape import scrape_source_league
from core.pipeline_timing import PipelineTimer
from core.scrape_result import ScrapeResult
from parsers.normalize import normalize_all, persist_source_boards, persist_unified_board
from scrapers.dfs.betr.betr_auth import BetrAuthError, ensure_betr_token, validate_betr_token_or_raise


DEFAULT_DATA_DIR = "data/processed"


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


def _resolve_run_scope(
    *,
    dfs: tuple[str, ...] | None,
    books: tuple[str, ...] | None,
    leagues: tuple[str, ...] | None,
    scrape_only: bool,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Resolve dfs, books, and leagues for this invocation."""
    if scrape_only:
        resolved_dfs = dfs if dfs is not None else DFS_SOURCES
        resolved_books = books if books is not None else BOOK_SOURCES
    else:
        resolved_dfs = DFS_SOURCES
        resolved_books = books if books is not None else BOOK_SOURCES
    resolved_leagues = leagues if leagues is not None else PIPELINE_LEAGUES
    return resolved_dfs, resolved_books, resolved_leagues


def _is_full_run(
    dfs_sources: tuple[str, ...],
    book_sources: tuple[str, ...],
    leagues: tuple[str, ...],
) -> bool:
    return (
        dfs_sources == DFS_SOURCES
        and book_sources == BOOK_SOURCES
        and leagues == PIPELINE_LEAGUES
    )


def _format_coverage_summary(sources: dict[str, dict]) -> str:
    parts = []
    for key in sorted(sources):
        entry = sources[key]
        status = entry.get("status", "?")
        count = entry.get("prop_count", 0)
        parts.append(f"{key}={status}({count})")
    return " ".join(parts)


async def _scrape_league_sources(
    league: str,
    dfs_sources: tuple[str, ...],
    book_sources: tuple[str, ...],
    timer: PipelineTimer,
) -> list[ScrapeResult]:
    """Scrape all enabled sources for one league in parallel."""
    labels: list[str] = []
    coros = []
    for source in dfs_sources:
        labels.append(source)
        coros.append(scrape_source_league(source, league))
    for source in book_sources:
        labels.append(source)
        coros.append(scrape_source_league(source, league))

    if not coros:
        return []

    if timer.enabled:
        wall_start = time.perf_counter()
        results = await asyncio.gather(*coros)
        timer.record(
            f"scrape league {league} (parallel wall)",
            time.perf_counter() - wall_start,
        )
    else:
        results = await asyncio.gather(*coros)
    return list(results)


def _accumulate_results(
    accumulators: dict[str, list[dict]],
    results: list[ScrapeResult],
    coverage: dict[str, dict],
) -> None:
    for result in results:
        coverage[result.coverage_key] = result.to_dict()
        if result.props:
            accumulators[result.source].extend(result.props)


def _source_has_props(accumulators: dict[str, list[dict]], sources: tuple[str, ...]) -> bool:
    return any(len(accumulators.get(source, [])) > 0 for source in sources)


def _any_source_failed(
    coverage: dict[str, dict],
    sources: tuple[str, ...],
) -> bool:
    for key, entry in coverage.items():
        source = key.split(":", 1)[0]
        if source in sources and entry.get("status") == "failed":
            return True
    return False


def normalize_league_flag_argv(argv: list[str] | None) -> list[str] | None:
    """Lowercase per-league shorthand flags so --WNBA matches --wnba."""
    if argv is None:
        return None
    league_flags = {f"--{lg.lower()}" for lg in PIPELINE_LEAGUES}
    return [
        token.lower() if token.lower() in league_flags else token
        for token in argv
    ]


def merge_leagues_from_args(args: argparse.Namespace) -> tuple[str, ...] | None:
    """Union --leagues with any --<league> shorthand flags; empty means all leagues."""
    shorthand = [
        lg for lg in PIPELINE_LEAGUES if getattr(args, lg.lower(), False)
    ]
    from_csv = parse_leagues(args.leagues) or ()
    merged = tuple(dict.fromkeys((*from_csv, *shorthand)))
    return merged if merged else None


def _apply_deprecated_flags(args: argparse.Namespace) -> argparse.Namespace:
    """Map legacy skip/only flags onto --dfs/--books/--leagues/--scrape-only."""
    if getattr(args, "betr_only", False):
        warnings.warn(
            "--betr-only is deprecated; use --dfs betr --scrape-only",
            DeprecationWarning,
            stacklevel=2,
        )
        args.dfs = "betr"
        args.scrape_only = True
    if getattr(args, "dk_only", False):
        warnings.warn(
            "--dk-only is deprecated; use --books dk --scrape-only",
            DeprecationWarning,
            stacklevel=2,
        )
        args.books = "dk"
        args.scrape_only = True
    if getattr(args, "skip_betr", False):
        warnings.warn(
            "--skip-betr is deprecated; partial book runs always refresh all dfs",
            DeprecationWarning,
            stacklevel=2,
        )
    if getattr(args, "skip_dk", False):
        warnings.warn(
            "--skip-dk is deprecated; use --books fd (etc.)",
            DeprecationWarning,
            stacklevel=2,
        )
        if args.books is None:
            args.books = "fd"
        else:
            args.books = ",".join(
                b for b in args.books.split(",") if b.strip().lower() != "dk"
            )
    if getattr(args, "skip_fd", False):
        warnings.warn(
            "--skip-fd is deprecated; use --books dk",
            DeprecationWarning,
            stacklevel=2,
        )
        if args.books is None:
            args.books = "dk"
        else:
            args.books = ",".join(
                b for b in args.books.split(",") if b.strip().lower() != "fd"
            )
    if getattr(args, "league", None) and not getattr(args, "leagues", None):
        warnings.warn(
            "--league is deprecated; use --leagues",
            DeprecationWarning,
            stacklevel=2,
        )
        args.leagues = args.league
    return args


def run_refresh(
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    skip_scrape: bool = False,
    scrape_only: bool = False,
    dfs: tuple[str, ...] | None = None,
    books: tuple[str, ...] | None = None,
    leagues: tuple[str, ...] | None = None,
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
    run_id = str(uuid.uuid4())
    dfs_sources, book_sources, league_list = _resolve_run_scope(
        dfs=dfs,
        books=books,
        leagues=leagues,
        scrape_only=scrape_only,
    )
    full_run = _is_full_run(dfs_sources, book_sources, league_list)
    mode = "skip_scrape" if skip_scrape else ("scrape_only" if scrape_only else "full")

    try:
        if skip_scrape:
            logger.info("skipping scrape — normalizing from master boards on disk")
            with timer.stage("normalize"):
                normalize_all(data_path)
        else:
            prior_ev_path = data_path / "ev_opportunities.json"
            _, prior_run_id = load_wrapped_board(prior_ev_path)

            if full_run:
                wipe_files(data_path, list(all_pipeline_artifacts()))
            else:
                wipe_files(
                    data_path,
                    artifacts_for_sources(
                        DFS_SOURCES,
                        book_sources,
                        include_ev=not scrape_only,
                        include_shared=True,
                    ),
                )

            if "betr" in dfs_sources:
                with timer.stage("betr auth"):
                    _preflight_betr_auth(skip_expiry_check=skip_expiry_check)

            accumulators: dict[str, list[dict]] = {
                source: [] for source in (*dfs_sources, *book_sources)
            }
            coverage: dict[str, dict] = {}

            for league in league_list:
                with timer.stage(f"scrape {league}"):
                    try:
                        results = asyncio.run(
                            _scrape_league_sources(
                                league,
                                dfs_sources,
                                book_sources,
                                timer,
                            )
                        )
                    except Exception as exc:
                        logger.error(f"scrape failed for league {league}: {exc}")
                        return 1
                    _accumulate_results(accumulators, results, coverage)

            logger.info(f"scrape coverage: {_format_coverage_summary(coverage)}")

            with timer.stage("normalize"):
                normalized_chunks: list[list[dict]] = []
                for source in (*dfs_sources, *book_sources):
                    raw_props = accumulators[source]
                    if not raw_props:
                        logger.info(f"{source}: no props across leagues — skipping board write")
                        continue
                    normalized_chunks.append(
                        persist_source_boards(
                            data_path,
                            run_id=run_id,
                            source=source,
                            raw_props=raw_props,
                        )
                    )
                if normalized_chunks:
                    persist_unified_board(
                        data_path,
                        run_id=run_id,
                        normalized_chunks=normalized_chunks,
                    )

            dfs_ok = _source_has_props(accumulators, dfs_sources)
            books_ok = _source_has_props(accumulators, book_sources)
            ev_eligible = dfs_ok and books_ok and not scrape_only

            write_scrape_coverage(
                data_path / SCRAPE_COVERAGE_FILENAME,
                run_id=run_id,
                mode=mode,
                dfs_sources=dfs_sources,
                book_sources=book_sources,
                leagues=league_list,
                sources=coverage,
                ev_eligible=ev_eligible,
                previous_run_id=prior_run_id,
            )

            if scrape_only:
                logger.success("scrape-only complete (no EV scan)")
                return 0

            if not dfs_ok or not books_ok:
                logger.error(
                    "EV requires at least one dfs source and one book with props "
                    f"(dfs_ok={dfs_ok}, books_ok={books_ok})"
                )
                return 1

            if _any_source_failed(coverage, dfs_sources + book_sources):
                if not (dfs_ok and books_ok):
                    return 1
                logger.warning(
                    "some source/league scrapes failed; continuing with available props"
                )

        if scrape_only:
            return 0

        filter_min_ev = plus_ev_only or min_ev > 0

        betr_path = data_path / BETR_NORMALIZED
        dk_path = data_path / DK_NORMALIZED
        if not betr_path.exists() and not dk_path.exists():
            logger.error(f"no normalized boards in {data_path}; run scrape first")
            return 1

        with timer.stage("load comparison inputs"):
            expected_run_id = None if skip_scrape else run_id
            active_sources = (
                None
                if skip_scrape
                else (*dfs_sources, *book_sources)
            )
            betr_props, dk_props, fd_props = load_comparison_inputs(
                data_path,
                expected_run_id=expected_run_id,
                active_sources=active_sources,
            )
        if not betr_props:
            logger.error("missing betr normalized props for EV scan")
            return 1
        if not dk_props and not fd_props:
            logger.error(
                "missing sharp book normalized props for EV scan (need dk and/or fd)"
            )
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
                expected_run_id=expected_run_id,
                active_sources=active_sources,
            )
        plus_ev_count = sum(1 for row in opportunities if row.get("plus_ev"))

        logger.success(
            "refresh summary: "
            f"betr={stats['betr_props']} dk={stats['dk_props']} fd={stats.get('fd_props', 0)} "
            f"matched={stats['matched_keys']} ({stats['betr_match_rate_pct']}%) "
            f"unmatched_betr={stats['unmatched_betr']} unmatched_dk={stats['unmatched_dk']} "
            f"top={len(opportunities)} plus_ev={plus_ev_count} "
            f"(min_ev={min_ev}, top_n={top_n}) run_id={run_id}"
        )
        return 0
    finally:
        timer.log_summary()


def build_parser() -> argparse.ArgumentParser:
    """CLI argument parser for run_refresh."""
    parser = argparse.ArgumentParser(
        description="Refresh dfs/books boards (all leagues), normalize, and run EV scan."
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Reuse existing master boards; normalize and EV scan only",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Scrape and normalize only (no EV scan)",
    )
    parser.add_argument(
        "--dfs",
        type=str,
        default=None,
        help=(
            "Comma-separated dfs apps to scrape (default: all). "
            "On EV runs all dfs are always refreshed; use with --scrape-only to limit."
        ),
    )
    parser.add_argument(
        "--books",
        type=str,
        default=None,
        help="Comma-separated sportsbooks to scrape (default: all). EV runs always refresh all dfs.",
    )
    parser.add_argument(
        "--leagues",
        type=str,
        default=None,
        help=f"Comma-separated leagues (default: {','.join(PIPELINE_LEAGUES)})",
    )
    parser.add_argument(
        "--min-ev",
        type=float,
        default=0.0,
        help="Edge threshold: plus_ev when ev > value; also filters output when > 0",
    )
    parser.add_argument(
        "--plus-ev-only",
        action="store_true",
        help="Only include rows with ev > --min-ev in output",
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
        help="Include Betr integer lines (push risk) in EV scan",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Print wall-clock timing for each pipeline stage at the end",
    )
    parser.add_argument("--betr-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dk-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-betr", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-dk", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-fd", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--league", type=str, default=None, help=argparse.SUPPRESS)
    for league in PIPELINE_LEAGUES:
        parser.add_argument(
            f"--{league.lower()}",
            action="store_true",
            help=f"Include {league} in this run (shorthand for --leagues {league.lower()})",
        )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint."""
    os.chdir(_backend_root())
    argv = normalize_league_flag_argv(argv)
    args = build_parser().parse_args(argv)
    args = _apply_deprecated_flags(args)

    if args.skip_scrape and args.scrape_only:
        logger.error("--skip-scrape and --scrape-only are mutually exclusive")
        raise SystemExit(1)

    try:
        dfs = parse_csv_sources(args.dfs, valid=DFS_SOURCES, label="dfs")
        books = parse_csv_sources(args.books, valid=BOOK_SOURCES, label="books")
        leagues = merge_leagues_from_args(args)
    except ValueError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc

    code = run_refresh(
        data_dir=args.data_dir,
        skip_scrape=args.skip_scrape,
        scrape_only=args.scrape_only,
        dfs=dfs,
        books=books,
        leagues=leagues,
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
