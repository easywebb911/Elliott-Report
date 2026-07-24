"""Konfluenz-Marken (Lit-Check-Punkt a) — REINE Anzeige/Messung.

Crowd-Marken (52-Wochen-Hoch, 200-Tage-Linie, nächste runde Zahl) vs. Zielzone/
Invalidierung. Kein Score-/Ranking-Einfluss (bewiesen). Point-in-time eingefroren
in der Forward-Sammlung. Aus den bereits geladenen Tagesschlusskursen — keine
neuen Fetches.
"""
import json

import config
import elliott_pipeline as pipe
import forward_collection as fc

TS = "2024-01-01T00:00:00Z"
NOW = "2026-07-22T00:00:00Z"


# ---------------------------------------------------------------------------
# Rundzahl-Stufen je Preisklasse (Beispiele über Preisklassen)
# ---------------------------------------------------------------------------
def test_round_step_by_price_class():
    assert pipe._round_step(3.5) == 1.0        # < 20  (Penny/.DE-Cent)
    assert pipe._round_step(19.99) == 1.0
    assert pipe._round_step(20.0) == 5.0       # 20–100 (2-stellig US/.DE)
    assert pipe._round_step(55.0) == 5.0
    assert pipe._round_step(100.0) == 10.0     # 100–500 (3-stellig)
    assert pipe._round_step(410.0) == 10.0
    assert pipe._round_step(500.0) == 50.0     # >= 500
    assert pipe._round_step(593.0) == 50.0


def test_nearest_round_examples():
    assert pipe._nearest_round(3.5) in (3.0, 4.0)   # step 1 -> banker's rounding
    assert pipe._nearest_round(55.05) == 55.0       # step 5
    assert pipe._nearest_round(410.05) == 410.0     # step 10
    assert pipe._nearest_round(593.08) == 600.0     # step 50


# ---------------------------------------------------------------------------
# compute_confluence — die drei Marken
# ---------------------------------------------------------------------------
def test_confluence_200d_in_band():
    # SMA200 landet im Band, 52w-Hoch außerhalb; nicht-runde Kanten/Invalidierung.
    closes = [124.0] * 200 + [135.0] * 6      # SMA(last200) ~124.3 in [121.3,128.7]
    conf = pipe.compute_confluence(
        closes, {"low": 121.3, "high": 128.7}, invalidation=91.4)
    assert "200d" in conf["target"]           # 200d-Linie in der Zielzone
    assert "52w_high" not in conf["target"]   # 135 außerhalb des Bandes
    assert "round" not in conf["target"]      # 121.3/128.7 nicht rund genug (±1%)


def test_confluence_52w_high_in_band_and_near_invalidation():
    closes = [100.0] * 50 + [125.0]           # 52w-Hoch = 125
    # Band um 125 -> 52w in target; Invalidierung ~125 -> 52w near inval.
    conf = pipe.compute_confluence(
        closes, {"low": 121.3, "high": 128.7}, invalidation=125.4)
    assert "52w_high" in conf["target"]
    assert "52w_high" in conf["invalidation"]


def test_confluence_round_at_zone_edge():
    # Zonen-Unterkante 120.4 liegt innerhalb ±1% der runden 120 (step 10).
    conf = pipe.compute_confluence(
        [110.0] * 10, {"low": 120.4, "high": 137.9}, invalidation=95.0)
    assert "round" in conf["target"]          # Kante auf runder Zahl
    assert "round" in conf["invalidation"]    # 95 ist rund (step 5)


def test_confluence_round_not_flagged_when_edge_off_round():
    # Kante 124.0 ist NICHT innerhalb ±1% einer runden Zahl (120/130, step 10).
    conf = pipe.compute_confluence(
        [110.0] * 10, {"low": 124.0, "high": 134.0}, invalidation=87.3)
    assert "round" not in conf["target"]
    assert "round" not in conf["invalidation"]


