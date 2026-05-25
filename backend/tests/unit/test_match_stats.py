from core.engine import compute_match_stats


def test_compute_match_stats_counts_cross_book_matches():
    betr = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "over_odds": -120,
            "under_odds": -120,
        },
        {
            "player": "No Match",
            "market": "assists",
            "line": 5.5,
            "over_odds": -120,
            "under_odds": -120,
        },
    ]
    dk = [
        {
            "player": "Test Player",
            "market": "points",
            "line": 20.5,
            "over_odds": -110,
            "under_odds": -110,
        }
    ]

    stats = compute_match_stats(betr, dk)

    assert stats == {"betr_props": 2, "dk_props": 1, "matched_keys": 1}
