#!/usr/bin/env python3
"""BACKFILL (einmalig): setzt ``invertiertes_risiko_bei_anlage`` auf den Bestand.

Kriterium, Marker-Semantik und Begründung stehen in
``scripts/invertiertes_risiko_anlage.py``. Dieses Skript wendet sie EINMAL auf
die bestehende Sammlung an. Anders als ``mark_in_session_creation.py`` gibt es
HIER keine laufende Fortführung im Tageslauf (Mini-Stopp, s. Moduldoc jenes
Skripts und SESSION_HANDOVER.md) — jeder künftige Lauf braucht bis auf
Weiteres einen erneuten (idempotenten) Aufruf dieses Backfills.

MET/D/PRU-PRINZIP: markieren, NIEMALS heilen. Es wird nichts zusammengeführt,
gelöscht oder in einem bestehenden Feld geändert; ausschließlich die zwei
additiven Marker-Felder entstehen.

DETERMINISMUS: das Kriterium braucht nur ``entry_close``/``invalidation_price``
des Records — kein Netz, kein Zufall, keine Uhrzeit. ``--marked-utc`` ist
deshalb PFLICHT und wird nicht aus der Systemuhr erraten: derselbe Repo-Stand
mit demselben Argument ergibt byte-identisch dasselbe Ergebnis.

Läufe:
  ``python scripts/mark_invertiertes_risiko_anlage.py``                 → DRY-RUN
  ``python scripts/mark_invertiertes_risiko_anlage.py --live --marked-utc 2026-10-14T00:00:00Z``
  ``python scripts/mark_invertiertes_risiko_anlage.py --purge --live``   → RÜCKWEG

Idempotent: ein zweiter Lauf ändert nichts (der ursprüngliche ``marked_utc``
bleibt stehen — die Markierung ist ein einmaliges Ereignis).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Sequence

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path
import invertiertes_risiko_anlage as ira  # noqa: E402

REPO_ROOT = repo_path.REPO_ROOT

REL_PATHS = ("data/forward_collection.json", "docs/data/forward_collection.json")

log = logging.getLogger("mark_invertiertes_risiko_anlage")


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
                   help="Stempel für invertiertes_risiko_bei_anlage_marked_utc "
                        "(Pflicht ohne --purge; NICHT aus der Systemuhr).")
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
        entfernt = ira.entferne_marker(records)
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

    treffer, unklar = ira.betroffene_records(records)
    log.info("Invertiertes-Risiko-Records: %d von %d", len(treffer), len(records))
    for r in sorted(treffer, key=lambda r: (r.get("created_utc"), r.get("ticker"))):
        log.info("   %-9s %-2s entry_close=%s invalidation_price=%s  %s",
                 r.get("ticker"), r.get("market"), r.get("entry_close"),
                 r.get("invalidation_price"), r.get("created_utc"))
    if unklar:
        log.warning("NICHT BERECHENBAR (bleiben unmarkiert): %d", len(unklar))
        for r in unklar:
            log.warning("   %s entry_close=%r invalidation_price=%r",
                        r.get("ticker"), r.get("entry_close"), r.get("invalidation_price"))

    gesetzt, _ = ira.markiere(records, a.marked_utc)
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