def test_confluence_empty_when_far_off():
    conf = pipe.compute_confluence(
        [50.0] * 10, {"low": 124.0, "high": 134.0}, invalidation=87.3)
    assert conf == {"target": [], "invalidation": []}


def test_confluence_no_200d_when_history_short():
    conf = pipe.compute_confluence(
        [100.0] * 199, {"low": 99.5, "high": 100.5}, invalidation=50.0)
    assert "200d" not in conf["target"]       # < 200 Bars -> kein 200d-Wert
    assert "52w_high" in conf["target"]       # 52w-Hoch (=100) im Band


def test_confluence_failsoft_empty_inputs():
    assert pipe.compute_confluence([], {"low": 1, "high": 2}, 1) == {"target": [], "invalidation": []}
    assert pipe.compute_confluence([1.0], None, 1) == {"target": [], "invalidation": []}


# ---------------------------------------------------------------------------
# Point-in-time-Einfrieren in der Forward-Sammlung
# ---------------------------------------------------------------------------
def _entry(ticker, confluence):
    return {
        "ticker": ticker, "close": 100.0, "score_heuristic": 70.0,
        "target_zone": {"low": 120.0, "high": 130.0},
        "target_zone_extended": {"low": 140.0, "high": 150.0},
        "invalidation_price": 90.0, "direction": "long",
        "confluence": confluence,
    }


def test_confluence_frozen_point_in_time():
    conf = {"target": ["200d", "round"], "invalidation": ["round"]}
    rec = fc._new_record(_entry("AAPL", conf), "US", "s", "risk_on", "2026-07-22", NOW)
    assert rec["confluence"] == conf
    frozen = json.dumps(rec["confluence"], sort_keys=True)
    # Reifung (mehrere Läufe) ändert die eingefrorene Konfluenz NIE.
    dates = ["s"] + [f"d{i}" for i in range(5)]
    closes = [100.0, 101, 102, 103, 104, 105]
    fc.mature_record(rec, dates, closes, NOW)
    assert json.dumps(rec["confluence"], sort_keys=True) == frozen


def test_confluence_default_when_missing_in_entry():
    e = _entry("X", None); del e["confluence"]
    rec = fc._new_record(e, "US", "s", "risk_on", "2026-07-22", NOW)
    assert rec["confluence"] == {"target": [], "invalidation": []}


# ---------------------------------------------------------------------------
# Grenzen: KEIN Score-/Ranking-Einfluss (bewiesen)
# ---------------------------------------------------------------------------
def test_confluence_does_not_affect_score_or_order(monkeypatch):
    base = pipe.build_report(pipe.fetch_synthetic, TS)
    order_base = [(c["ticker"], c["score_heuristic"])
                  for c in base["markets"]["US"]["candidates"]]
    # Konfluenz auf etwas völlig anderes zwingen -> Score/Reihenfolge UNVERÄNDERT.
    monkeypatch.setattr(pipe, "compute_confluence",
                        lambda *a, **k: {"target": ["200d", "round", "52w_high"],
                                         "invalidation": ["round"]})
    other = pipe.build_report(pipe.fetch_synthetic, TS)
    order_other = [(c["ticker"], c["score_heuristic"])
                   for c in other["markets"]["US"]["candidates"]]
    assert order_base == order_other          # Konfluenz beeinflusst Score/Ranking NICHT
    assert other["markets"]["US"]["candidates"][0]["confluence"]["target"]  # Feld gesetzt


def test_market_candidates_have_confluence_field():
    r = pipe.build_report(pipe.fetch_synthetic, TS)
    for mk in r["markets"].values():
        for c in mk["candidates"]:
            assert set(c["confluence"].keys()) == {"target", "invalidation"}


def test_watchlist_entry_has_confluence():
    e = pipe.build_watchlist_entry("AAPL", pipe.fetch_synthetic,
                                   pipe.fetch_synthetic_weekly)
    assert e["wl_status"] == "setup"
    assert "confluence" in e and set(e["confluence"]) == {"target", "invalidation"}
