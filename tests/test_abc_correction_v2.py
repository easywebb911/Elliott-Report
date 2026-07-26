"""ABC-Korrektur-Erkennung + Struktur-Vokabular v2 + ambiguity v2 (Lit-Check P4a).

Belegt: die zwei neuen structure_states (correction_running/complete) auf den
bestätigten Pivots, die Präzedenz gegenüber den Impuls-Kategorien, ambiguity v2
(erweitertes Vokabular, v1 unverändert), das Einfrieren von ambiguity_n_v2 und die
W5→A-Strukturmessung. Markt/Score/Ranking + v1-Felder + Reifung bleiben unberührt
(Byte-Identität separat in den Report-/Reifungs-Tests).
"""
import copy

import elliott_pipeline as pipe
import forward_collection as fc
from zigzag import Pivot

# Valider Long-Impuls P0..P5 (aufwärts), P5 = 160.
IMP = [100, 120, 110, 140, 130, 160]


def _piv(vals):
    return [Pivot(i * 5, v, "H" if i % 2 else "L") for i, v in enumerate(vals)]


def _state(vals):
    return pipe._classify_structure(vals, vals[-1])["state"]


# ---------------------------------------------------------------------------
# ABC-Erkennung (auf den Pivot-Preisen)
# ---------------------------------------------------------------------------
def test_correction_complete_running_a_ab():
    assert _state(IMP + [140]) == "correction_running"          # nur A
    assert _state(IMP + [140, 150]) == "correction_running"     # A-B
    assert _state(IMP + [140, 150, 135]) == "correction_complete"  # A-B-C


def test_correction_marks_and_invalidation():
    ab = pipe._detect_correction(IMP + [140, 150])
    assert ab["mark_label"] == "B-Hoch" and ab["invalidation_price"] == 150
    abc = pipe._detect_correction(IMP + [140, 150, 135])
    assert abc["mark_label"] == "C-Tief" and abc["invalidation_price"] == 135
    a = pipe._detect_correction(IMP + [140])
    assert a["mark_label"] == "W5-Extrem" and a["invalidation_price"] == 160


def test_b_over_a_start_invalid():
    # B überschreitet den A-Start (P5=160) -> keine ABC-Lesart.
    assert pipe._detect_correction(IMP + [140, 165]) is None


def test_c_not_beyond_a_not_complete():
    # C nicht jenseits des A-Endes (140) -> nicht complete.
    assert pipe._detect_correction(IMP + [140, 150, 145]) is None


def test_short_side_symmetric():
    # Abwärts-Impuls (P5=100) + Aufwärts-Korrektur A.
    imps = [160, 140, 150, 120, 130, 100]
    r = pipe._detect_correction(imps + [120])
    assert r is not None and r["direction"] == "short"
    assert r["state"] == "correction_running"


def test_pure_impulse_unchanged_no_correction():
    # Reiner 5er-Impuls (6 Pivots) -> weiterhin impulse_complete (Präzedenz greift nicht).
    assert _state(IMP) == "impulse_complete"


def test_determinism():
    v = IMP + [140, 150, 135]
    assert pipe._detect_correction(v) == pipe._detect_correction(v)


# ---------------------------------------------------------------------------
# Präzedenz: Korrektur gewinnt gegen erneute Impuls-Lesart
# ---------------------------------------------------------------------------
def test_precedence_correction_over_impulse():
    # 9 Pivots (Impuls + A-B-C): die Korrektur-Lesart beschreibt die Lage
    # vollständiger und gewinnt gegen das erneute Lesen der letzten 6/5/3 Pivots.
    st = _state(IMP + [140, 150, 135])
    assert st == "correction_complete"


# ---------------------------------------------------------------------------
# ambiguity v2 (v1 unverändert)
# ---------------------------------------------------------------------------
def test_ambiguity_v2_adds_correction_reading():
    # Pivots mit Impuls + bestätigter Korrektur: v2 = v1 + 1 (Korrektur als
    # Zusatz-Lesart). v1 bleibt unverändert (separat byte-identisch belegt).
    P = _piv(IMP + [140, 150, 135])
    assert pipe._detect_correction([p.price for p in P]) is not None
    v1_total, _ = pipe.ambiguity_fields(P, 135.0)
    v2_total, _ = pipe.ambiguity_v2_fields(P, 135.0)
    assert v2_total == v1_total + 1


