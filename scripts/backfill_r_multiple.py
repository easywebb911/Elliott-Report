#!/usr/bin/env python3
"""Befüllt die R-Multiple-Felder rückwirkend auf bereits bestehenden Records.

HINTERGRUND (06.09.2026, siehe docs/validation_registry.md). Easy hat nach der
n>=EVAL_MIN_N-Primärauswertung (#121, reine Trefferquote nicht signifikant über
dem Zufalls-Benchmark) zurecht argumentiert: bei realistischem Risikomanagement
(Positionsgröße invers zum Invalidierungs-Abstand skaliert) zählt das
Chance-Risiko-Verhältnis je Setup ("R-Multiple"), nicht die reine Trefferquote.
Für eine SPÄTERE, EIGENSTÄNDIGE Präregistrierung auf dieser Basis werden ab
jetzt zusätzlich, rein additiv, folgende Felder geführt (siehe
``forward_collection._r_kennzahlen``/``_r_erreicht_paar``):

    risiko_abstand            entry_close - invalidation_price
    chance_abstand_basis      target_zone.low - entry_close
    chance_abstand_extension  target_zone_extended.low - entry_close
    crv_basis                 chance_abstand_basis / risiko_abstand
    crv_extension             chance_abstand_extension / risiko_abstand
    r_erreicht_basis          −1,0 bei Invalidierung, +crv_basis bei Zonen-
                              treffer, sonst der tatsächliche Kursstand nach
                              10 Handelstagen relativ zum Risiko-Abstand
    r_erreicht_extension      dieselbe Regel, bezogen auf die Extension-Zone
    r_nicht_ermittelbar_grund NUR gesetzt, wenn risiko_abstand <= 0 (Invali-
                              dierung liegt über dem Einstieg — "1R" ist dann
                              nicht definiert) — crv_*/r_erreicht_* bleiben in
                              diesem Fall None, KEINE geschätzte Notlösung
                              (Easy-Entscheidung 06.09.2026).

ZWEI Gruppen, unterschiedlich behandelt:
  (a) crv/chance/risiko-Geometrie ist eine reine Funktion von entry_close/
      invalidation_price/target_zone(_extended) — für ALLE 133 Records sofort
      verfügbar, unabhängig vom Reifungsstatus.
  (b) r_erreicht_* braucht zusätzlich target_hit/ext_hit/invalidated UND (im
      "neutral"-Fall) den Kursstand am 10. Handelstag — NUR für bereits
      GEREIFTE Records (``matured: True``) verfügbar. Der Kurswert selbst ist
      dabei KEINE neue Datenquelle: ``mature_record()`` friert seit Commit
      7f67a6f (23.07.2026, vor der ältesten Episode dieser Sammlung) bei jeder
      Reifung ``price_path`` ein — die volle 10-Tage-Schlusskursreihe. Für
      offene Records (``matured: False``) bleibt r_erreicht_* auf None; sie
      bekommen den Wert regulär über ``mature_record()``, sobald sie künftig
      reifen (die dort JETZT zusätzlich berechnete Formel ist identisch,
      s. ``_r_erreicht_paar`` — EINE Stelle für die Regel).

MET/D/PRU-PRINZIP: rein additiv. Kein bestehendes Feld wird gelesen, um es zu
verändern; nichts wird zusammengeführt oder gelöscht. Ein Record, der die
Felder bereits trägt (jede künftige Neuanlage über ``_new_record`` sowie ein
bereits einmal befüllter Alt-Record), wird NICHT angefasst — Idempotenz: ein
zweiter Lauf ändert nichts mehr.

Läufe:
  ``python scripts/backfill_r_multiple.py``         -> DRY-RUN (Vorschau)
  ``python scripts/backfill_r_multiple.py --live``  -> schreibt

Kein Netz, kein Zufall, keine Uhrzeit-Abhängigkeit — reine Funktion der
bereits vorhandenen Sammlungs-Datei.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Sequence

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path
import forward_collection as fc

REPO_ROOT = Path(__file__).resolve().parent.parent

REL_PATHS = (fc.FORWARD_PATH, fc.FORWARD_PATH_PUBLISHED)
GEOMETRIE_FELDER = ("risiko_abstand", "chance_abstand_basis",
                    "chance_abstand_extension", "crv_basis", "crv_extension")

log = logging.getLogger("backfill_r_multiple")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def befuelle_record(rec: Dict) -> bool:
    """Ergänzt EINEN Record additiv. Gibt True zurück, wenn etwas geändert
    wurde. Rührt kein bestehendes Feld an — prüft je Feld einzeln, ob es
    schon da ist, statt den ganzen Record pauschal zu überspringen (ein
    Record könnte theoretisch schon r_erreicht_*, aber noch nicht die
    Geometrie tragen, oder umgekehrt — additiv heißt additiv)."""
    geaendert = False

    if not all(f in rec for f in GEOMETRIE_FELDER):
        kz = fc._r_kennzahlen(rec["entry_close"], rec["invalidation_price"],
                              rec["target_zone"], rec["target_zone_extended"])
        for k, v in kz.items():
            if k not in rec:
                rec[k] = v
                geaendert = True

    if "r_erreicht_basis" not in rec or "r_erreicht_extension" not in rec:
        if rec.get("matured") and not rec.get("unmeasurable"):
            if rec.get("r_nicht_ermittelbar_grund"):
                basis = ext = None
            else:
                pfad = rec.get("price_path") or []
                letzter = pfad[-1]["close"] if pfad else None
                entry = rec["entry_close"]
                risk = entry - rec["invalidation_price"]
                if letzter is None or not fc.finite(risk) or risk <= 0:
                    basis = ext = None
                else:
                    neutral_r = round((letzter - entry) / risk, 4)
                    basis, ext = fc._r_erreicht_paar(
                        rec.get("target_hit"), rec.get("ext_hit"),
                        rec.get("invalidated"), rec.get("crv_basis"),
                        rec.get("crv_extension"), neutral_r)
            if "r_erreicht_basis" not in rec:
                rec["r_erreicht_basis"] = basis
                geaendert = True
            if "r_erreicht_extension" not in rec:
                rec["r_erreicht_extension"] = ext
                geaendert = True
        else:
            # Noch nicht gereift (oder unmeasurable) -> None, wie bei jeder
            # Neuanlage (_new_record) auch. Wird regulär bei künftiger
            # Reifung über mature_record() befüllt.
            if "r_erreicht_basis" not in rec:
                rec["r_erreicht_basis"] = None
                geaendert = True
            if "r_erreicht_extension" not in rec:
                rec["r_erreicht_extension"] = None
                geaendert = True

    return geaendert


def anwenden(coll: Dict) -> int:
    """Wendet ``befuelle_record`` auf alle Records an. Reine Funktion,
    kein I/O. Gibt die Zahl der GEÄNDERTEN Records zurück."""
    return sum(1 for rec in coll.get("records", []) if befuelle_record(rec))


def _schreibe(path: Path, coll: Dict) -> None:
    """Exakt das Format von forward_collection.write_collection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(coll, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv: Sequence[str] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", help="Tatsächlich schreiben.")
    p.add_argument("--path", default=None,
                   help="Basis-Verzeichnis der Sammlungs-Dateien (Default: Repo-Root).")
    args = p.parse_args(argv)

    base = Path(args.path) if args.path else _repo_root()
    modus = "LIVE" if args.live else "DRY-RUN"
    ziele = [base / rel for rel in REL_PATHS if (base / rel).exists()]
    if not ziele:
        log.info("Keine Sammlungs-Datei unter %s — nichts zu tun.", base)
        return 0

    log.info("Modus: %s | Basis: %s", modus, base)
    for path in ziele:
        coll = json.loads(path.read_text(encoding="utf-8"))
        n = anwenden(coll)
        gereift_mit_r = sum(
            1 for r in coll.get("records", [])
            if r.get("matured") and r.get("r_erreicht_basis") is not None)
        gereift_gesamt = sum(1 for r in coll.get("records", []) if r.get("matured"))
        log.info("  %s: %d Record(s) ergänzt%s — %d/%d gereifte Episoden mit r_erreicht",
                 path.relative_to(base), n, "" if args.live else " (Dry-Run, nichts geschrieben)",
                 gereift_mit_r, gereift_gesamt)
        if args.live and n:
            _schreibe(path, coll)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
