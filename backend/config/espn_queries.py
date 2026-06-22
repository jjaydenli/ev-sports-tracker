"""ESPN (TheScore Bet) GraphQL persisted-query registry.

TheScore Bet / ESPN BET serves data via **GraphQL persisted queries** (GET): the client
sends only ``operationName`` + ``variables`` + an ``extensions`` blob carrying the
``sha256Hash`` of the server-side query body. Hashes and the app version rotate together
when the web app ships a new build, so they live in one env-overridable home.

Captured + validated live 2026-06-22 (app version ``26.12.0``). See ``docs/betting_odds/espn.md``.
"""

from __future__ import annotations

import json
import os

# App version the captured hashes belong to. Hashes rotate with the web build, so override
# ESPN_APP_VERSION (and the hashes below, if needed) together when ESPN ships a new bundle.
ESPN_APP_VERSION = os.getenv("ESPN_APP_VERSION", "26.12.0")

# Persisted-query version (the ``extensions.persistedQuery.version`` field). Stable at 1.
ESPN_PERSISTED_QUERY_VERSION = int(os.getenv("ESPN_PERSISTED_QUERY_VERSION", "1"))

# {operationName: sha256Hash}. Each value is also the path segment:
# /graphql/persisted_queries/<sha256Hash>?operationName=<Op>&variables=...&extensions=...
ESPN_PERSISTED_QUERIES: dict[str, str] = {
    # Anonymous bootstrap — mints data.startup.anonymousToken (the JWE). No auth header.
    "Startup": "72b1ffd2b081b918369a7e942093ec666b55c2f3768608a7ec76150db5ebcf62",
    # Competition (league) page → section list (Lines / Home Runs / Futures / …).
    "CompetitionPage": "5a1f47ccb1ac7b7c1f7da8d6607e6d6c429b25ba57b749961711a6cd4aa32119",
    # Default Lines section → the games list (StandardEvent ids).
    "CompetitionPageSectionLinesTabNode": (
        "35c91eef7459e3a5edbc18424f85dfd6905fb0abf0a2a77660f6f34b51d4a72b"
    ),
    # Per-event page → that event's sections (pitcher-props / batter-props ids).
    "EventPage": "10206a951d1f60440e00341961324273fe47ba879ff2271fb98eaa3d0d5ee679",
    # Per-event section → drawer stubs (one *(O/U) drawer per stat).
    "EventSection": "8ac31d28c8fd43e02a73beebd64e888bb0390db701907ecbd7b633a1bf00a750",
    # Per-drawer content → the actual OVER/UNDER markets + selections (the O/U leaf).
    "EventDrawerContent": "0f351a688287fbcb437b57d8b6ec26ded758eb18fc889ca04b2595f7aa6960f1",
}


def persisted_query_hash(operation_name: str) -> str:
    """Return the sha256Hash for an operationName, or raise if unregistered."""
    try:
        return ESPN_PERSISTED_QUERIES[operation_name]
    except KeyError as exc:
        raise KeyError(
            f"no ESPN persisted-query hash registered for {operation_name!r}; "
            "re-capture hashes after an app-version bump and update config/espn_queries.py"
        ) from exc


def persisted_query_extensions(operation_name: str) -> str:
    """Return the JSON ``extensions`` query-string value for an operationName."""
    extensions = {
        "persistedQuery": {
            "version": ESPN_PERSISTED_QUERY_VERSION,
            "sha256Hash": persisted_query_hash(operation_name),
        }
    }
    return json.dumps(extensions, separators=(",", ":"))
