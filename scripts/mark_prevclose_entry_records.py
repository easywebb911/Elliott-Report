#!/usr/bin/env python3
"""Markiert Records, die auf einem Lauf mit Kurs-Stand VOM VORTAG entstanden
(sitzungsbewusste Regel) — GETRENNTER Marker neben ``stale_market_suspect``.

HINTERGRUND (03.11.2026). ``scripts/mark_stale_market_records.py`` markiert
dieselbe Art Vorfall, rechnet den Rückstand aber bewusst nach dem alten,
reinen KALENDERTAG-Anker (``market_calendar.handelstage_rueckstand``) — und
bleibt dabei ABSICHTLICH so, weil er die historische Markierung beschreibt,
die der GATE-Code damals wirklich benutzte (``tests/test_sammlungs_schutz.py``,
Abschnitte 9 und 12b: "harte Grenze", "darf sich nicht rückwirkend ändern").

Dieses Skript ist die GETRENNTE Antwort auf dieselbe Frage mit der HEUTIGEN,
sitzungsbewussten Regel (``market_calendar.handelstage_rueckstand_sitzung``)
— derselben Regel, die ``health_check.check_bar_freshness`` (die reale
``bar_freshness``-Warnung) und das Sammlungs-Gate (``forward_collection.
stale_markets``) seit 17.09.2026 benutzen. Es ändert NICHTS an
``mark_stale_market_records.py`` und schreibt NIEMALS in dessen Marker-Feld.

MET/D/PRU-PRINZIP (wie beim Altmarker): bereits entstandene Records werden
**markiert, niemals geheilt**. Nichts wird zusammengeführt, gelöscht oder in
einem bestehenden Feld geändert. Die betroffenen Records bekommen additiv
EIN NEUES, EIGENES Feld:

    "prevclose_entry_suspect": {
        "marked_date":       Datum dieser Markierung (Argument, deterministisch)
        "run_utc":           Lauf, der den Record anlegte
        "last_bar_date":     Kurs-Stand des Markts in jenem Lauf (der Beleg)
        "lag_trading_days":  Rückstand in Handelstagen (SITZUNGSBEWUSST)
    }

Das Feld hat KEINE Zählwirkung: ``evaluate.py`` ist als Auswertung v1
SHA-gepinnt und liest ausschließlich ``FROZEN_FIELDS`` — dieser Marker steht
dort nicht. Ob/wie markierte Records künftig behandelt werden, ist eine
EIGENE, spätere Entscheidung (gemeinsam mit den bestehenden drei Markern aus
``filter_sensitivity_sammlung.py.MARKERS`` — dieses Skript trägt sich dort
BEWUSST NICHT selbst ein, s. Bericht).

WIEDERVERWENDUNG, KEINE NEUERFINDUNG: ``finde_stale_records()`` wird
UNVERÄNDERT aus ``mark_stale_market_records`` importiert — dieselbe Funktion,
mit denselben Garantien (rein, deterministisch, keine Seitenwirkung). Nur die
EINGABE (``lag_je_lauf``) unterscheidet sich: ``rueckstaende_je_lauf_sitzung()``
unten ruft ausschließlich ``market_calendar.handelstage_rueckstand_sitzung``
auf — keine eigene Kalender-Logik.

Läufe:
  ``python scripts/mark_prevclose_entry_records.py``                → DRY-RUN
  ``python scripts/mark_prevclose_entry_records.py --live``         → schreibt
  ``python scripts/mark_prevclose_entry_records.py --purge --live`` → RÜCKWEG

Idempotent: ein zweiter ``--live``-Lauf schreibt denselben Marker und ändert
nichts (siehe Tests).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path (EIN Baustein, s. repo_path.py; KEINE neue Eigenkopie)
import market_calendar as cal  # noqa: E402
from mark_stale_market_records import (  # noqa: E402 — Wiederverwendung, keine Kopie
    REL_PATHS,
    _last_bar,
    _repo_root,
    _schreibe,
    committete_reports,
    committete_sammlungen,
    finde_stale_records,
    marker_fuer,
    record_key,
)

MARKER = "prevclose_entry_suspect"

log = logging.getLogger("mark_prevclose_entry_records")


# ---------------------------------------------------------------------------
# Replay (pure) — EINZIGER neuer Rechenschritt: die sitzungsbewusste Regel.
# ---------------------------------------------------------------------------
def rueckstaende_je_lauf_sitzung(
    report_staende: Sequence[Dict],
) -> Dict[str, Dict[str, int]]:
    """``{run_timestamp_utc: {markt: rueckstand}}``, SITZUNGSBEWUSST.

    Dieselbe Form wie ``mark_stale_market_records.rueckstaende_je_lauf()``
    (passt deshalb unverändert in ``finde_stale_records()``), aber mit
    ``cal.handelstage_rueckstand_sitzung`` statt ``cal.handelstage_rueckstand``
    — exakt die Regel, die ``health_check.check_bar_freshness`` und
    ``forward_collection.stale_markets`` ebenfalls benutzen. Keine eigene
    Kalender-Logik, nur der eine, bereits vorhandene Aufruf.
    """
    out: Dict[str, Dict[str, int]] = {}
    for r in report_staende:
        ts = r.get("run_timestamp_utc")
        if not ts:
            continue
        jetzt = cal.parse_ts(ts)
        je_markt: Dict[str, int] = {}
        if jetzt is not None:
            for mk, m in (r.get("markets") or {}).items():
                if not isinstance(m, dict):
                    continue
                bar = (m.get("diag") or {}).get("last_bar_date")
                lag = cal.handelstage_rueckstand_sitzung(bar, mk, jetzt)
                if isinstance(lag, int):
                    je_markt[mk] = lag
        out[ts] = je_markt
    return out


# ---------------------------------------------------------------------------
# Anwenden / Rückweg — EIGENER Marker-Name, sonst identisches Muster zu
# mark_stale_market_records.setze_marker()/entferne_marker().
# ---------------------------------------------------------------------------
def setze_marker(coll: Dict, treffer: Sequence[Dict], marked_date: str,
                 last_bars: Dict[tuple, Optional[str]]) -> int:
    """Setzt den Marker in-place. Ändert AUSSCHLIESSLICH ``prevclose_entry_
    suspect`` — niemals ``stale_market_suspect`` oder ein anderes Feld."""
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
        log.error("--date fehlt (z. B. --date 2026-11-03).")
        return 2

    reports = committete_reports(git_root)
    treffer = finde_stale_records(committete_sammlungen(git_root),
                                  rueckstaende_je_lauf_sitzung(reports))
    last_bars = {t["key"]: _last_bar(reports, t["run_utc"], t["market"])
                 for t in treffer}
    log.info("Modus: %s | Aktion: MARK (%s) | Basis: %s | Historie: %s",
             modus, MARKER, base, git_root)
    log.info("Replay: %d Record(s) mit Kurs-Stand vom Vortag (sitzungsbewusst) angelegt",
             len(treffer))
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
