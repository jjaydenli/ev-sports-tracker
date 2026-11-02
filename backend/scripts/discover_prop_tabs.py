"""Discover sportsbook player-prop tabs by reading what each one actually returns.

Companion to ``verify_dk_subcategories``, which confirms ids already known. This
finds the unknown ones, for any league and for pregame or live.

Each book plugs into ``BOOKS`` with a function returning ``TabProbe`` rows, so the
verdict logic below is shared. DraftKings has no tab listing, so its adapter sweeps
numeric ids near the configured ones (ids cluster). FanDuel lists its tabs on every
event page, so one request per event is enough; its tabs depend on the event itself,
so pick a live game with --event-id, since --state does not filter FanDuel's slate.
ESPN has no adapter: ``probe_espn_milestone_drawers`` already prints every drawer.

Verdicts are guarded twice, because a false "absent" hides a market for a season:

- A **control** tab (a configured id) must return markets, or the event is excluded.
  An event with no props posted yet would otherwise read as every tab being absent.
- A **blocked** request is unknown, never absent, and fails the run.

examples:
  # sweep around every configured live NBA id on two in-progress games
  python -m scripts.discover_prop_tabs --league nba --state live

  # list every FanDuel tab on two slate games
  python -m scripts.discover_prop_tabs --book fanduel --league nba --state pregame

  # sweep explicit ids and ranges on chosen events
  python -m scripts.discover_prop_tabs --league nba --state pregame \\
      --event-id 34936963 34936964 --ids 2716470-2716500 13762
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config.api_headers import DK_BASE_HEADERS, FD_BASE_HEADERS  # noqa: E402
from config.dk_subcategories import (  # noqa: E402
    PropTabs,
    subcategories_for_league,
    subcategory_market_labels,
)
from config.fd_competitions import event_tab_labels_for_league  # noqa: E402
from scrapers.sportsbooks import fd_api  # noqa: E402
from scrapers.sportsbooks.dk_api import (  # noqa: E402
    LIVE_EVENT_STATUSES,
    SCRAPABLE_EVENT_STATUSES,
    classify_tab_shape,
    extract_event_ids,
    fetch_event_subcategory_markets,
    fetch_league_events,
    infer_canonical_market_from_dk_payload,
)

DEFAULT_CONCURRENCY = 2
DEFAULT_PAD = 15
MAX_TABS_PER_EVENT = 600


@dataclass(frozen=True)
class TabProbe:
    """What one tab returned for one event."""

    event_id: str
    tab_id: str
    blocked: bool = False
    markets: int = 0
    selections: int = 0
    shape: str = "empty"
    inferred: str | None = None
    sample: str = ""
    is_control: bool = False
    listed: bool = False  # the book named this tab, whatever it holds right now

    @property
    def hit(self) -> bool:
        return self.listed or self.markets > 0


@dataclass(frozen=True)
class Discovery:
    """Shared verdict over every probe from one run."""

    hits: dict[str, list[TabProbe]]
    absent: list[str]
    valid_events: list[str]
    unposted_events: list[str]
    blocked: int


def parse_id_spec(tokens: Iterable[str]) -> list[str]:
    """Expand ``["100-102", "7"]`` to ``["100", "101", "102", "7"]``."""
    ids: list[str] = []
    for token in tokens:
        start, sep, end = token.partition("-")
        if not sep:
            ids.append(str(int(token)))
            continue
        low, high = int(start), int(end)
        if high < low:
            raise ValueError(f"descending id range: {token}")
        ids.extend(str(value) for value in range(low, high + 1))
    return ids


def neighborhood_ids(seeds: Iterable[str], pad: int) -> list[str]:
    """Return every id within ``pad`` of a seed, sorted; ids cluster by market family."""
    window = {v for seed in seeds for v in range(int(seed) - pad, int(seed) + pad + 1)}
    return [str(value) for value in sorted(window)]


def summarize(probes: Iterable[TabProbe]) -> Discovery:
    """Reduce probes to hits, absences and event validity.

    A tab that returned markets is real wherever it did. A tab is absent only when
    it answered empty on every valid event: blocked answers and events with no
    control hit say nothing about whether it exists.
    """
    rows = list(probes)
    events = list(dict.fromkeys(probe.event_id for probe in rows))
    valid = [
        event
        for event in events
        if any(p.event_id == event and p.is_control and p.hit for p in rows)
    ]
    valid_rows = [probe for probe in rows if probe.event_id in valid]

    hits: dict[str, list[TabProbe]] = {}
    for probe in rows:
        if probe.hit:
            hits.setdefault(probe.tab_id, []).append(probe)

    blocked_tabs = {probe.tab_id for probe in rows if probe.blocked}
    absent = [
        tab_id
        for tab_id in dict.fromkeys(probe.tab_id for probe in valid_rows)
        if tab_id not in hits and tab_id not in blocked_tabs
    ]
    return Discovery(
        hits=hits,
        absent=absent,
        valid_events=valid,
        unposted_events=[event for event in events if event not in valid],
        blocked=sum(probe.blocked for probe in rows),
    )


def _state_tabs(league: str, state: str) -> PropTabs:
    subs = subcategories_for_league(league)
    return subs.live if state == "live" else subs.pregame


async def _resolve_dk_events(
    client: httpx.AsyncClient, args: argparse.Namespace
) -> list[str]:
    if args.event_id:
        return list(args.event_id)
    payload = await fetch_league_events(client, args.league)
    statuses = LIVE_EVENT_STATUSES if args.state == "live" else SCRAPABLE_EVENT_STATUSES
    return extract_event_ids(payload or {}, statuses=statuses)[: args.events]


async def _probe_dk_tab(
    client: httpx.AsyncClient,
    gate: asyncio.Semaphore,
    event_id: str,
    tab_id: str,
    is_control: bool,
) -> TabProbe:
    async with gate:
        payload = await fetch_event_subcategory_markets(client, event_id, tab_id)
    if payload is None:
        return TabProbe(event_id, tab_id, blocked=True, is_control=is_control)
    markets = payload.get("markets") or []
    return TabProbe(
        event_id=event_id,
        tab_id=tab_id,
        markets=len(markets),
        selections=len(payload.get("selections") or []),
        shape=classify_tab_shape(payload),
        inferred=infer_canonical_market_from_dk_payload(payload),
        sample=str(markets[0].get("name") or "") if markets else "",
        is_control=is_control,
    )


async def discover_dk(args: argparse.Namespace) -> list[TabProbe]:
    """Sweep DK ids on each event; every configured id doubles as a control."""
    tabs = _state_tabs(args.league, args.state)
    configured = [*tabs.configured_ou.values(), *tabs.configured_milestone.values()]
    if not configured:
        raise SystemExit(f"no configured {args.state} ids for {args.league} to use as a control")

    candidates = parse_id_spec(args.ids) if args.ids else neighborhood_ids(configured, args.pad)
    # Explicit --ids may miss every configured id, so always add one control.
    tab_ids = list(dict.fromkeys([*candidates, configured[0]]))
    if len(tab_ids) > MAX_TABS_PER_EVENT:
        raise SystemExit(f"{len(tab_ids)} ids per event exceeds {MAX_TABS_PER_EVENT}; narrow the sweep")

    gate = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(headers=DK_BASE_HEADERS, timeout=15.0) as client:
        events = await _resolve_dk_events(client, args)
        if not events:
            raise SystemExit(f"no {args.state} {args.league} events on the slate")
        print(f"draftkings {args.league} {args.state}: {len(tab_ids)} ids x {len(events)} events")
        control_ids = set(configured)
        return list(
            await asyncio.gather(
                *(
                    _probe_dk_tab(client, gate, event_id, tab_id, tab_id in control_ids)
                    for event_id in events
                    for tab_id in tab_ids
                )
            )
        )


async def discover_fd(args: argparse.Namespace) -> list[TabProbe]:
    """Read each event's ``layout.tabs``; any tab we already scrape is the control."""
    known_titles = set(event_tab_labels_for_league(args.league).values())
    async with httpx.AsyncClient(headers=FD_BASE_HEADERS, timeout=15.0) as client:
        events = args.event_id or (await fd_api.fetch_league_event_ids(client, args.league))[: args.events]
        if not events:
            raise SystemExit(f"no {args.league} events on the slate")
        print(f"fanduel {args.league}: tab listing on {len(events)} events")
        probes: list[TabProbe] = []
        for event_id in events:
            payload = await fd_api.fetch_event_page(client, event_id)
            if payload is None:
                probes.append(TabProbe(event_id, "*", blocked=True))
                continue
            tabs = (payload.get("layout") or {}).get("tabs") or {}
            probes.extend(
                TabProbe(
                    event_id=event_id,
                    tab_id=str(tab.get("title")),
                    shape="listed",
                    is_control=tab.get("title") in known_titles,
                    listed=True,
                )
                for tab in tabs.values()
            )
        return probes


