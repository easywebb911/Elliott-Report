#!/usr/bin/env python3
"""BACKFILL (einmalig): setzt ``in_session_creation`` auf den Bestand.

Kriterium, Marker-Semantik und Begründung stehen in ``scripts/in_session.py``.
Dieses Skript wendet sie EINMAL auf die bestehende Sammlung an — danach hält
``elliott_pipeline.main()`` den Marker von selbst fort (Teil B).

MET/D/PRU-PRINZIP: markieren, NIEMALS heilen. Es wird nichts zusammengeführt,
gelöscht oder in einem bestehenden Feld geändert; ausschließlich die zwei
additiven Marker-Felder entstehen.

DETERMINISMUS: das Kriterium braucht nur ``created_utc`` und ``market`` des
Records — kein Netz, kein Zufall, keine Uhrzeit. ``--marked-utc`` ist deshalb
PFLICHT und wird nicht aus der Systemuhr erraten: derselbe Repo-Stand mit
demselben Argument ergibt byte-identisch dasselbe Ergebnis.

BELEG STATT ANNAHME: ``--verify-history`` prüft gegen die committete
Report-Historie, dass jedes ``created_utc`` wirklich ein ``run_timestamp_utc``
eines Laufs ist — nur dann IST der Record-Stempel der Report-Stempel des
anlegenden Laufs, wie das Kriterium es verlangt.

Läufe:
  ``python scripts/mark_in_session_creation.py``                 → DRY-RUN
  ``python scripts/mark_in_session_creation.py --verify-history`` → + Beleg
  ``python scripts/mark_in_session_creation.py --live --marked-utc 2026-08-07T00:00:00Z``
  ``python scripts/mark_in_session_creation.py --purge --live``   → RÜCKWEG

Idempotent: ein zweiter Lauf ändert nichts (der ursprüngliche ``marked_utc``
bleibt stehen — die Markierung ist ein einmaliges Ereignis).
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import in_session as ins  # noqa: E402

REL_PATHS = ("data/forward_collection.json", "docs/data/forward_collection.json")
REPORT_REL = "data/report.json"

log = logging.getLogger("mark_in_session_creation")


# ---------------------------------------------------------------------------
# Historien-Beleg (I/O, nur für --verify-history)
# ---------------------------------------------------------------------------
def committete_report_stempel(base: Path) -> List[str]:
    """Alle ``run_timestamp_utc`` der committeten Report-Stände.

    ACHTUNG FLACHER KLON: ein `git clone --depth 1` (so klont die Sandbox und
    so klont `actions/checkout` per Default) liefert hier nur einen Bruchteil
    der Stände — dieselbe Falle wie in #68. Der Aufrufer prüft die Anzahl.
    """
    shas = subprocess.run(["git", "log", "--format=%H", "--", REPORT_REL],
                          cwd=base, capture_output=True, text=True,
                          check=True).stdout.split()
    stempel: List[str] = []
    for sha in shas:
        roh = subprocess.run(["git", "show", f"{sha}:{REPORT_REL}"], cwd=base,
                             capture_output=True, text=True)
        if roh.returncode != 0:
            continue
        try:
            st = json.loads(roh.stdout)
        except json.JSONDecodeError:  # pragma: no cover — defensiv
            continue
        ts = st.get("run_timestamp_utc") if isinstance(st, dict) else None
        if ts:
            stempel.append(str(ts))
    return sorted(set(stempel))


def pruefe_stempel_identitaet(records: Sequence[Dict],
                              report_stempel: Sequence[str]) -> List[Dict]:
    """Records, deren ``created_utc`` KEIN committeter Report-Stempel ist."""
    bekannt = set(report_stempel)
    return [r for r in records if r.get("created_utc") not in bekannt]


# ---------------------------------------------------------------------------
# Anwenden / Rückweg
# ---------------------------------------------------------------------------
def _schreibe(path: Path, coll: Dict) -> None:
    """Exakt das Format von forward_collection.write_collection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(coll, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", help="Tatsächlich schreiben.")
    p.add_argument("--purge", action="store_true", help="RÜCKWEG: Marker entfernen.")
    p.add_argument("--marked-utc", default=None,
                   help="Stempel für in_session_creation_marked_utc "
                        "(Pflicht ohne --purge; NICHT aus der Systemuhr).")
    p.add_argument("--verify-history", action="store_true",
                   help="created_utc gegen die committeten Report-Stempel belegen.")
    p.add_argument("--root", default=None, help="Repo-Wurzel (Tests).")
    a = p.parse_args(argv)

    base = Path(a.root).resolve() if a.root else REPO_ROOT
    haupt = base / REL_PATHS[0]
    if not haupt.exists():
        log.error("Sammlung nicht gefunden: %s", haupt)
        return 2
    coll = json.loads(haupt.read_text(encoding="utf-8"))
    records = coll.get("records") or []

    if a.purge:
        entfernt = ins.entferne_marker(records)
        log.info("RÜCKWEG: %d Record(s) tragen den Marker.", entfernt)
        if not a.live:
            log.info("DRY-RUN — nichts geschrieben (--live zum Ausführen).")
            return 0
        for rel in REL_PATHS:
            ziel = base / rel
            if ziel.exists() or rel == REL_PATHS[0]:
                _schreibe(ziel, coll)
        log.info("Marker entfernt, %d Datei(en) geschrieben.", len(REL_PATHS))
        return 0

    if not a.marked_utc:
        log.error("--marked-utc ist Pflicht (Determinismus: kein Systemuhr-Wert).")
        return 2

    if a.verify_history:
        stempel = committete_report_stempel(base)
        if len(stempel) < 40:
            log.error("Nur %d committete Report-Stände sichtbar — der Klon ist "
                      "vermutlich FLACH. `git fetch --unshallow` ausführen; mit "
                      "Teilhistorie wird hier nicht belegt.", len(stempel))
            return 3
        fremd = pruefe_stempel_identitaet(records, stempel)
        if fremd:
            log.error("%d Record(s) mit einem created_utc, das kein committeter "
                      "Report-Stempel ist — das Kriterium steht auf der "
                      "Gleichsetzung created_utc == run_timestamp_utc:", len(fremd))
            for r in fremd:
                log.error("   %s %s", r.get("ticker"), r.get("created_utc"))
            return 3
        log.info("BELEG: alle %d created_utc sind committete Report-Stempel "
                 "(%d Report-Stände geprüft).", len(records), len(stempel))

    treffer, unklar = ins.betroffene_records(records)
    log.info("In-Session-Records: %d von %d", len(treffer), len(records))
    for r in sorted(treffer, key=lambda r: (r.get("created_utc"), r.get("ticker"))):
        log.info("   %-9s %-2s %s  Bar %s", r.get("ticker"), r.get("market"),
                 r.get("created_utc"), r.get("first_seen_date"))
    if unklar:
        log.warning("NICHT BERECHENBAR (bleiben unmarkiert): %d", len(unklar))
        for r in unklar:
            log.warning("   %s market=%r created_utc=%r", r.get("ticker"),
                        r.get("market"), r.get("created_utc"))

    gesetzt, _ = ins.markiere(records, a.marked_utc)
    log.info("Neu gesetzt: %d (bereits markiert: %d)",
             gesetzt, len(treffer) - gesetzt)
    if not a.live:
        log.info("DRY-RUN — nichts geschrieben (--live zum Ausführen).")
        return 0
    for rel in REL_PATHS:
        ziel = base / rel
        if ziel.exists() or rel == REL_PATHS[0]:
            _schreibe(ziel, coll)
    log.info("Geschrieben: %s", ", ".join(REL_PATHS))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
