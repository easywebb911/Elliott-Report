#!/usr/bin/env python3
"""Markiert Records, die auf einem Lauf mit VERALTETEM Markt-Stand entstanden.

HINTERGRUND (05.08.2026). Am 04.08. lieferte die Quelle für beide Märkte eine
nicht-finite Tageszeile; die Härtung verwarf sie zu Recht, und der Report
rechnete danach auf Kursen vom 31.07. In diesem Zustand legte die Sammlung eine
Episode an (KKR), die es bei aktuellen Kursen nicht gäbe. Der Sammlungs-Schutz
verhindert das ab dem 05.08. — er wirkt aber nur VORWÄRTS.

MET/D/PRU-PRINZIP: bereits entstandene Records werden **markiert, niemals
geheilt**. Nichts wird zusammengeführt, gelöscht oder in einem bestehenden Feld
geändert. Die betroffenen Records bekommen additiv EIN Feld:

    "stale_market_suspect": {
        "marked_date":   Datum dieser Markierung (Argument, deterministisch)
        "run_utc":       Lauf, der den Record anlegte
        "last_bar_date": Kurs-Stand des Markts in jenem Lauf (der Beleg)
        "lag_trading_days": Rückstand in Handelstagen
    }

Das Feld hat JETZT KEINE Zählwirkung: ``evaluate.py`` ist als Auswertung v1
eingefroren und wird nicht angefasst. Wie markierte Records behandelt werden,
wird **gemeinsam mit ``episode_split_suspect``** bei der Marker-Entscheidung
VOR der ersten echten Auswertung (n>=EVAL_MIN_N) festgelegt — zwei Marker auf
derselben Population gehören in EINE Entscheidung.

IDENTIFIKATION per REPLAY: die committeten Sammlungs-Stände werden mit den
committeten Report-Ständen über den Lauf-Zeitstempel verknüpft (``updated_utc``
der Sammlung == ``run_timestamp_utc`` des Reports — beide stammen aus demselben
``ts`` eines Laufs). Für jeden NEU angelegten Record wird der Rückstand SEINES
Markts in jenem Lauf bestimmt — mit ``market_calendar.handelstage_rueckstand``,
derselben Funktion, die Wächter und Gate benutzen.

Läufe:
  ``python scripts/mark_stale_market_records.py``                → DRY-RUN
  ``python scripts/mark_stale_market_records.py --live``         → schreibt
  ``python scripts/mark_stale_market_records.py --purge --live`` → RÜCKWEG

Idempotent: ein zweiter Lauf schreibt denselben Marker und ändert nichts.
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
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import market_calendar as cal  # noqa: E402

MARKER = "stale_market_suspect"
REL_PATHS = ("data/forward_collection.json", "docs/data/forward_collection.json")
REPORT_REL = "data/report.json"

log = logging.getLogger("mark_stale_market_records")


def _repo_root() -> Path:
    return REPO_ROOT


def record_key(rec: Dict) -> Tuple:
    """Identität über Lauf-Stände hinweg — wie bei ``mark_episode_splits``.

    NICHT ``episode_id`` (``ticker@first_seen``): das kollidiert real.
    ``created_utc`` ist je Record eindeutig, pro Lauf entsteht höchstens einer
    je Ticker.
    """
    return (rec.get("ticker"), rec.get("created_utc"))


# ---------------------------------------------------------------------------
# Replay (pure)
# ---------------------------------------------------------------------------
def rueckstaende_je_lauf(report_staende: Sequence[Dict]) -> Dict[str, Dict[str, int]]:
    """``{run_timestamp_utc: {markt: rueckstand}}`` aus den Report-Ständen."""
    out: Dict[str, Dict[str, int]] = {}
    for r in report_staende:
        ts = r.get("run_timestamp_utc")
        if not ts:
            continue
        je_markt: Dict[str, int] = {}
        for mk, m in (r.get("markets") or {}).items():
            if not isinstance(m, dict):
                continue
            lag = cal.handelstage_rueckstand(
                (m.get("diag") or {}).get("last_bar_date"), str(ts)[:10])
            if isinstance(lag, int):
                je_markt[mk] = lag
        out[ts] = je_markt
    return out


def finde_stale_records(coll_staende: Sequence[Dict],
                        lag_je_lauf: Dict[str, Dict[str, int]],
                        ab_lag: int = 1) -> List[Dict]:
    """Records, die auf einem Lauf mit veraltetem Markt-Stand NEU entstanden.

    ``coll_staende`` = Sammlungs-Stände NACH je einem Lauf, aufsteigend nach
    ``updated_utc``. Rein lesend, deterministisch, ohne Seiteneffekt.
    """
    treffer: List[Dict] = []
    bekannt = set()
    erster = True
    for cur in coll_staende:
        ts = cur.get("updated_utc")
        lags = lag_je_lauf.get(str(ts), {})
        for rec in cur.get("records", []):
            key = record_key(rec)
            if key in bekannt:
                continue
            bekannt.add(key)
            if erster:
                continue          # der Anfangsbestand ist kein „neu angelegt"
            lag = lags.get(rec.get("market"))
            if isinstance(lag, int) and lag >= ab_lag:
                treffer.append({
                    "key": key, "ticker": rec.get("ticker"),
                    "market": rec.get("market"),
                    "episode_id": rec.get("episode_id"),
                    "run_utc": str(ts), "lag_trading_days": lag,
                })
        erster = False
    return treffer


def marker_fuer(treffer: Dict, marked_date: str, last_bar: Optional[str]) -> Dict:
    return {"marked_date": marked_date, "run_utc": treffer["run_utc"],
            "last_bar_date": last_bar, "lag_trading_days": treffer["lag_trading_days"]}


# ---------------------------------------------------------------------------
# Git-Historie (I/O)
# ---------------------------------------------------------------------------
def _committete(base: Path, rel: str, zeitfeld: str) -> List[Dict]:
    """Alle committeten Stände von ``rel``, nach ``zeitfeld`` sortiert/entdoppelt."""
    shas = subprocess.run(["git", "log", "--format=%H", "--", rel], cwd=base,
                          capture_output=True, text=True, check=True).stdout.split()
    je_lauf: Dict[str, Dict] = {}
    for sha in shas:
        roh = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=base,
                             capture_output=True, text=True)
        if roh.returncode != 0:
            continue
        try:
            st = json.loads(roh.stdout)
        except json.JSONDecodeError:  # pragma: no cover — defensiv
            continue
        if isinstance(st, dict) and st.get(zeitfeld):
            je_lauf[st[zeitfeld]] = st
    return [je_lauf[k] for k in sorted(je_lauf)]


def committete_sammlungen(base: Path) -> List[Dict]:
    return _committete(base, REL_PATHS[0], "updated_utc")


def committete_reports(base: Path) -> List[Dict]:
    return _committete(base, REPORT_REL, "run_timestamp_utc")


def _last_bar(report_staende: Sequence[Dict], run_utc: str,
              market: Optional[str]) -> Optional[str]:
    for r in report_staende:
        if r.get("run_timestamp_utc") == run_utc:
            m = (r.get("markets") or {}).get(market) or {}
            return (m.get("diag") or {}).get("last_bar_date")
    return None


# ---------------------------------------------------------------------------
# Anwenden / Rückweg
# ---------------------------------------------------------------------------
def _schreibe(path: Path, coll: Dict) -> None:
    """Exakt das Format von forward_collection.write_collection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(coll, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def setze_marker(coll: Dict, treffer: Sequence[Dict], marked_date: str,
                 last_bars: Dict[Tuple, Optional[str]]) -> int:
    """Setzt den Marker in-place. Ändert AUSSCHLIESSLICH ``stale_market_suspect``."""
    nach_key = {t["key"]: t for t in treffer}
    gesetzt = 0
    for rec in coll.get("records", []):
        t = nach_key.get(record_key(rec))
        if t is None:
            continue
        neu = marker_fuer(t, marked_date, last_bars.get(t["key"]))
        if rec.get(MARKER) != neu:
            rec[MARKER] = neu
            gesetzt += 1
    return gesetzt


def entferne_marker(coll: Dict) -> int:
    entfernt = 0
    for rec in coll.get("records", []):
        if MARKER in rec:
            del rec[MARKER]
            entfernt += 1
    return entfernt


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", help="Tatsächlich schreiben.")
    p.add_argument("--purge", action="store_true", help="RÜCKWEG: Marker entfernen.")
    p.add_argument("--date", default=None, help="marked_date (Pflicht ohne --purge).")
    p.add_argument("--path", default=None, help="Basis-Verzeichnis der Dateien.")
    p.add_argument("--git-root", default=None,
                   help="Repo für die Historie (Default: Repo-Root).")
    args = p.parse_args(argv)

    base = Path(args.path) if args.path else _repo_root()
    git_root = Path(args.git_root) if args.git_root else _repo_root()
    modus = "LIVE" if args.live else "DRY-RUN"
    ziele = [base / rel for rel in REL_PATHS if (base / rel).exists()]
    if not ziele:
        log.info("Keine Sammlungs-Datei unter %s — nichts zu tun.", base)
        return 0

    if args.purge:
        log.info("Modus: %s | Aktion: PURGE | Basis: %s", modus, base)
        for path in ziele:
            coll = json.loads(path.read_text(encoding="utf-8"))
            n = entferne_marker(coll)
            log.info("  %s: %d Marker%s", path.relative_to(base), n,
                     "" if args.live else " (Dry-Run)")
            if args.live and n:
                _schreibe(path, coll)
        return 0

    if not args.date:
        log.error("--date fehlt (z. B. --date 2026-08-05).")
        return 2

    reports = committete_reports(git_root)
    treffer = finde_stale_records(committete_sammlungen(git_root),
                                  rueckstaende_je_lauf(reports))
    last_bars = {t["key"]: _last_bar(reports, t["run_utc"], t["market"])
                 for t in treffer}
    log.info("Modus: %s | Aktion: MARK | Basis: %s | Historie: %s",
             modus, base, git_root)
    log.info("Replay: %d Record(s) auf veraltetem Markt-Stand angelegt", len(treffer))
    for t in treffer:
        log.info("  %s (%s) Lauf %s — Kurs-Stand %s, %d Handelstag(e) zurück",
                 t["ticker"], t["market"], t["run_utc"],
                 last_bars.get(t["key"]), t["lag_trading_days"])
    for path in ziele:
        coll = json.loads(path.read_text(encoding="utf-8"))
        n = setze_marker(coll, treffer, args.date, last_bars)
        log.info("  %s: %d Record(s) neu markiert%s", path.relative_to(base), n,
                 "" if args.live else " (Dry-Run)")
        if args.live and n:
            _schreibe(path, coll)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
