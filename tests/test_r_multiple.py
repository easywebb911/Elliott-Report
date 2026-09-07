"""R-Multiple-Erfassung (additiv, 06.09.2026) — risiko_abstand/chance_abstand_*/
crv_*/r_erreicht_* (siehe docs/validation_registry.md, Eintrag 06.09.2026).

Deckt genau die Fälle ab, die die Diagnose vor der Umsetzung fand und die
Easy per Rückfrage entschieden hat: matured-Gating (kein verfrühter
"neutral"-Wert vor Tag 10), invertiertes Risiko (entry_close <
invalidation_price -> None statt Schätzung, KEINE Notlösung), Extension-
Divergenz (target_zone_extended.low kann UNTER ODER ÜBER target_zone.low
liegen -> eigenes CRV/r_erreicht-Paar statt eines gemeinsamen Werts), und
Konsistenz zwischen `mature_record()` (Live-Reifung) und dem rückwirkenden
Backfill (`scripts/backfill_r_multiple.py`) — EINE Regel (`_r_erreicht_paar`),
zwei Aufrufer, darf nie auseinanderlaufen (Guardian-Nit, 07.09.2026)."""
from __future__ import annotations

import copy

import forward_collection as fc
import backfill_r_multiple as bf

ENTRY = {
    "ticker": "TEST", "close": 100.0, "score_heuristic": 1.0,
    "target_zone": {"low": 120.0, "high": 130.0},
    "target_zone_extended": {"low": 140.0, "high": 150.0},
    "invalidation_price": 90.0,
}
NOW = "2026-01-01T00:00:00Z"


def _neu(entry_over=None):
    entry = dict(ENTRY, **(entry_over or {}))
    return fc._new_record(entry, "US", "2026-01-01", "bull", "2026-01-01", NOW)


def _serie(vals):
    """``vals`` = Schlusskurse NACH dem Einstiegstag (Index 0 = first_seen)."""
    dates = ["2026-01-01"] + [f"2026-01-{d:02d}" for d in range(2, 2 + len(vals))]
    return dates, [100.0] + list(vals)


# ---------------------------------------------------------------------------
# Geometrie bei Anlage (_r_kennzahlen, in _new_record)
# ---------------------------------------------------------------------------
def test_geometrie_bei_anlage_ist_sofort_verfuegbar():
    rec = _neu()
    assert rec["risiko_abstand"] == 10.0
    assert rec["chance_abstand_basis"] == 20.0
    assert rec["chance_abstand_extension"] == 40.0
    assert rec["crv_basis"] == 2.0
    assert rec["crv_extension"] == 4.0
    assert "r_nicht_ermittelbar_grund" not in rec
    assert rec["r_erreicht_basis"] is None and rec["r_erreicht_extension"] is None


def test_chance_abstand_negativ_wird_ehrlich_gespeichert_nicht_gefiltert():
    """PRU-Guard-Fall (Zone schon bei Anlage erreicht): chance_abstand_basis
    und crv_basis werden als rohe (dann negative) Zahlen gespeichert — keine
    Sonderbehandlung, dieselbe Praxis wie beim bestehenden r_multiple-Feld."""
    rec = _neu({"close": 125.0})  # ueber target_zone.low (120.0)
    assert rec["risiko_abstand"] == 35.0  # entry(125) - invalidation(90)
    assert rec["chance_abstand_basis"] == -5.0
    assert rec["crv_basis"] == round(-5.0 / 35.0, 4)


# ---------------------------------------------------------------------------
# Invertiertes Risiko (Easy-Entscheidung 06.09.2026: None, keine Notloesung)
# ---------------------------------------------------------------------------
def test_invertiertes_risiko_liefert_none_mit_grund():
    rec = _neu({"invalidation_price": 105.0})  # entry(100) < invalidation(105)
    assert rec["risiko_abstand"] == -5.0
    assert rec["crv_basis"] is None and rec["crv_extension"] is None
    assert rec["r_nicht_ermittelbar_grund"] == "invertiertes_risiko"

    # Auch nach vollstaendiger Reifung bleibt r_erreicht_* None — KEINE
    # geschaetzte Notloesung, unabhaengig vom tatsaechlichen Kursverlauf.
    dates, closes = _serie([105.0] * 10)
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["matured"] is True
    assert rec["r_erreicht_basis"] is None and rec["r_erreicht_extension"] is None


# ---------------------------------------------------------------------------
# matured-Gating: kein verfrühter "neutral"-Wert vor dem finalen Reifungslauf
# ---------------------------------------------------------------------------
def test_r_erreicht_bleibt_none_bis_zum_finalen_reifungslauf():
    rec = _neu()
    # Lauf 1: nur 3 Tage Daten, Invalidierung feuert bereits am 2. Tag —
    # `resolved` ist True, `matured` aber noch False (bars_elapsed < 10).
    dates1, closes1 = _serie([95.0, 85.0])
    fc.mature_record(rec, dates1, closes1, NOW)
    assert rec["matured"] is False and rec["invalidated"] == 1
    assert rec["r_erreicht_basis"] is None, (
        "r_erreicht darf vor dem vollen 10-Tage-Horizont nicht gesetzt sein")
    assert rec["r_erreicht_extension"] is None

    # Lauf 2: jetzt 10 Tage Daten vorhanden -> matured, r_erreicht final.
    dates2, closes2 = _serie([95.0, 85.0, 80.0, 78.0, 76.0, 74.0, 72.0, 70.0, 68.0, 66.0])
    fc.mature_record(rec, dates2, closes2, NOW)
    assert rec["matured"] is True
    assert rec["r_erreicht_basis"] == -1.0 and rec["r_erreicht_extension"] == -1.0


