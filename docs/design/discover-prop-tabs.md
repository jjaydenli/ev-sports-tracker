# Prop tab discovery

## Context

Sportsbook tab ids are not published. Until now, unknown DraftKings ids came from reading the
browser's network tab one stat at a time, with `verify_dk_subcategories` confirming each candidate.
That works for a known tab, but it cannot show that a market is missing. An earlier range-scan module
was removed because nothing used it, so this tool starts from a different requirement: a verdict that
can be trusted when it says a tab is absent.

## Design decisions

- **A false "absent" is the failure that matters.** It hides a market for a season, so a tab is
  reported absent only when it answered empty on every valid event.
- **Control tabs define a valid event.** A configured id must return markets, or the event is excluded.
  An event with no props posted yet would otherwise read as every tab being absent.
- **A blocked request is unknown, never absent**, and it fails the run.
- **Books plug in as adapters over one verdict.** Each adapter returns `TabProbe` rows and `summarize`
  decides. DraftKings has no tab listing, so its adapter sweeps ids near the configured ones, since ids
  cluster. FanDuel names its tabs on every event page, so it needs one request per event. ESPN has no
  adapter because `probe_espn_milestone_drawers` already prints every drawer.
- **The sweep is bounded:** concurrency 2 by default, with a cap of 600 tabs per event.
- **`classify_tab_shape` lives in `dk_api`, beside the selection parsing it reads.** It separates tabs
  the flatteners can read from Yes-only tabs, which fetch cleanly but flatten to zero rows.

## Non-goals

- Writing ids into config. Discovery produces candidates, and `verify_dk_subcategories` still confirms
  each one before it is hardcoded.
- Any pipeline dependency. This is a command line tool only.

## Files / modules

| Path | Change |
|------|--------|
| `backend/scripts/discover_prop_tabs.py` | new tool: book adapters, `summarize`, rendering |
| `backend/scrapers/sportsbooks/dk_api.py` | `classify_tab_shape` |
| `backend/scripts/verify_dk_subcategories.py` | points at the new tool |
| `backend/tests/fixtures/dk_markets_double_double_live_34930762.json` | captured Yes-only tab |

## Test plan

`test_discover_prop_tabs.py` runs shape classification against captured payloads, including the
Yes-only capture, and covers the event and tab verdicts.
