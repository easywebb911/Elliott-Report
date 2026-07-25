"""Messfelder v1 (Lit-Check P2) — Volumen-Profil (A), Alternation (B),
W5-Momentum-Divergenz (C). REINE MESSUNG, additiv, point-in-time.

Belegt an konstruierten Fällen: die Ziel-Mechanik je Feld (W3-Volumen stark/
schwach; Alternation ja/nein/null bei end_of_w2; Divergenz true/false/null),
das Einfrieren bei Anlage, die Idempotenz und dass die BESTEHENDE Reifung
byte-identisch bleibt (die C-Messung berührt nur w5_*-Felder).
"""
import copy

import pytest

import elliott_pipeline as pipe
import forward_collection as fc
from zigzag import Pivot

pd = pytest.importorskip("pandas")


# ---------------------------------------------------------------------------
# (A) Volumen-Profil — build_candidate / _volume_profile
# ---------------------------------------------------------------------------
def _piv5():
    # P0..P4 mit index (zeigt auf volumes) + Preisen (end_of_w4).
    return [Pivot(0, 100, "L"), Pivot(5, 120, "H"), Pivot(9, 110, "L"),
            Pivot(15, 150, "H"), Pivot(19, 138, "L")]


def test_vol_profile_w3_strong_vs_weak():
    P = _piv5()
    vol = [1000.0] * 20
    for i in range(0, 6):
        vol[i] = 2000.0                 # W1
    for i in range(9, 16):
        vol[i] = 5000.0                 # W3 stark
    prof = pipe._volume_profile(P, "end_of_w4", vol)
    assert set(prof["vol_mean"]) == {"w1", "w2", "w3", "w4"}
    assert prof["vol_ratio_w3_w1"] > 1               # W3 > W1
    # W3 schwach -> Ratio < 1 (Chip-Auslöser)
    vol2 = [1000.0] * 20
    for i in range(0, 6):
        vol2[i] = 5000.0
    for i in range(9, 16):
        vol2[i] = 1500.0
    assert pipe._volume_profile(P, "end_of_w4", vol2)["vol_ratio_w3_w1"] < 1


def test_vol_profile_end_of_w2_only_w1_w2():
    P = [Pivot(0, 100, "L"), Pivot(5, 120, "H"), Pivot(9, 110, "L")]
    prof = pipe._volume_profile(P, "end_of_w2", [1000.0] * 20)
    assert set(prof["vol_mean"]) == {"w1", "w2"}
    assert prof["vol_ratio_w2_w1"] is not None
    assert prof["vol_ratio_w3_w1"] is None and prof["vol_ratio_w4_w3"] is None


def test_vol_profile_guards():
    P = _piv5()
    # kein Volumen -> alles null
    empty = pipe._volume_profile(P, "end_of_w4", None)
    assert empty["vol_mean"] == {} and empty["vol_ratio_w3_w1"] is None
    # 0-Volumen-Segment -> betroffenes Feld null (Division-Guard)
    assert pipe._volume_profile(P, "end_of_w4", [0.0] * 20)["vol_ratio_w3_w1"] is None
    # Index außerhalb der Volumen-Länge -> null (kein Absturz)
    assert pipe._volume_profile(P, "end_of_w4", [1000.0] * 3)["vol_mean"].get("w4") is None


def test_build_candidate_attaches_vol_fields_and_only_those():
    out = pipe.fetch_synthetic("AMAT")
    entry, reason, _ = pipe.build_candidate("AMAT", out.data[0], out.data[1],
                                            volumes=out.volumes)
    assert entry is not None and reason is None
    for k in ("vol_profile", "vol_ratio_w3_w1", "vol_ratio_w4_w3", "vol_ratio_w2_w1"):
        assert k in entry
    assert entry["vol_profile"], "Profil sollte gefüllt sein (Synthetic hat Volumen)"
    # Ohne Volumen -> Felder vorhanden aber null/leer (fail-soft, kein Absturz).
    e2, _, _ = pipe.build_candidate("AMAT", out.data[0], out.data[1], volumes=None)
    assert e2["vol_profile"] == {} and e2["vol_ratio_w2_w1"] is None


