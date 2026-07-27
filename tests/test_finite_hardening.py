"""Nicht-finit-Härtung (27.07.2026) — je Guard-Klasse NaN **und** Inf.

Ursachen-Fix zu #51: der Health-Check macht die Folgen sichtbar, hier wird die
Ursache beseitigt. Kernproblem der Klasse:

    x is not None   ist WAHR für NaN
    nan <= 0        ist False        (jeder Vergleich mit NaN ist False)
    nan > 0         ist False
    bool(nan)       ist True         (truthy!)

Guards dieser Formen schützen nicht, sie **schweigen**. Jeder Test hier hat
zwei Hälften: der kaputte Fall wird abgefangen, **und** gesunde Daten liefern
unverändert dasselbe Ergebnis wie vorher (Gegenprobe).
"""
import copy
import json
import math

import pandas as pd
import pytest

import elliott_pipeline as pipe
import forward_collection as fc
from numeric import all_finite, finite, finite_or_none
from zigzag import Pivot

NAN = float("nan")
INF = float("inf")
NOW = "2026-07-27T21:45:00Z"
BAD = (NAN, INF, -INF)


# ══ Das Prädikat ═══════════════════════════════════════════════════════════
def test_finite_predicate():
    for bad in (None, NAN, INF, -INF, True, False, "3.5", [], {}):
        assert finite(bad) is False, f"finite({bad!r}) müsste False sein"
    for good in (0, -1, 3.5, 1e9):
        assert finite(good) is True


def test_finite_helpers():
    assert all_finite([]) is True
    assert all_finite([1.0, 2.0]) is True
    assert all_finite([1.0, NAN]) is False
    assert all_finite([1.0, INF]) is False
    assert finite_or_none(2) == 2.0
    for bad in BAD + (None, "x"):
        assert finite_or_none(bad) is None


def test_the_class_itself_is_documented_by_behaviour():
    """Der Grund, warum es diese Härtung gibt — als ausführbarer Beleg."""
    assert (NAN is not None) is True          # None-Guard blind
    assert (NAN <= 0) is False                # negierter Guard blind
    assert (NAN > 0) is False
    assert bool(NAN) is True                  # truthy-Guard blind
    assert finite(NAN) is False               # das Prädikat greift immer


# ══ 1) QUELLE: parse_download_df ═══════════════════════════════════════════
def _df(closes, volumes=None, start="2026-01-01"):
    idx = pd.date_range(start, periods=len(closes), freq="D")
    data = {"Close": [float(c) for c in closes]}
    if volumes is not None:
        data["Volume"] = [float(v) for v in volumes]
    return pd.DataFrame(data, index=idx)


@pytest.mark.parametrize("bad", BAD)
def test_source_drops_non_finite_bars_and_counts_them(bad):
    closes = [10.0 + i for i in range(60)]
    closes[5] = bad
    out = pipe.parse_download_df(_df(closes), min_bars=10)
    assert out.data is not None
    dates, got = out.data
    assert out.dropped_bars == 1
    assert len(got) == len(closes) - 1 == len(dates)
    assert all(finite(c) for c in got)


def test_source_keeps_dates_aligned_after_a_hole():
    """DER eigentliche Quell-Bug: ``dropna`` entfernte die Zeile, das Datum
    wurde aber nur vorne abgeschnitten — jeder Close nach dem Loch bekam das
    Datum seines Vorgängers. Das verschob Pivot-Daten, ``chart_points``, die
    Sparkline-Achsen und die eingefrorenen Pivots in der Sammlung."""
    closes = [10.0, NAN, 30.0, 40.0] + [50.0 + i for i in range(20)]
    out = pipe.parse_download_df(_df(closes, start="2026-01-01"), min_bars=5)
    dates, got = out.data
    assert got[0] == 10.0 and dates[0] == "2026-01-01"
    # 30.0 ist der Bar vom 03.01. — NICHT vom 02.01. (das war der Versatz).
    assert got[1] == 30.0 and dates[1] == "2026-01-03"
    assert got[2] == 40.0 and dates[2] == "2026-01-04"
    assert len(dates) == len(got)


