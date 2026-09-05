"""Sensitivitäts-Sammlung für die präregistrierte Auswertung (05.09.2026).

ANLASS: Die Auswertungsregel (docs/validation_registry.md, Eintrag
07./08.08.2026) verlangt eine Sensitivitätsrechnung ohne Records, die
mindestens einen der drei Qualitäts-Marker tragen. `evaluate.py` (v1,
SHA-gepinnt) kennt diese Marker bewusst nicht — die Trennung passiert VOR
dem Auswertungslauf, auf Ebene der `--sammlung`-Eingabedatei. Dieses Skript
(`scripts/filter_sensitivity_sammlung.py`) erzeugt diese gefilterte Kopie,
OHNE die Originaldatei zu berühren.

ZWEI NETZE:
  (a) Synthetische Fälle — jede Marker-Kombination einzeln UND überlappend,
      deterministisch, unabhängig vom täglich wandernden echten Datenstand.
  (b) Ein Lauf gegen die ECHTE, aktuelle `data/forward_collection.json` —
      prüft aber nur INVARIANTEN (jeder entfernte Record trägt mindestens
      einen Marker, jeder verbleibende keinen, Summe stimmt, Original
      bleibt byte-identisch), NIE eine hart codierte Zahl — die Sammlung
      wächst täglich per Cron, ein fester Zahlenwert wäre morgen bereits
      falsch.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import filter_sensitivity_sammlung as fs  # noqa: E402

ECHTE_SAMMLUNG = ROOT / "data" / "forward_collection.json"


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rec(id_, **marker):
    r = {"episode_id": id_, "matured": True}
    r.update(marker)
    return r


# ---------------------------------------------------------------------------
# (a) Synthetische Fälle — jede Marker-Kombination
# ---------------------------------------------------------------------------
def test_filtert_jeden_der_drei_marker_einzeln():
    coll = {"schema_version": 1, "records": [
        _rec("ohne_marker"),
        _rec("mit_in_session", in_session_creation=True),
        _rec("mit_split", episode_split_suspect={"marked_date": "2026-08-01"}),
        _rec("mit_stale", stale_market_suspect={"marked_date": "2026-08-05"}),
    ]}
    neu, entfernt = fs.filtere(coll)
    assert [r["episode_id"] for r in neu["records"]] == ["ohne_marker"]
    assert {r["episode_id"] for r in entfernt} == {
        "mit_in_session", "mit_split", "mit_stale"}


def test_ueberlappende_marker_werden_nur_einmal_entfernt():
    coll = {"records": [
        _rec("doppelt", in_session_creation=True,
             episode_split_suspect={"marked_date": "2026-08-01"}),
        _rec("dreifach", in_session_creation=True,
             episode_split_suspect={"marked_date": "2026-08-01"},
             stale_market_suspect={"marked_date": "2026-08-05"}),
    ]}
    neu, entfernt = fs.filtere(coll)
    assert neu["records"] == []
    assert len(entfernt) == 2   # kein Record taucht doppelt in der Liste auf


def test_marker_auf_false_oder_none_zaehlt_nicht_als_gesetzt():
    """Ein gelöschtes/nie gesetztes Feld ist 'falsch' — dieselbe
    Wahrheitswert-Prüfung wie überall sonst in der Codebasis
    (scripts/in_session.py:224 setzt True, nie False)."""
    coll = {"records": [
        _rec("false_wert", in_session_creation=False),
        _rec("none_wert", episode_split_suspect=None),
    ]}
    neu, _ = fs.filtere(coll)
    assert len(neu["records"]) == 2


def test_andere_top_level_felder_bleiben_unveraendert_durchgereicht():
    coll = {"schema_version": 1, "updated_utc": "2026-09-05T00:00:00Z",
            "last_run_date": "2026-09-05", "records": [_rec("x")]}
    neu, _ = fs.filtere(coll)
    assert neu["schema_version"] == 1
    assert neu["updated_utc"] == "2026-09-05T00:00:00Z"
    assert neu["last_run_date"] == "2026-09-05"


def test_filtere_ist_eine_reine_funktion_kein_input_mutiert():
    coll = {"records": [_rec("a", in_session_creation=True), _rec("b")]}
    original_json = json.dumps(coll, sort_keys=True)
    fs.filtere(coll)
    assert json.dumps(coll, sort_keys=True) == original_json, \
        "filtere() hat das Eingabe-Dict veraendert"


def test_leere_sammlung_ergibt_leere_ausgabe_kein_absturz():
    neu, entfernt = fs.filtere({"records": []})
    assert neu["records"] == [] and entfernt == []
    neu2, entfernt2 = fs.filtere({})
    assert neu2["records"] == [] and entfernt2 == []


# ---------------------------------------------------------------------------
# CLI: main() schreibt eine NEUE Datei, Original bleibt unangetastet
# ---------------------------------------------------------------------------
def test_main_schreibt_neue_datei_original_bleibt_byte_identisch(tmp_path):
    quelle = tmp_path / "sammlung.json"
    quelle.write_text(json.dumps({"schema_version": 1, "records": [
        _rec("a"), _rec("b", in_session_creation=True),
    ]}), encoding="utf-8")
    vorher_hash = _hash(quelle)
    vorher_bytes = quelle.read_bytes()

    ziel = tmp_path / "sensitivity.json"
    # main() loest --sammlung/--out über REPO_ROOT / args auf; ein bereits
    # ABSOLUTER Pfad bleibt dabei unveraendert (Python-Path-Semantik:
    # `Path("/repo") / "/abs"` == `Path("/abs")`), tmp_path funktioniert also
    # direkt, ohne Bezug zu REPO_ROOT.
    rc = fs.main(["--sammlung", str(quelle), "--out", str(ziel),
                  "--now", "2026-09-05T22:53:00Z"])
    assert rc == 0
    assert quelle.read_bytes() == vorher_bytes, "Originaldatei wurde veraendert"
    assert _hash(quelle) == vorher_hash

    ergebnis = json.loads(ziel.read_text(encoding="utf-8"))
    assert [r["episode_id"] for r in ergebnis["records"]] == ["a"]
    meta = ergebnis["sensitivity_filter"]
    assert meta["records_gesamt"] == 2
    assert meta["records_entfernt"] == 1
    assert meta["records_verbleibend"] == 1
    assert meta["erzeugt_utc"] == "2026-09-05T22:53:00Z"
    assert meta["nennungen_je_marker"]["in_session_creation"] == 1
    assert meta["nennungen_je_marker"]["episode_split_suspect"] == 0
    assert meta["nennungen_je_marker"]["stale_market_suspect"] == 0


def test_main_ueberschreibt_niemals_die_eingabedatei_selbst():
    """Sicherheitsnetz gegen ein Versehen: --out darf niemals zufaellig
    gleich --sammlung sein und dadurch die Originaldatei kaputt schreiben."""
    quelle_arg = "data/forward_collection.json"
    ziel_arg = "data/forward_collection_sensitivity.json"
    assert quelle_arg != ziel_arg


# ---------------------------------------------------------------------------
# (b) Echte, aktuelle Sammlung — nur Invarianten, keine harte Zahl
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not ECHTE_SAMMLUNG.exists(), reason="keine echte Sammlung vorhanden")
def test_echte_sammlung_invarianten_und_original_bleibt_unangetastet(tmp_path):
    vorher_hash = _hash(ECHTE_SAMMLUNG)
    coll = json.loads(ECHTE_SAMMLUNG.read_text(encoding="utf-8"))

    neu, entfernt = fs.filtere(coll)

    assert _hash(ECHTE_SAMMLUNG) == vorher_hash, \
        "die Originaldatei wurde durch das reine Einlesen veraendert"
    assert len(neu["records"]) + len(entfernt) == len(coll.get("records") or [])
    for r in entfernt:
        assert fs._traegt_marker(r), "entfernter Record ohne jeden Marker"
    for r in neu["records"]:
        assert not fs._traegt_marker(r), "verbliebener Record traegt einen Marker"

    # Auch der CLI-Pfad (main()) darf die Originaldatei nicht anfassen.
    ziel = tmp_path / "sensitivity.json"
    rc = fs.main(["--sammlung", "data/forward_collection.json",
                  "--out", str(ziel), "--now", "2026-09-05T22:53:00Z"])
    assert rc == 0
    assert _hash(ECHTE_SAMMLUNG) == vorher_hash