def _fd_known_labels(league: str) -> dict[str, str]:
    return {title: f"tab:{slug}" for slug, title in event_tab_labels_for_league(league).items()}


def _dk_known_labels(_league: str) -> dict[str, str]:
    return subcategory_market_labels()


@dataclass(frozen=True)
class BookAdapter:
    """One book's way of listing tabs, and of naming the ones already wired."""

    discover: Callable[[argparse.Namespace], Awaitable[list[TabProbe]]]
    known_labels: Callable[[str], dict[str, str]]


BOOKS: dict[str, BookAdapter] = {
    "draftkings": BookAdapter(discover_dk, _dk_known_labels),
    "fanduel": BookAdapter(discover_fd, _fd_known_labels),
}


def render(discovery: Discovery, known: dict[str, str]) -> str:
    """Format a discovery for the terminal, new tabs first."""
    lines = [f"valid events: {', '.join(discovery.valid_events) or 'none'}"]
    if discovery.unposted_events:
        lines.append(
            f"EXCLUDED, control empty (props not posted?): {', '.join(discovery.unposted_events)}"
        )
    if discovery.blocked:
        lines.append(f"INCOMPLETE: {discovery.blocked} blocked requests, those tabs are unknown")

    events = len(discovery.valid_events) + len(discovery.unposted_events)
    ordered = sorted(discovery.hits, key=lambda tab_id: (tab_id in known, tab_id.zfill(12)))
    for tab_id in ordered:
        probes = discovery.hits[tab_id]
        best = max(probes, key=lambda probe: probe.markets)
        label = known.get(tab_id, "NEW")
        lines.append(
            f"{tab_id:>16} {label:24} {best.shape:9} {len(probes)}/{events} events "
            f"markets={best.markets:<3} inferred={best.inferred or '-':14} {best.sample!r}"
        )
    lines.append(f"absent on all valid events: {len(discovery.absent)} ids")
    return "\n".join(lines)


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--book", choices=sorted(BOOKS), default="draftkings")
    parser.add_argument("--league", required=True, choices=("nba", "mlb", "wnba"))
    parser.add_argument("--state", required=True, choices=("pregame", "live"))
    parser.add_argument("--event-id", nargs="+", help="Default: first --events slate games")
    parser.add_argument("--events", type=_positive_int, default=2, help="Slate games to sweep")
    parser.add_argument("--ids", nargs="+", metavar="ID", help="Ids or ranges, e.g. 16755-16784")
    parser.add_argument("--pad", type=_positive_int, default=DEFAULT_PAD, help="Default sweep width")
    parser.add_argument("--concurrency", type=_positive_int, default=DEFAULT_CONCURRENCY)
    return parser


async def main() -> int:
    args = build_parser().parse_args()
    adapter = BOOKS[args.book]
    discovery = summarize(await adapter.discover(args))
    print(render(discovery, adapter.known_labels(args.league)))
    return 0 if discovery.valid_events and not discovery.blocked else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