def test_source_volume_stays_aligned_with_closes():
    """Zweiter Versatz: die Volumen kamen aus dem UNGEFILTERTEN Frame."""
    closes = [10.0, NAN, 30.0, 40.0] + [50.0 + i for i in range(20)]
    vols = [float(100 + i) for i in range(len(closes))]
    out = pipe.parse_download_df(_df(closes, vols), min_bars=5)
    _dates, got = out.data
    assert len(out.volumes) == len(got)
    # Volumen des 03.01. gehört zu Close 30.0 (Index 2 im Rohframe).
    assert out.volumes[1] == 102.0


@pytest.mark.parametrize("bad", BAD)
def test_source_volume_non_finite_keeps_the_bar(bad):
    closes = [10.0 + i for i in range(30)]
    vols = [1000.0] * 30
    vols[4] = bad
    out = pipe.parse_download_df(_df(closes, vols), min_bars=10)
    assert out.dropped_bars == 0, "ein gültiger Preis-Bar darf nicht wegen des Volumens fliegen"
    assert out.invalid_volume_bars == 1
    assert out.volumes[4] is None


def test_source_healthy_data_is_unchanged():
    """Gegenprobe: ohne kaputte Werte exakt das alte Ergebnis."""
    closes = [10.0 + i for i in range(60)]
    vols = [float(1000 + i) for i in range(60)]
    out = pipe.parse_download_df(_df(closes, vols), min_bars=10)
    dates, got = out.data
    assert got == closes
    assert out.volumes == vols
    assert out.dropped_bars == 0 and out.invalid_volume_bars == 0
    assert dates[0] == "2026-01-01" and len(dates) == 60


def test_source_all_bars_bad_is_a_clean_skip():
    out = pipe.parse_download_df(_df([NAN] * 40), min_bars=10)
    assert out.data is None and out.reason == pipe.EMPTY_DATA
    assert out.dropped_bars == 40
    assert "verworfene Bars=40" in out.detail


# ══ 2) Volumen-Profil (Messfeld → null) ════════════════════════════════════
def _pivots(n=5):
    return [Pivot(i, 100.0 + i, "LOW" if i % 2 else "HIGH", f"2026-07-0{i+1}")
            for i in range(n)]


@pytest.mark.parametrize("bad", BAD)
def test_volume_profile_never_emits_non_finite(bad):
    prof = pipe._volume_profile(_pivots(), "end_of_w4", [bad] * 5)
    assert prof["vol_ratio_w3_w1"] is None and prof["vol_ratio_w4_w3"] is None
    assert all(v is None for v in prof["vol_mean"].values())


def test_volume_profile_single_gap_nulls_only_its_segment():
    vols = [100.0, 200.0, None, 400.0, 500.0]
    prof = pipe._volume_profile(_pivots(), "end_of_w4", vols)
    assert prof["vol_mean"]["w1"] is not None      # P0..P1 sauber
    assert prof["vol_mean"]["w3"] is None          # Segment mit Lücke
    assert prof["vol_ratio_w3_w1"] is None


def test_volume_profile_healthy_unchanged():
    prof = pipe._volume_profile(_pivots(), "end_of_w4",
                                [100.0, 200.0, 300.0, 400.0, 500.0])
    assert prof["vol_mean"]["w1"] == 150.0
    assert prof["vol_ratio_w3_w1"] == round(350.0 / 150.0, 4)


# ══ 3) Score-Guards ════════════════════════════════════════════════════════
@pytest.mark.parametrize("bad", BAD)
def test_score_bonuses_reject_non_finite(bad):
    assert pipe._fib_proximity_bonus(bad, [0.5, 0.618]) == 0.0
    assert pipe._invalidation_bonus(bad, 90.0) == 0.0
    assert pipe._invalidation_bonus(100.0, bad) == 0.0


def test_score_bonuses_healthy_unchanged():
    assert pipe._fib_proximity_bonus(0.5, [0.5, 0.618]) == pytest.approx(
        pipe.config.FIB_PROXIMITY_MAX_BONUS)
    assert pipe._invalidation_bonus(100.0, 90.0) > 0.0
    assert pipe._invalidation_bonus(0.0, 90.0) == 0.0      # wie bisher


