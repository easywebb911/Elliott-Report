#!/usr/bin/env python3
"""BEWEISSICHERUNG (Teil C): echte Schlusskurse zu den In-Session-Records.

WARUM JETZT UND NICHT SPÄTER — DAS FENSTER SCHLIESST SICH TÄGLICH. Ein
In-Session-Record ist nur so lange belegbar, wie die committete Report-Historie
einen SPÄTEREN Lauf enthält, der dieselbe Bar desselben Markts zeigt UND den
Ticker noch in seinen Top-5 führt. Fällt der Ticker aus den Top-5, ist der echte
Schlusskurs jenes Tages aus Repo-Daten nicht mehr rekonstruierbar. Von den 18
heute nicht belegbaren Fällen sind 6 genau so entstanden.

WAS HIER *NICHT* PASSIERT: kein externer Kursabruf. Die Sandbox erreicht die
Quelle nicht, und ein späterer Abruf wäre ohnehin kein Beleg für den Stand von
damals. Quelle ist ausschließlich die committete Report-Historie im Repo.

WAS EIN „ECHTER SCHLUSSKURS" IST: der Kurs derselben Bar aus einem Lauf, der
NICHT selbst in der Sitzung dieser Bar lag — sonst vergliche man einen
Zwischenstand mit einem anderen Zwischenstand. Geprüft mit demselben Prädikat
wie der Marker (``in_session.ist_in_session_anlage``), kein zweites Kriterium.

APPEND-ONLY: bestehende Einträge werden NIE überschrieben oder entfernt.
Identität wie überall sonst: ``(ticker, created_utc)`` — NICHT ``episode_id``.

Die Datei geht in KEINE Berechnung ein. ``evaluate.py`` liest sie nicht, das
Frontend kennt sie nicht, die Pipeline schreibt sie nicht. Sie ist ein
Beweisstück für die Marker-Entscheidung vor der ersten Auswertung.

Läufe:
  ``python scripts/collect_in_session_evidence.py``                → DRY-RUN
  ``python scripts/collect_in_session_evidence.py --live --created-utc 2026-08-07T00:00:00Z``
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

COLL_REL = "data/forward_collection.json"
REPORT_REL = "data/report.json"
EVIDENCE_REL = "data/in_session_evidence.json"
SCHEMA_VERSION = 1

log = logging.getLogger("collect_in_session_evidence")


# ---------------------------------------------------------------------------
# Report-Historie (I/O)
# ---------------------------------------------------------------------------
def bar_datum_bruecke(coll: Dict) -> Dict[Tuple[str, str], Optional[str]]:
    """``{(run_utc, markt): bar_datum}`` aus den Records — für Läufe VOR #63.

    ``diag.last_bar_date`` gibt es erst seit #63 (30.07.2026). Ältere Läufe
    tragen das Feld nicht; ohne Ersatz wären sie als Vergleichsquelle blind,
    und sieben belegbare Fälle fielen still unter den Tisch.

    DIE BRÜCKE IST BELEGT, NICHT ANGENOMMEN: ``first_seen_date`` eines Records
    IST das ``diag.last_bar_date`` seines Markts im anlegenden Lauf — über den
    gesamten Bestand geprüft, 29 von 29 dort, wo beide Angaben existieren, kein
    Gegenbeispiel (Test ``test_bruecke_stimmt_wo_beide_angaben_existieren``).

    Vorsichtsregel: liefern mehrere Records desselben Laufs und Markts
    VERSCHIEDENE ``first_seen_date``, ist die Brücke mehrdeutig -> None statt
    Raten. Kommt im Bestand nicht vor, der Test hält es fest.
    """
    roh: Dict[Tuple[str, str], set] = {}
    for rec in (coll.get("records") or []):
        if not isinstance(rec, dict):
            continue
        schl = (str(rec.get("created_utc")), str(rec.get("market")))
        roh.setdefault(schl, set()).add(rec.get("first_seen_date"))
    return {k: (next(iter(v)) if len(v) == 1 else None) for k, v in roh.items()}


def report_historie(base: Path, bruecke: Optional[Dict] = None) -> List[Dict]:
    """``[{ts, sha, markets:{mk:{last_bar_date, bar_date_source, closes}}}]``.

    Aufsteigend nach ts. ``bruecke`` schließt die Lücke vor #63 (s. o.).

    ACHTUNG FLACHER KLON: `git clone --depth 1` liefert nur einen Bruchteil der
    Stände (#68). Der Aufrufer prüft die Anzahl.
    """
    shas = subprocess.run(["git", "log", "--format=%H", "--", REPORT_REL],
                          cwd=base, capture_output=True, text=True,
                          check=True).stdout.split()
    je_lauf: Dict[str, Dict] = {}
    for sha in shas:
        roh = subprocess.run(["git", "show", f"{sha}:{REPORT_REL}"], cwd=base,
                             capture_output=True, text=True)
        if roh.returncode != 0:
            continue
        try:
            rep = json.loads(roh.stdout)
        except json.JSONDecodeError:  # pragma: no cover — defensiv
            continue
        ts = rep.get("run_timestamp_utc") if isinstance(rep, dict) else None
        if not ts or ts in je_lauf:
            continue
        markets: Dict[str, Dict] = {}
        for mk, mv in (rep.get("markets") or {}).items():
            if not isinstance(mv, dict):
                continue
            bar = (mv.get("diag") or {}).get("last_bar_date")
            quelle = "diag"
            if bar is None and bruecke is not None:
                bar = bruecke.get((str(ts), str(mk)))
                quelle = "bruecke" if bar is not None else "diag"
            markets[mk] = {
                "last_bar_date": bar,
                "bar_date_source": quelle,
                "closes": {c.get("ticker"): c.get("close")
                           for c in (mv.get("candidates") or [])
                           if isinstance(c, dict)},
            }
        je_lauf[str(ts)] = {"ts": str(ts), "sha": sha, "markets": markets}
    return [je_lauf[k] for k in sorted(je_lauf)]


# ---------------------------------------------------------------------------
# Beleg-Suche (pure)
# ---------------------------------------------------------------------------
def belege(records: Sequence[Dict], historie: Sequence[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """(Belege, nicht belegbare Records) — rein, deterministisch, ohne I/O."""
    gefunden: List[Dict] = []
    offen: List[Dict] = []
    for rec in records:
        mk, bar = rec.get("market"), rec.get("first_seen_date")
        ts0, tk = rec.get("created_utc"), rec.get("ticker")
        kandidat = None
        for lauf in historie:                       # aufsteigend -> letzter gewinnt
            if lauf["ts"] <= str(ts0):
                continue
            m = lauf["markets"].get(mk)
            if not m or m.get("last_bar_date") != bar:
                continue
            close = (m.get("closes") or {}).get(tk)
            if close is None:
                continue
            # Der Vergleichslauf darf nicht selbst in der Sitzung DIESER Bar
            # liegen — sonst steht Zwischenstand gegen Zwischenstand.
            if ins.ist_in_session_anlage(mk, lauf["ts"], bar) is not False:
                continue
            kandidat = (lauf, close, m.get("bar_date_source", "diag"))
        if kandidat is None:
            offen.append(rec)
            continue
        lauf, close, bar_quelle = kandidat
        frozen = rec.get("entry_close")
        abweichung = None
        if isinstance(frozen, (int, float)) and isinstance(close, (int, float)) and close:
            abweichung = round((frozen - close) / close * 100.0, 4)
        gefunden.append({
            "ticker": tk,
            "created_utc": ts0,
            "market": mk,
            "bar_date": bar,
            "entry_close_frozen": frozen,
            "close_after_session": close,
            "deviation_pct": abweichung,
            "source_run_utc": lauf["ts"],
            "source_commit": lauf["sha"],
            # Woher stammt das Bar-Datum des VERGLEICHSLAUFS: "diag" = das Feld
            # `diag.last_bar_date` (ab #63), "bruecke" = aus `first_seen_date`
            # der Records jenes Laufs abgeleitet (davor). Steht hier, damit die
            # Beweiskraft je Eintrag sichtbar bleibt statt gemittelt.
            "bar_date_source": bar_quelle,
        })
    gefunden.sort(key=lambda e: (e["created_utc"], e["ticker"]))
    return gefunden, offen


def zusammenfuehren(alt: Optional[Dict], neu: Sequence[Dict],
                    created_utc: str) -> Tuple[Dict, int]:
    """APPEND-ONLY: bestehende Einträge bleiben unangetastet."""
    bestand = list((alt or {}).get("records") or [])
    bekannt = {(e.get("ticker"), e.get("created_utc")) for e in bestand}
    dazu = [e for e in neu if (e["ticker"], e["created_utc"]) not in bekannt]
    alle = bestand + dazu
    alle.sort(key=lambda e: (str(e.get("created_utc")), str(e.get("ticker"))))
    datei = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": (alt or {}).get("created_utc") or created_utc,
        "last_appended_utc": created_utc if dazu else (alt or {}).get("last_appended_utc"),
        "note": ("Echte Schlusskurse zu Records mit in_session_creation. Quelle "
                 "ausschliesslich die committete Report-Historie dieses Repos, "
                 "kein externer Abruf. Geht in KEINE Berechnung ein."),
        "records": alle,
    }
    return datei, len(dazu)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", help="Tatsächlich schreiben.")
    p.add_argument("--created-utc", default=None,
                   help="Stempel der Datei (Pflicht mit --live; kein Systemuhr-Wert).")
    p.add_argument("--root", default=None, help="Repo-Wurzel (Tests).")
    a = p.parse_args(argv)

    base = Path(a.root).resolve() if a.root else REPO_ROOT
    coll = json.loads((base / COLL_REL).read_text(encoding="utf-8"))
    markiert = [r for r in (coll.get("records") or [])
                if isinstance(r, dict) and r.get(ins.MARKER) is True]
    if not markiert:
        log.error("Kein Record trägt %s — erst den Backfill fahren.", ins.MARKER)
        return 2

    historie = report_historie(base, bar_datum_bruecke(coll))
    if len(historie) < 40:
        log.error("Nur %d committete Report-Stände sichtbar — der Klon ist "
                  "vermutlich FLACH. `git fetch --unshallow` ausführen.", len(historie))
        return 3

    gefunden, offen = belege(markiert, historie)
    log.info("Markierte Records: %d | belegbar: %d | nicht belegbar: %d",
             len(markiert), len(gefunden), len(offen))
    for e in gefunden:
        log.info("   %-9s %-2s Bar %s  eingefroren %-12s echt %-12s  %+8.4f %%  <- %s",
                 e["ticker"], e["market"], e["bar_date"], e["entry_close_frozen"],
                 e["close_after_session"], e["deviation_pct"] or 0.0,
                 e["source_run_utc"])
    for r in sorted(offen, key=lambda r: (r.get("created_utc"), r.get("ticker"))):
        log.info("   NICHT BELEGBAR: %-9s %-2s Bar %s (gereift=%s)", r.get("ticker"),
                 r.get("market"), r.get("first_seen_date"), r.get("matured"))

    if not a.live:
        log.info("DRY-RUN — nichts geschrieben (--live zum Ausführen).")
        return 0
    if not a.created_utc:
        log.error("--created-utc ist Pflicht (Determinismus: kein Systemuhr-Wert).")
        return 2

    ziel = base / EVIDENCE_REL
    alt = json.loads(ziel.read_text(encoding="utf-8")) if ziel.exists() else None
    datei, dazu = zusammenfuehren(alt, gefunden, a.created_utc)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with ziel.open("w", encoding="utf-8") as fh:
        json.dump(datei, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    log.info("Geschrieben: %s (%d Einträge, davon %d neu)",
             EVIDENCE_REL, len(datei["records"]), dazu)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