# ---------------------------------------------------------------------------
# Volume durch den Parse-Pfad (Mock spiegelt echte yfinance-Form INKL. Volume)
# ---------------------------------------------------------------------------
def _mk_df(n=120, with_volume=True, multiindex=True):
    closes = [100.0 + i for i in range(n)]
    rows, cols = [], ["Close", "High", "Low", "Open"] + (["Volume"] if with_volume else [])
    for i in range(n):
        r = [closes[i], closes[i] + 1, closes[i] - 1, closes[i]]
        if with_volume:
            r.append(1000 + i)
        rows.append(r)
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    if multiindex:
        cols = pd.MultiIndex.from_tuples([(c, "AAPL") for c in cols])
    return pd.DataFrame(rows, index=idx, columns=cols)


def test_parse_extracts_aligned_volume():
    out = pipe.parse_download_df(_mk_df())
    assert out.volumes is not None
    assert len(out.volumes) == len(out.data[1])          # aligned zu closes
    assert out.volumes[0] == 1000.0 and out.volumes[5] == 1005.0


def test_parse_no_volume_column_failsoft():
    out = pipe.parse_download_df(_mk_df(with_volume=False))
    assert out.data is not None and out.volumes is None    # fail-soft None


def test_parse_volume_nan_to_zero():
    import math
    df = _mk_df()
    df.iloc[7, df.columns.get_loc(("Volume", "AAPL"))] = math.nan
    out = pipe.parse_download_df(df)
    assert out.volumes[7] == 0.0


# ---------------------------------------------------------------------------
# (B) Alternation — _alternation_fields (aus eingefrorenen Pivots)
# ---------------------------------------------------------------------------
def _cps_labels(pivs):
    """chart_points (12 lang, vorne gepolstert) + count_wave_labels für P0..P4."""
    pad = [{"index": i, "price": 50.0 + i, "date": f"2025-01-{i + 1:02d}", "kind": "L"}
           for i in range(7)]
    cps = pad + [{"index": ix, "price": pr, "date": d, "kind": "H"} for ix, pr, d in pivs]
    ncp = len(cps)
    labels = [{"index": ncp - 5 + j, "wave": j} for j in range(5)]
    return cps, labels


def test_alternation_sharp_vs_flat_true():
    # scharfe W2 (83 %, 2 Bars) vs. flache W4 (18 %, 15 Bars) -> alterniert
    pivs = [(20, 100, "2025-02-01"), (25, 130, "2025-02-06"), (27, 105, "2025-02-08"),
            (35, 160, "2025-02-16"), (50, 150, "2025-03-03")]
    b = fc._alternation_fields(*_cps_labels(pivs))
    assert b["w2_retrace_pct"] > 80 and b["w4_retrace_pct"] < 20
    assert b["w2_bars"] == 2 and b["w4_bars"] == 15
    assert b["alternation_observed"] is True


def test_alternation_similar_false():
    pivs = [(20, 100, "a"), (25, 130, "b"), (28, 115, "c"), (33, 160, "d"), (37, 145, "e")]
    b = fc._alternation_fields(*_cps_labels(pivs))
    assert b["alternation_observed"] is False


def test_alternation_null_for_end_of_w2():
    cps, _ = _cps_labels([(20, 100, "a"), (25, 130, "b"), (28, 115, "c"),
                          (33, 160, "d"), (37, 145, "e")])
    labels_w2 = [{"index": 9, "wave": 0}, {"index": 10, "wave": 1}, {"index": 11, "wave": 2}]
    b = fc._alternation_fields(cps, labels_w2)
    assert all(v is None for v in b.values())