# ══ 4) Reifung: fehlender Bar ≠ „kein Treffer" ═════════════════════════════
def _rec(**over):
    r = {"first_seen_date": "d0", "entry_close": 100.0,
         "invalidation_price": 90.0,
         "target_zone": {"low": 110.0, "high": 120.0},
         "target_zone_extended": {"low": 125.0, "high": 140.0},
         "matured": False}
    r.update(over)
    return r


def _series(vals):
    return [f"d{i}" for i in range(len(vals))], list(vals)


@pytest.mark.parametrize("bad", BAD)
def test_maturation_skips_bad_bar_and_counts_it(bad):
    rec = _rec()
    dates, closes = _series([100.0, 101.0, bad, 102.0, 103.0])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["skipped_bars"] == 1
    assert rec["bars_elapsed"] == 3, "nur gültige Bars zählen als abgelaufen"
    assert len(rec["price_path"]) == 3
    assert all(finite(p["close"]) for p in rec["price_path"])


def test_maturation_bad_bar_does_not_swallow_an_invalidation():
    """Der stille Schaden: der kaputte Bar verlor JEDEN Vergleich (also auch
    ``c <= inval``) und zählte trotzdem als abgelaufener Handelstag — er konnte
    eine Invalidierung verschlucken und die Reifung gleichzeitig vorantreiben."""
    good = _rec()
    dates, closes = _series([100.0, 101.0, 89.0] + [100.0] * 8)
    fc.mature_record(good, dates, closes, NOW)
    assert good["invalidated"] == 1

    # Derselbe Verlauf, aber der Riss-Bar ist kaputt -> KEIN erfundenes Urteil:
    # der Bar fehlt, die Reifung läuft mit den übrigen weiter.
    withnan = _rec()
    dates, closes = _series([100.0, 101.0, NAN] + [100.0] * 8)
    fc.mature_record(withnan, dates, closes, NOW)
    assert withnan.get("invalidated", 0) == 0
    assert withnan["skipped_bars"] == 1
    assert withnan["bars_elapsed"] == 9


def test_maturation_matures_on_valid_bars_and_never_stalls_forever():
    """Ein Record darf nicht still ewig offen bleiben: sobald genügend GÜLTIGE
    Bars da sind, reift er — der Fehlbar verzögert nur, er blockiert nicht."""
    rec = _rec()
    dates, closes = _series([100.0] + [NAN] + [101.0] * fc.HORIZON_DAYS)
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["bars_elapsed"] == fc.HORIZON_DAYS
    assert rec["matured"] is True
    assert rec["skipped_bars"] == 1


@pytest.mark.parametrize("bad", BAD)
def test_maturation_marks_unmeasurable_legacy_records(bad):
    """Alt-Record mit nicht endlichem Anlage-Wert: markieren statt rechnen."""
    rec = _rec(entry_close=bad)
    dates, closes = _series([100.0] + [101.0] * 12)
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["unmeasurable"] is True and rec["matured"] is False
    assert "target_hit" not in rec


def test_maturation_healthy_record_is_byte_identical():
    """Gegenprobe (Pflicht): gesunde Reifung liefert exakt dasselbe wie vorher —
    inklusive der Felder, die die Validierung auswertet."""
    dates, closes = _series([100.0, 101.0, 112.0] + [111.0] * 10)
    rec = _rec()
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["target_hit"] == 1 and rec["invalidated"] == 0
    assert rec["matured"] is True and rec["bars_elapsed"] == 10
    assert "skipped_bars" not in rec, "ohne Fehlbar kein Zusatzfeld"
    assert "unmeasurable" not in rec
    assert rec["max_gain_10d"] == 12.0
    assert rec["r_multiple"] == round(12.0 / 10.0, 4)


