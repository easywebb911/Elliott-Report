"""Ambiguitäts-Ausweis v1 (Lit-Check P3) — wie viele valide Long-Zählungen lässt
die Struktur zu (Suchraum = die 2 festen End-Fenster von classify_setup:
Ende-W4/Ende-W2), plus die beste Alternative. REINE ANZEIGE/MESSUNG.

Belegt: N=1 (eindeutig, nichts angezeigt) / N=2 (+ korrekte Alternative);
Short-Alternativen zählen NICHT mit; Primär byte-identisch zu classify_setup;
Determinismus; Einfrieren von ambiguity_n bei Anlage.
"""
import elliott_pipeline as pipe
import forward_collection as fc
from zigzag import Pivot


def _piv(vals):
    return [Pivot(i * 5, v, "H" if i % 2 else "L") for i, v in enumerate(vals)]


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------
def test_n2_both_windows_valid_long():
    # letzte 5 = valides W4-Long UND letzte 3 = valides W2-Long -> N=2.
    P = _piv([100, 130, 112, 160, 145])
    close = 150.0
    total, alt = pipe.ambiguity_fields(P, close)
    assert total == 2
    assert alt is not None
    # Primär = W4 (Priorität), Alternative = W2.
    assert "Ende W2" in alt["count_label"]
    for k in ("count_label", "invalidation_price", "target_zone", "score_heuristic"):
        assert k in alt


def test_n1_single_window():
    # nur 3 Pivots -> W4 unmöglich (len<5), W2 valide -> N=1, keine Alternative.
    P = _piv([100, 130, 112])
    total, alt = pipe.ambiguity_fields(P, 120.0)
    assert total == 1 and alt is None


def test_primary_byte_identical_to_classify_setup():
    # counts[0] der Enumeration == classify_setup-Primär (gleiche Wahl, gleiches Dict).
    for vals, close in ([100, 130, 112, 160, 145], 150.0), ([100, 130, 112], 120.0):
        P = _piv(vals)
        prim = pipe.classify_setup(P, close)
        counts = pipe.enumerate_long_counts(P, close)
        assert counts, "Primär sollte ein Long-Count sein"
        assert counts[0] == prim, "Primär-Zählung darf sich NICHT ändern"


def test_short_counts_not_counted():
    # Abwärts-Struktur: die Zählung ist SHORT (direction<0) -> zählt NICHT mit.
    P = _piv([130, 100, 118])          # p0=130 > p1=100 -> Abwärts-W1 -> short
    prim = pipe.classify_setup(P, 110.0)
    assert prim is not None and prim["direction"] < 0
    total, alt = pipe.ambiguity_fields(P, 110.0)
    assert total == 0 and alt is None   # Long-only: keine valide Long-Zählung


def test_alt_is_best_of_rest_by_score():
    # Bei genau 2 ist die Alternative die Nicht-Primäre, nach score_setup bewertet.
    P = _piv([100, 130, 112, 160, 145])
    counts = pipe.enumerate_long_counts(P, 150.0)
    total, alt = pipe.ambiguity_fields(P, 150.0)
    assert total == 2
    assert alt["score_heuristic"] == pipe.score_setup(counts[1])


def test_determinism():
    P = _piv([100, 130, 112, 160, 145])
    a = pipe.ambiguity_fields(P, 150.0)
    b = pipe.ambiguity_fields(P, 150.0)
    assert a[0] == b[0] and a[1] == b[1]


# ---------------------------------------------------------------------------
# Kandidat + Zeitebenen-Count tragen die Felder
# ---------------------------------------------------------------------------
def test_build_candidate_and_count_carry_ambiguity():
    out = pipe.fetch_synthetic("AMAT")
    entry, _, _ = pipe.build_candidate("AMAT", out.data[0], out.data[1])
    assert isinstance(entry["valid_count_total"], int) and entry["valid_count_total"] >= 1
    assert "alt_count" in entry
    c = pipe._count_from_series(out.data[0], out.data[1])
    assert "valid_count_total" in c and "alt_count" in c


# ---------------------------------------------------------------------------
# Messung: ambiguity_n bei Anlage eingefroren
# ---------------------------------------------------------------------------
def test_ambiguity_n_frozen_at_new_record():
    entry = {"ticker": "TST", "close": 100.0, "score_heuristic": 70.0,
             "target_zone": {"low": 120.0, "high": 130.0},
             "target_zone_extended": {"low": 140.0, "high": 150.0},
             "invalidation_price": 90.0, "direction": "long", "count_label": "W4",
             "chart_points": [], "count_wave_labels": [], "valid_count_total": 2}
    rec = fc._new_record(entry, "US", "2025-03-03", "risk_on", "2025-03-03", "now")
    assert rec["ambiguity_n"] == 2
    # fehlt das Feld (Alt-Kandidat) -> null (fail-soft, kein Backfill)
    del entry["valid_count_total"]
    rec2 = fc._new_record(entry, "US", "2025-03-03", "risk_on", "2025-03-03", "now")
    assert rec2["ambiguity_n"] is None
