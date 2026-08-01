#!/usr/bin/env python3
"""Markiert Alt-Records, die vom Mehrfach-Lauf-Defekt zerschnitten wurden.

HINTERGRUND (01.08.2026). Bis zum 31.07.2026 hing der Episoden-Anschluss an
``coll["last_run_date"]`` — dem Datum des letzten LAUFS. Bei mehreren Läufen
am selben Kalendertag setzte der erste Lauf dieses Datum bereits auf heute;
ein Record von gestern fand im zweiten Lauf desselben Tages keinen Anschluss
mehr und wurde zu einer ZWEITEN Episode zerschnitten, obwohl der Ticker an
zwei konsekutiven Kalendertagen in den Top 5 stand. Die Anschluss-Regel ist
seit dem 01.08. repariert (``forward_collection.episode_anchor_dates``); sie
wirkt aber nur VORWÄRTS.

MET/D/PRU-PRINZIP: bereits zerschnittene Records werden **markiert, niemals
geheilt**. Es wird nichts zusammengeführt, nichts gelöscht, kein bestehendes
Feld geändert. Die betroffenen Records bekommen additiv EIN Feld:

    "episode_split_suspect": {
        "marked_date":       Datum dieser Markierung (Argument, deterministisch)
        "reason":            "mehrfach_lauf_tag"
        "run_date":          Lauf-Datum, an dem der Schnitt entstand
        "would_have_extended": episode_id des Vorgängers, den die Soll-Regel
                             verlängert hätte
    }

Das Feld hat JETZT KEINE Zählwirkung: ``evaluate.py`` ist als Auswertung v1
eingefroren und wird nicht angefasst. Ob und wie die Auswertung markierte
Records behandelt, ist eine spätere, datierte Entscheidung VOR der ersten
echten Auswertung (n>=EVAL_MIN_N). Siehe docs/validation_registry.md.

IDENTIFIKATION per REPLAY über die committeten Sammlungs-Stände: für jeden
Lauf-Übergang wird geprüft, ob ein neu angelegter Record unter der SOLL-Regel
eine Verlängerung gewesen wäre, während die ALTE Regel ihn nicht erfasst hat.
Nur diese Differenzmenge wird markiert — nichts, was auch die Soll-Regel als
neue Episode angelegt hätte. Die Stände werden nach ``updated_utc`` sortiert,
nicht nach Git-Reihenfolge: die Rebase-Schleife des Tageslaufs verdreht die
Commit-Reihenfolge gelegentlich gegenüber der echten Lauf-Reihenfolge.

Läufe:
  ``python scripts/mark_episode_splits.py``                 → DRY-RUN (Preview)
  ``python scripts/mark_episode_splits.py --live``          → schreibt Marker
  ``python scripts/mark_episode_splits.py --purge --live``  → RÜCKWEG: entfernt
      exakt die Marker-Felder; der Rest bleibt byte-identisch.

Idempotent: ein zweiter Lauf schreibt denselben Marker und ändert nichts.
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

MARKER = "episode_split_suspect"
REL_PATHS = ("data/forward_collection.json", "docs/data/forward_collection.json")

log = logging.getLogger("mark_episode_splits")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Replay (pure) — keine Datei-, keine Git-Zugriffe
# ---------------------------------------------------------------------------
def record_key(rec: Dict) -> Tuple:
    """Identität eines Records über Lauf-Stände hinweg.

    NICHT ``episode_id``: das ist ``ticker@first_seen`` und kollidiert bei genau
    den Splits, um die es hier geht (zwei Records desselben Tickers mit
    demselben ``first_seen_date`` — real: ADS.DE@2026-07-24). ``created_utc``
    ist je Record eindeutig: pro Lauf entsteht höchstens ein Record je Ticker.
    """
    return (rec.get("ticker"), rec.get("created_utc"))


def finde_splits(staende: Sequence[Dict]) -> List[Dict]:
    """Die zerschnittenen Records aus einer nach Lauf-Zeit sortierten Folge.

    ``staende`` = Sammlungs-Stände NACH je einem Lauf, aufsteigend. Ein Record
    gilt als Split, wenn er in einem Übergang NEU auftaucht und im Vorzustand
    ein offener Record desselben Tickers lag, den die SOLL-Anker erfasst hätten,
    die ALTEN aber nicht. Rein lesend, deterministisch, ohne Seiteneffekt.
    """
    treffer: List[Dict] = []
    vor: Optional[Dict] = None
    prev_run: Optional[str] = None
    prev_distinct: Optional[str] = None
    for cur in staende:
        run_date = cur.get("last_run_date")
        if vor is not None and run_date:
            alt_anker = {prev_run}
            soll_anker = {run_date}
            if prev_run and prev_run != run_date:
                soll_anker.add(prev_run)
            elif prev_run == run_date and prev_distinct:
                soll_anker.add(prev_distinct)
            bekannt = {record_key(r) for r in vor.get("records", [])}
            for rec in cur.get("records", []):
                if record_key(rec) in bekannt:
                    continue
                offen = [a for a in vor.get("records", [])
                         if a.get("ticker") == rec.get("ticker")
                         and not a.get("matured")]
                nach_alt = [a for a in offen
                            if a.get("last_seen_top5_date") in alt_anker]
                nach_soll = [a for a in offen
                             if a.get("last_seen_top5_date") in soll_anker]
                if nach_soll and not nach_alt:
                    vorgaenger = max(
                        nach_soll,
                        key=lambda a: str(a.get("last_seen_top5_date")))
                    treffer.append({
                        "key": record_key(rec),
                        "ticker": rec.get("ticker"),
                        "run_date": run_date,
                        "neue_episode": rec.get("episode_id"),
                        "would_have_extended": vorgaenger.get("episode_id"),
                    })
        if run_date:
            if prev_run != run_date:
                prev_distinct = prev_run
            prev_run = run_date
        vor = cur
    return treffer


def marker_fuer(treffer: Dict, marked_date: str) -> Dict:
    """Der Marker-Inhalt — eine reine Funktion, damit er testbar fix ist."""
    return {
        "marked_date": marked_date,
        "reason": "mehrfach_lauf_tag",
        "run_date": treffer["run_date"],
        "would_have_extended": treffer["would_have_extended"],
    }


# ---------------------------------------------------------------------------
# Git-Historie (I/O)
# ---------------------------------------------------------------------------
def committete_staende(base: Path, rel: str = REL_PATHS[0]) -> List[Dict]:
    """Alle committeten Stände von ``rel``, nach ``updated_utc`` sortiert.

    Stände ohne ``updated_utc`` (der Initial-Commit der leeren Struktur) fallen
    heraus; mehrfach committete Stände desselben Laufs werden entdoppelt.
    """
    shas = subprocess.run(["git", "log", "--format=%H", "--", rel],
                          cwd=base, capture_output=True, text=True,
                          check=True).stdout.split()
    je_lauf: Dict[str, Dict] = {}
    for sha in shas:
        roh = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=base,
                             capture_output=True, text=True, check=True).stdout
        try:
            st = json.loads(roh)
        except json.JSONDecodeError:  # pragma: no cover — defensiv
            continue
        if isinstance(st, dict) and st.get("updated_utc"):
            je_lauf[st["updated_utc"]] = st
    return [je_lauf[u] for u in sorted(je_lauf)]


# ---------------------------------------------------------------------------
# Anwenden / Rückweg (I/O)
# ---------------------------------------------------------------------------
def _schreibe(path: Path, coll: Dict) -> None:
    """Exakt das Format von forward_collection.write_collection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(coll, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def setze_marker(coll: Dict, treffer: Sequence[Dict], marked_date: str) -> int:
    """Setzt den Marker in-place. Gibt die Zahl der markierten Records zurück.

    Ändert AUSSCHLIESSLICH das Feld ``episode_split_suspect``. Idempotent:
    ein bereits identisch markierter Record zählt nicht erneut.
    """
    nach_key = {t["key"]: t for t in treffer}
    gesetzt = 0
    for rec in coll.get("records", []):
        t = nach_key.get(record_key(rec))
        if t is None:
            continue
        neu = marker_fuer(t, marked_date)
        if rec.get(MARKER) != neu:
            rec[MARKER] = neu
            gesetzt += 1
    return gesetzt


def entferne_marker(coll: Dict) -> int:
    """Rückweg: entfernt exakt ``episode_split_suspect``. In-place."""
    entfernt = 0
    for rec in coll.get("records", []):
        if MARKER in rec:
            del rec[MARKER]
            entfernt += 1
    return entfernt


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true",
                   help="Tatsächlich schreiben (sonst Dry-Run).")
    p.add_argument("--purge", action="store_true",
                   help="RÜCKWEG: nur die Marker-Felder entfernen.")
    p.add_argument("--date", default=None,
                   help="marked_date im Marker (Pflicht ohne --purge).")
    p.add_argument("--path", default=None,
                   help="Basis-Verzeichnis der Sammlungs-DATEIEN "
                        "(Default: Repo-Root).")
    p.add_argument("--git-root", default=None,
                   help="Repo, aus dem die Historie gelesen wird (Default: "
                        "Repo-Root). Getrennt von --path, damit Tests die "
                        "Dateien isolieren, die Historie aber echt bleibt.")
    args = p.parse_args(argv)

    base = Path(args.path) if args.path else _repo_root()
    git_root = Path(args.git_root) if args.git_root else _repo_root()
    modus = "LIVE" if args.live else "DRY-RUN"
    ziele = [base / rel for rel in REL_PATHS if (base / rel).exists()]
    if not ziele:
        log.info("Keine Sammlungs-Datei unter %s — nichts zu tun.", base)
        return 0

    if args.purge:
        log.info("Modus: %s | Aktion: PURGE (Marker entfernen) | Basis: %s",
                 modus, base)
        for path in ziele:
            coll = json.loads(path.read_text(encoding="utf-8"))
            n = entferne_marker(coll)
            log.info("  %s: %d Marker%s", path.relative_to(base), n,
                     "" if args.live else " (Dry-Run, nichts geschrieben)")
            if args.live and n:
                _schreibe(path, coll)
        return 0

    if not args.date:
        log.error("--date fehlt (Datum der Markierung, z. B. --date 2026-08-01).")
        return 2

    treffer = finde_splits(committete_staende(git_root))
    log.info("Modus: %s | Aktion: MARK | Basis: %s | Historie: %s",
             modus, base, git_root)
    log.info("Replay über die committeten Stände: %d zerschnittene Record(s)",
             len(treffer))
    for t in treffer:
        log.info("  %s  Lauf %s  %s  (Soll: Verlängerung von %s)",
                 t["ticker"], t["run_date"], t["neue_episode"],
                 t["would_have_extended"])
    for path in ziele:
        coll = json.loads(path.read_text(encoding="utf-8"))
        n = setze_marker(coll, treffer, args.date)
        log.info("  %s: %d Record(s) neu markiert%s", path.relative_to(base), n,
                 "" if args.live else " (Dry-Run, nichts geschrieben)")
        if args.live and n:
            _schreibe(path, coll)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