# ---------------------------------------------------------------------------
# Extension-Divergenz (Easy-Entscheidung 06.09.2026: eigenes CRV-Paar)
# ---------------------------------------------------------------------------
def test_extension_treffer_ohne_basiszonentreffer_nutzt_eigenes_crv():
    """Wie MA@2026-08-19 real in der Sammlung: die (niedrigere) Extension-Zone
    wird erreicht, die (höhere) Basiszone nicht — beide r_erreicht-Werte
    müssen sich unterscheiden, nicht denselben CRV teilen."""
    entry = dict(ENTRY, close=100.0, invalidation_price=90.0)
    entry["target_zone"] = {"low": 130.0, "high": 140.0}
    entry["target_zone_extended"] = {"low": 121.0, "high": 135.0}
    rec = fc._new_record(entry, "US", "2026-01-01", "bull", "2026-01-01", NOW)
    assert rec["crv_basis"] != rec["crv_extension"]

    # Kurs erreicht 121 (Extension), aber nie 130 (Basiszone).
    dates, closes = _serie([121.5] * 10)
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["target_hit"] == 0 and rec["ext_hit"] == 1
    assert rec["r_erreicht_extension"] == rec["crv_extension"]
    # Basiszone nie getroffen, nicht invalidiert -> neutraler Fallback,
    # NICHT crv_basis (der waere ein Treffer, den es nie gab).
    assert rec["r_erreicht_basis"] != rec["crv_basis"]
    erwartet_neutral = round((closes[-1] - 100.0) / 10.0, 4)
    assert rec["r_erreicht_basis"] == erwartet_neutral


def test_beide_zonen_getroffen_liefert_beide_positiven_crv_werte():
    rec = _neu()
    dates, closes = _serie([145.0] * 10)  # ueber beiden Zonen (120/140)
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["target_hit"] == 1 and rec["ext_hit"] == 1
    assert rec["r_erreicht_basis"] == rec["crv_basis"] == 2.0
    assert rec["r_erreicht_extension"] == rec["crv_extension"] == 4.0


# ---------------------------------------------------------------------------
# Konsistenz mature_record() <-> backfill_r_multiple.py (Guardian-Nit)
# ---------------------------------------------------------------------------
def test_backfill_reproduziert_mature_record_exakt():
    """Ein Record wird regulaer gereift (mature_record) — DAS ist die
    Referenz. Danach werden exakt die additiven R-Multiple-Felder wieder
    entfernt (simuliert einen Alt-Record von vor Phase 2) und per Backfill
    neu berechnet. Beide Wege muessen BYTE-IDENTISCHE Werte liefern, sonst
    laufen die zwei Implementierungen derselben Regel auseinander."""
    rec_referenz = _neu()
    dates, closes = _serie([121.0, 122.0, 123.0, 124.0, 125.0, 126.0, 127.0,
                            128.0, 129.0, 131.0])
    fc.mature_record(rec_referenz, dates, closes, NOW)
    assert rec_referenz["matured"] is True

    alt_record = copy.deepcopy(rec_referenz)
    for feld in ("risiko_abstand", "chance_abstand_basis",
                "chance_abstand_extension", "crv_basis", "crv_extension",
                "r_erreicht_basis", "r_erreicht_extension"):
        alt_record.pop(feld, None)

    geaendert = bf.befuelle_record(alt_record)
    assert geaendert is True
    for feld in ("risiko_abstand", "chance_abstand_basis",
                "chance_abstand_extension", "crv_basis", "crv_extension",
                "r_erreicht_basis", "r_erreicht_extension"):
        assert alt_record[feld] == rec_referenz[feld], (
            f"{feld}: Backfill {alt_record[feld]!r} != mature_record "
            f"{rec_referenz[feld]!r}")


def test_backfill_ist_idempotent():
    rec = _neu()
    coll = {"records": [rec]}
    n1 = bf.anwenden(coll)
    assert n1 == 0, "Geometrie ist bei Anlage schon da — nichts zu ergaenzen"

    del rec["crv_basis"]
    n2 = bf.anwenden(coll)
    assert n2 == 1
    n3 = bf.anwenden(coll)
    assert n3 == 0, "zweiter Lauf auf demselben Stand darf nichts mehr aendern"


def test_backfill_ruehrt_bestehende_felder_nicht_an():
    rec = _neu()
    dates, closes = _serie([145.0] * 10)
    fc.mature_record(rec, dates, closes, NOW)
    vorher = copy.deepcopy(rec)
    del rec["r_erreicht_basis"]

    bf.befuelle_record(rec)

    for k, v in vorher.items():
        if k == "r_erreicht_basis":
            continue
        assert rec[k] == v, f"{k} wurde veraendert, obwohl nur ergaenzt werden sollte"


def test_backfill_offener_record_bekommt_geometrie_aber_kein_r_erreicht():
    rec = _neu()
    assert rec["matured"] is False
    geaendert = bf.befuelle_record(rec)
    # Geometrie war schon da (Anlage), r_erreicht_* war schon None -> nichts
    # NEU ergaenzt, aber beides bleibt korrekt vorhanden/None.
    assert geaendert is False
    assert rec["crv_basis"] == 2.0
    assert rec["r_erreicht_basis"] is None
