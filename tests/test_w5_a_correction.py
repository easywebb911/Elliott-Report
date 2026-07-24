"""W5->A-Nachprüfung (Lit-Check-Punkt b) — reines Mess-Feld.

Bei gereiften end_of_w4-Treffern: setzt nach dem Episoden-Hoch die theorie-gemäße
Korrektur (>= 38,2 % Rücklauf der W5-Strecke P4->Hoch) innerhalb A_OBSERVE_DAYS
ein? Kein Score/Ranking/Reifungs-Einfluss; angehängtes Beobachtungsfenster.
"""
import json

import forward_collection as fc

NOW = "2026-07-22T00:00:00Z"


def _w4_rec(target_hit=1, matured=True, excluded=False, w4=True):
    """end_of_w4-Record (P4=100 aus chart_points[wave==4]). w4=False -> end_of_w2."""
    labels = [{"index": j, "wave": j} for j in range(5 if w4 else 3)]
    prices = [90.0, 110.0, 100.0, 115.0, 100.0] if w4 else [90.0, 110.0, 100.0]
    rec = {
        "ticker": "AAA", "first_seen_date": "s", "matured": matured,
        "count_wave_labels": labels,
        "chart_points": [{"index": j, "price": p} for j, p in enumerate(prices)],
        "target_hit": target_hit,
        "a_correction_observed": None, "a_retrace_pct": None, "a_observe_until": None,
    }
    if excluded:
        rec["pre_reached_target"] = True
    return rec


def _series(fwd, tail):
    """dates/closes so, dass first_seen "s" auf Index 0 zeigt; danach fwd (die
    Reifungs-10) + tail (weitere Tage fürs A-Fenster). entry_close irrelevant."""
    closes = [105.0] + list(fwd) + list(tail)
    dates = ["s"] + [f"d{i}" for i in range(len(closes) - 1)]
    return dates, closes


# W5 steigt auf Hoch 120 bei fwd-Index 3 (P4=100 -> W5-Strecke=20; 38,2 % -> 112,36).
_FWD = [108.0, 112.0, 116.0, 120.0, 119.0, 118.0, 117.0, 118.0, 119.0, 119.0]


# ---------------------------------------------------------------------------
# Konstruierte Kernfälle
# ---------------------------------------------------------------------------
def test_a_correction_observed_on_deep_retrace():
    # A-Fenster fällt auf 111 (Rücklauf 45 % > 38,2 %) -> beobachtet.
    dates, closes = _series(_FWD, [114.0, 111.0, 113.0, 116.0, 118.0])
    rec = _w4_rec()
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert rec["a_correction_observed"] is True
    assert rec["a_retrace_pct"] == 45.0            # (120-111)/20*100


def test_a_correction_false_on_shallow_retrace():
    # A-Fenster (voll, 10 Tage) fällt nur auf 116 (Rücklauf 20 %) -> nicht beobachtet.
    dates, closes = _series(_FWD, [118.0, 117.0, 116.0, 117.0, 118.0])
    rec = _w4_rec()
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert rec["a_correction_observed"] is False
    assert rec["a_retrace_pct"] == 20.0            # (120-116)/20*100


def test_a_correction_open_when_window_incomplete():
    # Kaum Folgetage nach dem Hoch -> A-Fenster noch offen -> None.
    dates, closes = _series(_FWD, [118.0])         # nur 1 Extra-Tag
    rec = _w4_rec()
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert rec["a_correction_observed"] is None     # offen, kein Trigger, nicht voll


def test_no_measurement_for_end_of_w2():
    dates, closes = _series(_FWD, [110.0] * 6)
    rec = _w4_rec(w4=False)                          # end_of_w2
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert rec["a_correction_observed"] is None
    assert rec["a_retrace_pct"] is None


def test_no_measurement_for_pre_reached():
    dates, closes = _series(_FWD, [111.0] * 6)       # würde sonst triggern
    rec = _w4_rec(excluded=True)                     # PRU-Guard: kein W5->A
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert rec["a_correction_observed"] is None
    assert rec["a_retrace_pct"] is None


def test_no_measurement_without_target_hit():
    dates, closes = _series(_FWD, [111.0] * 6)
    rec = _w4_rec(target_hit=0)
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert rec["a_correction_observed"] is None


def test_no_measurement_when_not_matured():
    dates, closes = _series(_FWD, [111.0] * 6)
    rec = _w4_rec(matured=False)
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert rec["a_correction_observed"] is None


# ---------------------------------------------------------------------------
# Nur die a_*-Felder werden berührt; Idempotenz
# ---------------------------------------------------------------------------
def test_only_a_fields_touched():
    dates, closes = _series(_FWD, [114.0, 111.0, 113.0, 116.0, 118.0])
    rec = _w4_rec()
    before = {k: v for k, v in rec.items() if not k.startswith("a_")}
    fc.observe_a_correction(rec, dates, closes, NOW)
    after = {k: v for k, v in rec.items() if not k.startswith("a_")}
    assert before == after                          # target_hit/matured/... unverändert


def test_a_correction_idempotent():
    dates, closes = _series(_FWD, [114.0, 111.0, 113.0, 116.0, 118.0])
    rec = _w4_rec()
    fc.observe_a_correction(rec, dates, closes, NOW)
    snap = json.dumps({k: rec[k] for k in ("a_correction_observed", "a_retrace_pct")},
                      sort_keys=True)
    fc.observe_a_correction(rec, dates, closes, NOW)
    assert json.dumps({k: rec[k] for k in ("a_correction_observed", "a_retrace_pct")},
                      sort_keys=True) == snap


# ---------------------------------------------------------------------------
# Integration: bestehende Reifung byte-identisch (mature_record unberührt)
# ---------------------------------------------------------------------------
def test_existing_maturation_byte_identical():
    # Ein Record wird gereift; die Standard-Reifungs-Zahlen dürfen sich durch den
    # W5->A-Durchgang NICHT ändern.
    rec = fc._new_record(
        {"ticker": "AAA", "close": 100.0, "score_heuristic": 70.0,
         "target_zone": {"low": 120.0, "high": 130.0},
         "target_zone_extended": {"low": 140.0, "high": 150.0},
         "invalidation_price": 90.0, "direction": "long",
         "count_wave_labels": [{"index": j, "wave": j} for j in range(5)],
         "chart_points": [{"index": j, "price": p} for j, p in
                          enumerate([90.0, 110.0, 100.0, 115.0, 100.0])]},
        "US", "s", "risk_on", "2026-07-22", NOW)
    dates = ["s"] + [f"d{i}" for i in range(15)]
    closes = [100.0] + _FWD + [114.0, 111.0, 113.0, 116.0, 118.0]
    fc.mature_record(rec, dates, closes, NOW)
    std_before = {k: rec[k] for k in ("target_hit", "ext_hit", "invalidated",
                                      "matured", "max_gain_10d", "max_drawdown_10d",
                                      "r_multiple", "bars_elapsed")}
    fc.observe_a_correction(rec, dates, closes, NOW)
    std_after = {k: rec[k] for k in ("target_hit", "ext_hit", "invalidated",
                                     "matured", "max_gain_10d", "max_drawdown_10d",
                                     "r_multiple", "bars_elapsed")}
    assert std_before == std_after                  # Reifungs-Zahlen byte-identisch
    assert rec["a_correction_observed"] is True      # aber A-Messung gesetzt