# ---------------------------------------------------------------------------
# (C) W5-Momentum-Divergenz — observe_w5_divergence
# ---------------------------------------------------------------------------
def _c_series():
    dates = [f"2025-04-{d:02d}" for d in range(1, 31)] + [f"2025-05-{d:02d}" for d in range(1, 20)]
    closes = [100 + i * 3 for i in range(20)]            # steil bis idx19 (starkes ROC)
    closes += [159 - (i % 2) for i in range(20, 35)]     # seitwärts
    closes += [160 + 0.2 * i for i in range(35, 49)]     # höherer, flacher Hochpunkt
    return dates, closes


def _c_rec(dates, closes, fs_idx=33, w3_idx=19, w4_idx=34, target_hit=1, matured=True):
    return {"matured": matured, "target_hit": target_hit, "first_seen_date": dates[fs_idx],
            "chart_points": [{"index": w3_idx, "price": closes[w3_idx], "date": dates[w3_idx], "kind": "H"},
                             {"index": w4_idx, "price": closes[w4_idx], "date": dates[w4_idx], "kind": "L"}],
            "count_wave_labels": [{"index": 0, "wave": 3}, {"index": 1, "wave": 4}],
            "pre_reached_target": False, "pre_reached_ext": False, "invalidated": 0,
            "w5_momentum_divergence": None, "w5_mom_w3": None, "w5_mom_high": None}


def test_divergence_true():
    dates, closes = _c_series()
    r = _c_rec(dates, closes)
    fc.observe_w5_divergence(r, dates, closes, "now")
    assert r["w5_mom_w3"] is not None and r["w5_mom_high"] is not None
    assert r["w5_mom_high"] < r["w5_mom_w3"]
    assert r["w5_momentum_divergence"] is True


def test_divergence_false_when_no_higher_high():
    dates, closes = _c_series()
    r = _c_rec(dates, closes)
    r["chart_points"][0]["price"] = 99999.0            # W3-Hoch künstlich unerreichbar
    fc.observe_w5_divergence(r, dates, closes, "now")
    assert r["w5_momentum_divergence"] is False


def test_divergence_null_cases():
    dates, closes = _c_series()
    # nicht end_of_w4
    r = _c_rec(dates, closes)
    r["count_wave_labels"] = [{"index": 0, "wave": 2}]
    fc.observe_w5_divergence(r, dates, closes, "now")
    assert r["w5_momentum_divergence"] is None
    # kein target_hit
    r2 = _c_rec(dates, closes, target_hit=0)
    fc.observe_w5_divergence(r2, dates, closes, "now")
    assert r2["w5_momentum_divergence"] is None
    # zu wenig Vorlauf für ROC (W3 sehr früh)
    r3 = _c_rec(dates, closes, w3_idx=5)
    fc.observe_w5_divergence(r3, dates, closes, "now")
    assert r3["w5_momentum_divergence"] is None and r3["w5_mom_w3"] is None


# ---------------------------------------------------------------------------
# Einfrieren + Idempotenz + Reifung byte-identisch
# ---------------------------------------------------------------------------
def _entry_w4():
    cps, labels = _cps_labels([(20, 100, "2025-02-01"), (25, 130, "2025-02-06"),
                               (27, 105, "2025-02-08"), (35, 160, "2025-02-16"),
                               (50, 150, "2025-03-03")])
    return {
        "ticker": "TST", "close": 150.0, "score_heuristic": 70.0,
        "target_zone": {"low": 170.0, "high": 180.0},
        "target_zone_extended": {"low": 190.0, "high": 200.0},
        "invalidation_price": 95.0, "direction": "long", "count_label": "W4",
        "chart_points": cps, "count_wave_labels": labels,
        "vol_profile": {"w1": 2000000, "w2": 1500000, "w3": 1400000, "w4": 1200000},
        "vol_ratio_w3_w1": 0.7, "vol_ratio_w4_w3": 0.86, "vol_ratio_w2_w1": None,
    }


