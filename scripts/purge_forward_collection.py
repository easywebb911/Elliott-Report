#!/usr/bin/env python3
"""Isolierter Rückweg für die Forward-Sammlung (siehe docs/validation_registry.md).

Die Sammlung lebt vollständig in EIGENEN Dateien
(``data/forward_collection.json`` + ``docs/data/forward_collection.json``),
getrennt von ``report.json``. Der Rückweg ist deshalb denkbar einfach und
kollisionsfrei: die beiden Sammel-Dateien werden entfernt (oder auf eine leere,
valide Struktur zurückgesetzt). **``report.json`` wird NIE berührt** — es gibt
keinen gemeinsamen Key, kein Manifest, keine Recompute-Kollision.

Läufe:
  ``python scripts/purge_forward_collection.py``          → DRY-RUN (Preview).
  ``python scripts/purge_forward_collection.py --live``   → führt aus.

Optionen:
  ``--reset``  statt löschen die Dateien auf die leere Struktur zurücksetzen
               (Sammlung bleibt aktiv, startet aber bei 0).
  ``--path X`` Basis-Verzeichnis überschreiben (Tests).

Fail-soft: fehlende Dateien sind kein Fehler (no-op).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Wir spiegeln die Pfad-Konstanten aus forward_collection, ohne das Modul
# zwingend importieren zu müssen (der Rückweg soll auch standalone laufen).
_REL_PATHS = ("data/forward_collection.json", "docs/data/forward_collection.json")
_EMPTY = {"schema_version": 1, "last_run_date": None, "updated_utc": None,
          "records": []}

log = logging.getLogger("purge_forward_collection")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _targets(base: Path):
    return [base / rel for rel in _REL_PATHS]


def _reset_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(_EMPTY, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true",
                   help="Tatsächlich ausführen (sonst Dry-Run).")
    p.add_argument("--reset", action="store_true",
                   help="Auf leere Struktur zurücksetzen statt löschen.")
    p.add_argument("--path", default=None,
                   help="Basis-Verzeichnis (Default: Repo-Root).")
    args = p.parse_args(argv)

    base = Path(args.path) if args.path else _repo_root()
    action = "RESET" if args.reset else "DELETE"
    mode = "LIVE" if args.live else "DRY-RUN"
    log.info("Modus: %s | Aktion: %s | Basis: %s", mode, action, base)

    # Sicherheitsnetz: report.json darf nie in der Zielliste stehen.
    targets = _targets(base)
    assert all("forward_collection" in t.name for t in targets), \
        "Sicherheitsnetz: Ziel enthält Nicht-Sammel-Datei"

    touched = 0
    for path in targets:
        if not path.exists():
            log.info("  (fehlt, übersprungen) %s", path)
            continue
        touched += 1
        if not args.live:
            log.info("  würde %s: %s", action.lower(), path)
            continue
        if args.reset:
            _reset_file(path)
            log.info("  zurückgesetzt: %s", path)
        else:
            path.unlink()
            log.info("  gelöscht: %s", path)

    log.info("Fertig. %d Datei(en) betroffen.%s", touched,
             "" if args.live else " (Dry-Run — nichts geschrieben.)")
    log.info("report.json wurde NICHT berührt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