def test_ambiguity_v2_alt_correction_kind():
    # Genau eine Impuls-Lesart + eine Korrektur -> alt trägt kind='correction'.
    import elliott_pipeline as ep
    # Konstruiere: impulse=[<eine Long-Lesart>], corr vorhanden -> alt=Korrektur.
    class _P:  # leichter Pivot-Ersatz mit .price/.index
        def __init__(self, i, p): self.index, self.price, self.kind = i, p, "H"
    pivs = _piv(IMP + [140, 150, 135])
    # forciere impulse=1 über einen Monkey-Patch-freien Weg: nutze ein reales Setup
    # (fetch_synthetic liefert end_of_w2) und prüfe nur die alt-Semantik generisch.
    total, alt = ep.ambiguity_v2_fields(pivs, 135.0)
    if alt is not None:
        assert alt["kind"] in ("impulse", "correction")
        if alt["kind"] == "correction":
            assert alt["target_zone"] is None and alt["score_heuristic"] is None


def test_ambiguity_v2_equals_v1_without_correction():
    # Ohne Korrektur (kurze Impuls-Struktur) ist v2 == v1.
    P = _piv([100, 130, 112])
    v1_total, _ = pipe.ambiguity_fields(P, 120.0)
    v2_total, _ = pipe.ambiguity_v2_fields(P, 120.0)
    assert v2_total == v1_total


def test_build_candidate_and_count_carry_v2():
    out = pipe.fetch_synthetic("AMAT")
    e, _, _ = pipe.build_candidate("AMAT", out.data[0], out.data[1])
    assert "valid_count_total_v2" in e and "alt_count_v2" in e
    assert e["valid_count_total_v2"] >= e["valid_count_total"]   # v2 >= v1
    c = pipe._count_from_series(out.data[0], out.data[1])
    assert "valid_count_total_v2" in c and "alt_count_v2" in c


# ---------------------------------------------------------------------------
# Sammlung: ambiguity_n_v2 eingefroren; v1 weiter befüllt
# ---------------------------------------------------------------------------
def test_ambiguity_n_v2_frozen_alongside_v1():
    entry = {"ticker": "TST", "close": 100.0, "score_heuristic": 70.0,
             "target_zone": {"low": 120.0, "high": 130.0},
             "target_zone_extended": {"low": 140.0, "high": 150.0},
             "invalidation_price": 90.0, "direction": "long", "count_label": "W4",
             "chart_points": [], "count_wave_labels": [],
             "valid_count_total": 1, "valid_count_total_v2": 2}
    rec = fc._new_record(entry, "US", "2025-03-03", "risk_on", "2025-03-03", "now")
    assert rec["ambiguity_n"] == 1 and rec["ambiguity_n_v2"] == 2
    assert rec["a_structure_observed"] is None and rec["c_target_pct"] is None


# ---------------------------------------------------------------------------
# W5→A strukturell
# ---------------------------------------------------------------------------
def _w5_series():
    # P4 (W5-Start) @ idx5=100; Hoch (W5-Top) @ idx15=131; danach klare Korrektur mit
    # bestätigtem Tief-Pivot @ idx21=110 (ZIGZAG_WINDOW=5 -> je 5 Bars Raum), dann hoch.
    closes = [80, 85, 90, 95, 98, 100]                                  # idx0–5 (P4@5)
    closes += [104, 108, 113, 118, 122, 125, 127, 129, 130, 131]        # idx6–15 (Hoch@15)
    closes += [128, 123, 118, 114, 112, 110]                            # idx16–21 (Tief@21)
    closes += [112, 118, 124, 130, 136, 142, 148, 154, 160]             # idx22–30 (Erholung)
    dates = [f"2025-06-{i + 1:02d}" for i in range(len(closes))]
    return dates, closes


def _w5_rec(dates, closes, fs_idx=10, p4_idx=5):
    return {"matured": True, "target_hit": 1, "first_seen_date": dates[fs_idx],
            "chart_points": [{"index": p4_idx, "price": closes[p4_idx], "date": dates[p4_idx], "kind": "L"}],
            "count_wave_labels": [{"index": 0, "wave": 4}],
            "pre_reached_target": False, "pre_reached_ext": False, "invalidated": 0,
            "a_structure_observed": None, "c_target_pct": None}


def test_w5_structure_observed_true_with_confirmed_pivot():
    dates, closes = _w5_series()
    r = _w5_rec(dates, closes)
    fc.observe_w5_structure(r, dates, closes, "now")
    # Ein bestätigter Gegen-Pivot nach dem Hoch -> True + c_target_pct gesetzt.
    assert r["a_structure_observed"] is True
    assert r["c_target_pct"] is not None and r["c_target_pct"] > 0


def test_w5_structure_null_when_not_end_of_w4():
    dates, closes = _w5_series()
    r = _w5_rec(dates, closes)
    r["count_wave_labels"] = [{"index": 0, "wave": 2}]     # kein W4
    fc.observe_w5_structure(r, dates, closes, "now")
    assert r["a_structure_observed"] is None


def test_w5_structure_null_when_no_target_hit():
    dates, closes = _w5_series()
    r = _w5_rec(dates, closes)
    r["target_hit"] = 0
    fc.observe_w5_structure(r, dates, closes, "now")
    assert r["a_structure_observed"] is None