def test_new_record_freezes_vol_and_computes_alternation():
    rec = fc._new_record(_entry_w4(), "US", "2025-03-03", "risk_on", "2025-03-03", "now")
    # (A) eingefroren aus dem Kandidaten
    assert rec["vol_ratio_w3_w1"] == 0.7 and rec["vol_profile"]["w3"] == 1400000
    # (B) aus den eingefrorenen Pivots berechnet
    assert rec["w2_retrace_pct"] is not None and rec["alternation_observed"] is True
    # (C) noch unbestimmt (wird erst bei Reifung gesetzt)
    assert rec["w5_momentum_divergence"] is None


def test_new_record_end_of_w2_alternation_null():
    e = _entry_w4()
    e["count_wave_labels"] = [{"index": 9, "wave": 0}, {"index": 10, "wave": 1},
                              {"index": 11, "wave": 2}]
    rec = fc._new_record(e, "US", "2025-03-03", "risk_on", "2025-03-03", "now")
    assert rec["w2_retrace_pct"] is None and rec["alternation_observed"] is None


MATURE_KEYS = ("target_hit", "ext_hit", "invalidated", "matured", "bars_elapsed",
               "max_gain_10d", "max_drawdown_10d", "r_multiple", "price_path",
               "pre_reached_target", "pre_reached_ext")


def test_appended_measurement_steps_leave_maturation_byte_identical():
    # first_seen INTERIOR (d0), steigende Kurse -> target_hit=1, matured.
    dates = [f"2025-06-{d:02d}" for d in range(2, 20)]
    closes = [100.0 + i for i in range(len(dates))]      # steigt -> Ziel getroffen
    e = _entry_w4()
    e["close"] = 100.0                               # < target-low -> kein PRU-Guard
    e["target_zone"] = {"low": 105.0, "high": 108.0}
    e["target_zone_extended"] = {"low": 110.0, "high": 112.0}
    e["invalidation_price"] = 95.0
    # W3-Hoch (P3) auf ein reales Datum/Kurs legen, damit C messbar ist.
    e["chart_points"][10]["date"] = dates[0]
    rec = fc._new_record(e, "US", dates[0], "risk_on", dates[0], "now")

    fc.mature_record(rec, dates, closes, "now")
    assert rec["target_hit"] == 1 and rec["matured"] is True
    snap = {k: copy.deepcopy(rec[k]) for k in MATURE_KEYS}

    # Angehängte Messschritte (A/B sind schon gefroren; C + W5->A laufen jetzt).
    fc.observe_a_correction(rec, dates, closes, "now")
    fc.observe_w5_divergence(rec, dates, closes, "now")
    for k in MATURE_KEYS:
        assert rec[k] == snap[k], f"Reifungsfeld {k} durch Messschritt verändert"

    # Idempotenz: erneut -> Reifungsfelder UND Messfelder stabil.
    div1, mom1 = rec["w5_momentum_divergence"], rec["w5_mom_w3"]
    fc.observe_w5_divergence(rec, dates, closes, "now")
    for k in MATURE_KEYS:
        assert rec[k] == snap[k]
    assert rec["w5_momentum_divergence"] == div1 and rec["w5_mom_w3"] == mom1


def test_update_collection_end_to_end_carries_measurement_fields():
    # Voller Sammel-Durchlauf: Record trägt die neuen Felder (fail-soft, kein Crash).
    dates = [f"2025-07-{d:02d}" for d in range(1, 15)]
    closes = [100.0 + i for i in range(len(dates))]
    entry = _entry_w4()
    entry["ticker"] = "E2E"
    report = {"markets": {"US": {"candidates": [entry]}}}
    coll = {"schema_version": 1, "last_run_date": None, "records": []}
    fc.update_forward_collection(coll, report, {"E2E": (dates, closes)},
                                 {"US": "risk_on"}, dates[-1], "now")
    rec = coll["records"][0]
    for k in ("vol_profile", "vol_ratio_w3_w1", "w2_retrace_pct", "w4_bars",
              "alternation_observed", "w5_momentum_divergence"):
        assert k in rec
    assert rec["vol_ratio_w3_w1"] == 0.7           # (A) eingefroren aus dem Kandidaten
