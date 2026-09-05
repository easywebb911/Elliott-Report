#!/usr/bin/env python3
"""Erzeugt die Sensitivitäts-Sammlung für die präregistrierte Auswertung.

HINTERGRUND (05.09.2026, Vorbereitung der n>=EVAL_MIN_N-Auswertung).
Die Auswertungsregel (docs/validation_registry.md, Eintrag 07./08.08.2026)
verlangt ZWEI getrennte Rechnungen: (a) die Primärrechnung über alle
auswertbaren Records, (b) eine Sensitivitätsrechnung ohne die Records, die
mindestens einen der drei Qualitäts-Marker tragen (``in_session_creation``,
``episode_split_suspect``, ``stale_market_suspect``). Wörtlich aus der
Registry: "(b) ist eine Sicht auf dieselben Daten, kein Eingriff in sie."

``scripts/evaluate.py`` ist als Auswertung v1 SHA-gepinnt (Hash im Test
gepinnt, siehe tests/test_sammlungs_schutz.py) und kennt diese drei Marker
BEWUSST nicht — die Trennung in (a)/(b) passiert deshalb nicht im
Auswertungsprogramm selbst, sondern VORHER, auf Ebene der Eingabedatei: (b)
braucht eine eigene ``--sammlung``-Datei ohne die markierten Records. Dieses
Skript erzeugt genau diese Datei.

WAS ES TUT (rein mechanisch, keine Interpretation):
  1. liest ``data/forward_collection.json`` (nur lesend),
  2. entfernt jeden Record, der MINDESTENS EINEN der drei Marker trägt
     (Wahrheitswert-Prüfung wie im Rest der Codebasis: ``in_session_creation``
     steht auf ``True``, die anderen beiden auf einem Metadaten-Dict — beides
     ist "wahr", ein gelöschtes/nie gesetztes Feld ist "falsch"),
  3. schreibt das Ergebnis als NEUE, zusätzliche Datei
     (``data/forward_collection_sensitivity.json``) — die Originaldatei wird
     nicht angefasst, nicht einmal geöffnet mit Schreibrecht.

WAS ES BEWUSST NICHT TUT: es trifft keine Aussage über Invalidierung,
PRU-Guard-Ausschluss (``pre_reached_target``/``pre_reached_ext``/
``pre_guard_contaminated``, s. ``forward_collection.is_excluded``) oder
Reifung — das bleibt vollständig Sache von ``evaluate.py``s eigener,
unveränderter ``build_population()``/``is_excluded()``-Logik, angewandt auf
die (gefilterte oder ungefilterte) Sammlung, die man ihr per ``--sammlung``
übergibt. Ein Record kann z. B. gleichzeitig einen Qualitäts-Marker UND
einen PRU-Guard-Ausschlussgrund tragen — dieses Skript entfernt ihn allein
wegen des Qualitäts-Markers; ob er auch ausgeschlossen wäre, entscheidet
weiterhin ausschließlich ``evaluate.py`` beim jeweiligen Lauf.

VERWENDUNG (Vorbereitung, NICHT die Auswertung selbst):
  ``python scripts/filter_sensitivity_sammlung.py``
      -> schreibt data/forward_collection_sensitivity.json

  Der zweite (Sensitivitäts-)Lauf der eigentlichen Auswertung nimmt dann:
  ``python scripts/evaluate.py --sammlung data/forward_collection_sensitivity.json ...``

Deterministisch: keine Zufallsquelle, keine Uhrzeit-Abhängigkeit im
Filterergebnis selbst (nur der dokumentierte ``erzeugt_utc``-Metadaten-
Zeitstempel im Kopf der Ausgabedatei hängt vom Lauf-Zeitpunkt ab).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Dieselben drei Marker-Feldnamen wie in scripts/in_session.py,
# scripts/mark_episode_splits.py, scripts/mark_stale_market_records.py —
# hier NUR gelesen, nie gesetzt oder verändert.
MARKERS = ("in_session_creation", "episode_split_suspect", "stale_market_suspect")


def _traegt_marker(rec: Dict) -> bool:
    return any(rec.get(m) for m in MARKERS)


def filtere(coll: Dict) -> Tuple[Dict, List[Dict]]:
    """(gefilterte Sammlung, entfernte Records). Reine Funktion, kein I/O.

    Alle Top-Level-Felder außer ``records`` werden unverändert durchgereicht
    — ``evaluate.py`` liest ohnehin nur ``records`` (build_population) bzw.
    ``forward_collection.eval_counts``."""
    records = coll.get("records") or []
    behalten = [r for r in records if not _traegt_marker(r)]
    entfernt = [r for r in records if _traegt_marker(r)]
    neu = dict(coll)
    neu["records"] = behalten
    return neu, entfernt


def main(argv: Sequence[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Erzeugt die Sensitivitäts-Sammlung (ohne markierte "
                    "Records) als NEUE Datei — die Originalsammlung bleibt "
                    "unangetastet.")
    ap.add_argument("--sammlung", default="data/forward_collection.json",
                    help="Eingabe (nur lesend, wird NIE verändert)")
    ap.add_argument("--out", default="data/forward_collection_sensitivity.json",
                    help="Ausgabe (neue, zusätzliche Datei)")
    ap.add_argument("--now", default=None, help="Zeitstempel festnageln (Tests)")
    args = ap.parse_args(argv)

    in_path = REPO_ROOT / args.sammlung
    coll = json.loads(in_path.read_text(encoding="utf-8"))

    gefiltert, entfernt = filtere(coll)

    zaehlung: Dict[str, int] = {m: 0 for m in MARKERS}
    for rec in entfernt:
        for m in MARKERS:
            if rec.get(m):
                zaehlung[m] += 1

    gefiltert["sensitivity_filter"] = {
        "erzeugt_utc": args.now or _dt.datetime.now(_dt.timezone.utc)
                                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quelle": args.sammlung,
        "marker": list(MARKERS),
        "records_gesamt": len(coll.get("records") or []),
        "records_entfernt": len(entfernt),
        "records_verbleibend": len(gefiltert["records"]),
        "nennungen_je_marker": zaehlung,
        "hinweis": "Sicht auf dieselben Daten (Sensitivitätsanalyse gemäß "
                   "docs/validation_registry.md, Eintrag 07./08.08.2026) — "
                   "kein Record wurde in der Originaldatei verändert.",
    }

    out_path = REPO_ROOT / args.out
    out_path.write_text(
        json.dumps(gefiltert, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Gesamt: {len(coll.get('records') or [])} · "
          f"entfernt: {len(entfernt)} · "
          f"verbleibend: {len(gefiltert['records'])}")
    print(f"Je Marker (Mehrfachnennung möglich): {zaehlung}")
    print(f"Geschrieben: {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
