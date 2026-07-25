"""Struktur-Befund (Watchlist-Diagnostik) — alle 5 Kategorien + Grenzfall.

_classify_structure ist reine Logik (Pivot-Preise + Schlusskurs). Reine Anzeige:
Markt/Score/Ranking/Sammlung bleiben unberührt (eigener Test unten).
"""
import elliott_pipeline as pipe


def _state(prices, close):
    return pipe._classify_structure(prices, close)["state"]


# Aufwärts-Impuls-Pivots: P0<P1>P2<P3>P4<P5 (H/L alternierend).
_UP5 = [100.0, 120.0, 110.0, 140.0, 130.0, 160.0]   # komplett bis P5
_UP4 = [100.0, 120.0, 110.0, 140.0, 130.0]           # bis P4 (W5 offen)
_UP2 = [100.0, 120.0, 110.0]                          # bis P2 (W3 offen)


# ---------------------------------------------------------------------------
# Konstruierte Kernfälle — alle 5 Kategorien
# ---------------------------------------------------------------------------
def test_long_setup_end_of_w2():
    # Kurs noch UNTER W1-Hoch (120) -> offenes Ende-W2-Setup.
    r = pipe._classify_structure(_UP2, 115.0)
    assert r["state"] == "long_setup"
    assert "Ende W2" in r["label"]
    assert r["invalidation_price"] == 100.0       # P0
    assert r["direction"] == "long"


def test_long_setup_end_of_w4():
    # Kurs noch UNTER W3-Hoch (140) -> offenes Ende-W4-Setup.
    r = pipe._classify_structure(_UP4, 132.0)
    assert r["state"] == "long_setup"
    assert "Ende W4" in r["label"]
    assert r["invalidation_price"] == 120.0       # P1


def test_impulse_running_w3():
    # W1-Hoch (120) gebrochen -> W3 läuft.
    r = pipe._classify_structure(_UP2, 135.0)
    assert r["state"] == "impulse_running"
    assert "W3" in r["label"]
    assert r["direction"] == "long"


def test_impulse_running_w5():
    # W3-Hoch (140) gebrochen, aber P5 noch NICHT bestätigt (nur 5 Pivots) -> W5 läuft.
    r = pipe._classify_structure(_UP4, 150.0)
    assert r["state"] == "impulse_running"
    assert "W5" in r["label"]


def test_impulse_complete():
    # 6 Pivots, valider kompletter Impuls -> Korrektur A erwartet.
    r = pipe._classify_structure(_UP5, 158.0)
    assert r["state"] == "impulse_complete"
    assert "Korrektur" in r["label"]
    assert r["direction"] == "long"
    assert r["invalidation_price"] == 100.0       # P0


def test_short_structure_down_w2():
    # Abwärts: P0>P1<P2 (P2 unter P0). Long-only gilt nur fürs Markt-Board.
    r = pipe._classify_structure([100.0, 80.0, 90.0], 85.0)
    assert r["state"] == "short_structure"
    assert r["direction"] == "short"
    assert r["invalidation_price"] == 100.0


def test_short_structure_down_complete():
    # Kompletter Abwärts-Impuls (6 Pivots).
    r = pipe._classify_structure([200.0, 180.0, 190.0, 160.0, 170.0, 140.0], 145.0)
    assert r["state"] == "short_structure"
    assert "komplett" in r["label"]


def test_no_structure():
    # W2 retraciert > 100 % (P2 unter P0) -> keine regelkonforme Zählung.
    r = pipe._classify_structure([100.0, 120.0, 90.0], 95.0)
    assert r["state"] == "no_structure"
    assert r["invalidation_price"] is None
    assert r["direction"] is None


def test_too_few_pivots_no_structure():
    assert _state([100.0, 120.0], 110.0) == "no_structure"


# ---------------------------------------------------------------------------
# Grenzfall: W5 gerade komplett (5 Pivots + hoher Kurs vs. 6 Pivots)
# ---------------------------------------------------------------------------
def test_boundary_w5_running_vs_complete():
    # Nur 5 Pivots (P5 unbestätigt), Kurs über W3-Hoch -> „W5 läuft".
    assert _state(_UP4, 150.0) == "impulse_running"
    # Sobald P5 als 6. Pivot bestätigt ist -> „5 komplett" (Priorität kompletter Impuls).
    assert _state(_UP5, 150.0) == "impulse_complete"


def test_complete_impulse_beats_partial():
    # Der komplette Impuls (6) hat Vorrang vor der Teil-Deutung der letzten 5.
    r = pipe._classify_structure(_UP5, 159.0)
    assert r["state"] == "impulse_complete"


# ---------------------------------------------------------------------------
# Struktur-Befund konsistent mit dem Long-Count (long_setup <-> Count vorhanden)
# ---------------------------------------------------------------------------
def test_structure_from_series_shape():
    # Fail-soft: zu wenig Daten -> Default-Dict, nie Exception.
    r = pipe._structure_from_series(["d0", "d1"], [10.0, 11.0])
    assert r["state"] == "no_structure"
    assert set(r) == {"state", "label", "invalidation_price", "direction"}


# ---------------------------------------------------------------------------
# Unberührtheit: structure ist REINE Watchlist-Diagnostik
# ---------------------------------------------------------------------------
import json  # noqa: E402

FIXED_TS = "2026-07-24T21:45:00Z"


def _report(monthly=None):
    return pipe.build_report(pipe.fetch_synthetic, FIXED_TS,
                             pipe.fetch_synthetic_weekly, monthly)


def test_market_candidates_have_no_structure():
    r = _report(pipe.fetch_synthetic_monthly)
    for mk in r["markets"].values():
        for c in mk["candidates"]:
            assert "structure" not in c        # Struktur-Befund NUR Watchlist


def test_markets_byte_identical_regardless_of_structure_field():
    # Der Struktur-Befund (Watchlist) darf die Märkte (Score/Ranking) nicht ändern.
    a = _report(None)
    b = _report(pipe.fetch_synthetic_monthly)
    assert json.dumps(a["markets"], sort_keys=True) == json.dumps(b["markets"], sort_keys=True)


def test_watchlist_entries_carry_structure_per_timeframe():
    e = pipe.build_watchlist_entry("AAPL", pipe.fetch_synthetic,
                                   pipe.fetch_synthetic_weekly, pipe.fetch_synthetic_monthly)
    assert set(e["structure"]) == {"day", "week", "month"}
    for tf in e["structure"].values():
        assert tf is None or set(tf) == {"state", "label", "invalidation_price", "direction"}