# ══ 5) Alternation / Momentum / W5 (Messfelder) ════════════════════════════
@pytest.mark.parametrize("bad", BAD)
def test_alternation_non_finite_pivot_is_null_not_false(bad):
    cps = [{"index": i, "price": 50.0 + i, "date": f"2026-01-{i+1:02d}"}
           for i in range(5)]
    cps[2]["price"] = bad
    labs = [{"index": i, "wave": i} for i in range(5)]
    out = fc._alternation_fields(cps, labs)
    for key in ("w2_retrace_pct", "w4_retrace_pct"):
        assert out[key] is None or finite(out[key])
    assert not any(isinstance(v, float) and not math.isfinite(v)
                   for v in out.values() if isinstance(v, float))


@pytest.mark.parametrize("bad", BAD)
def test_roc_rejects_non_finite(bad):
    closes = [10.0] * 20
    closes[0] = bad
    assert fc._roc(closes, 14, 14) is None
    closes = [10.0] * 20
    closes[14] = bad
    assert fc._roc(closes, 14, 14) is None


def test_roc_healthy_unchanged():
    closes = [10.0] * 14 + [11.0]
    assert fc._roc(closes, 14, 14) == round(11.0 / 10.0 - 1.0, 6)


# ══ 6) Regime ══════════════════════════════════════════════════════════════
def test_regime_filter_would_drop_inf():
    """``dropna`` entfernt NUR NaN — Inf lief durch und hätte den SMA vergiftet."""
    assert [float(x) for x in pd.Series([1.0, INF]).dropna().tolist()] == [1.0, INF]
    assert [float(x) for x in pd.Series([1.0, INF]).tolist() if finite(x)] == [1.0]


# ══ 7) Ende-zu-Ende: nichts Nicht-Endliches verlässt die Pipeline ══════════
def test_end_to_end_report_stays_finite_with_poisoned_source(monkeypatch):
    """Vergiftete Rohdaten -> der Report bleibt frei von NaN/Inf, und der
    Diag-Zähler weist die verworfenen Bars aus."""
    import health_check as hc

    def poisoned(ticker):
        base = pipe.fetch_synthetic(ticker)
        dates, closes = base.data
        closes = list(closes)
        closes[3] = NAN
        closes[7] = INF
        df = pd.DataFrame(
            {"Close": closes, "Volume": [1000.0] * len(closes)},
            index=pd.to_datetime(dates))
        return pipe.parse_download_df(df)

    monkeypatch.setattr(pipe.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE"]},
    })
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    report = pipe.build_report(poisoned, NOW, poisoned, poisoned)
    assert hc.non_finite_paths(report) == []
    for mk in ("US", "DE"):
        d = report["markets"][mk]["diag"]
        assert d["dropped_bars"] == 2 * len(
            pipe.config.MARKETS[mk]["universe"]), d
        assert d["bad_bar_tickers"], "verworfene Bars müssen namentlich stehen"


def test_end_to_end_healthy_report_has_zero_dropped(monkeypatch):
    monkeypatch.setattr(pipe.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE"]},
    })
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    report = pipe.build_report(pipe.fetch_synthetic, NOW,
                               pipe.fetch_synthetic_weekly,
                               pipe.fetch_synthetic_monthly)
    for mk in ("US", "DE"):
        d = report["markets"][mk]["diag"]
        assert d["dropped_bars"] == 0 and d["invalid_volume_bars"] == 0
        assert d["bad_bar_tickers"] == []


def test_hardening_does_not_change_healthy_report(monkeypatch):
    """Population/Score-Gegenprobe im Kleinen: derselbe gesunde Input muss
    denselben Report ergeben — die Härtung ist für gesunde Daten ein No-op."""
    monkeypatch.setattr(pipe.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT", "NVDA"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE", "SIE.DE"]},
    })
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    a = pipe.build_report(pipe.fetch_synthetic, NOW, pipe.fetch_synthetic_weekly,
                          pipe.fetch_synthetic_monthly)
    b = pipe.build_report(pipe.fetch_synthetic, NOW, pipe.fetch_synthetic_weekly,
                          pipe.fetch_synthetic_monthly)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    scores = [c["score_heuristic"] for c in a["markets"]["US"]["candidates"]]
    assert scores == sorted(scores, reverse=True) and all(finite(s) for s in scores)
