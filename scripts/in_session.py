#!/usr/bin/env python3
"""In-Session-Marker: lief der ANLEGENDE Lauf mitten in der Börsensitzung?

HINTERGRUND (07.08.2026, Befund derselben Session). 34 von 69 Bestands-Records
wurden in Läufen angelegt, deren Report-Stempel INNERHALB der regulären Sitzung
des eigenen Markt-Kalenders lag. Die Quelle liefert dann bereits eine Zeile für
den laufenden Tag — eine **noch nicht fertige** Bar. Alles, was die Anlage
einfriert, ist damit ein Zwischenstand:

  * ``entry_close`` (gemessen: Median 0,36 %, Maximum 1,58 % Abweichung vom
    späteren echten Schlusskurs, kein Vorzeichen-Bias)
  * ``score_heuristic`` (gemessen: 11 von 16 exakt gleich, Maximum 0,60 Punkte)
  * ``confluence``, ``vol_*``, ``ambiguity_n*``, ``agent_concern_level``
  * und die AUSWAHL selbst: ``target_exceeded``-Filter und Ranking liefen auf
    demselben vorläufigen Close — WELCHE Ticker überhaupt in die Top-5 kamen,
    hing am Abrufzeitpunkt. Dieser Selektionseffekt ist rückwirkend nicht
    messbar; er ist in der Registry als Grenze benannt.

BESCHLUSS EASY (07.08.2026): **EIN Marker für den ganzen Zustand, kein
Ausschluss, nichts heilen.** Wie markierte Records in der Auswertung behandelt
werden, entscheidet die gemeinsame Marker-Entscheidung VOR der ersten echten
Auswertung — jetzt mit DREI Markern (``episode_split_suspect``,
``stale_market_suspect``, ``in_session_creation``) statt zwei.

DAS FELD ÄNDERT KEINE BERECHNUNG. Es ist additiv, wird NIE entfernt und NIE
geheilt (MET/D/PRU-Prinzip). ``mature_record``, ``evaluate.py``, das #72/#75-Gate
und alle bestehenden Felder bleiben unberührt; ``FROZEN_FIELDS`` kennt es nicht,
die Auswertung v1 ist eingefroren.

WARUM ``false`` NICHT GESCHRIEBEN WIRD: Abwesenheit = sauber. So sind Alt- und
Neubestand gleich lesbar, und es hängt sich kein Feld an 35 unbeteiligte
Records (dieselbe Begründung wie bei ``skipped_bars``, Variante b, #72).

WARUM DIESES MODUL UND NICHT ``forward_collection``: ``tests/test_sitzungs_ende.py``
verbietet der Sammlung statisch jeden Zugriff auf ``MARKET_SESSIONS``/``zoneinfo``
und die Sitzungs-Funktionen — der Wächter der #75-Populations-Garantie („eine
Kalenderfunktion, zwei Erwartungs-Anker"; das Gate bleibt am Kalendertag-Anker).
Dieser Marker etikettiert nur und gatet nichts, aber der Wächter soll scharf
bleiben. Die Markierung läuft deshalb in ``elliott_pipeline.main()`` — NACH
``update_forward_collection`` und VOR ``write_collection``, genau wie die
Score-Alert-Flanke. Ein Record erreicht die Platte nie ohne seinen Marker.
"""
from __future__ import annotations

import datetime as _dt
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import market_calendar as cal  # noqa: E402

log = logging.getLogger("in_session")

MARKER = "in_session_creation"
MARKER_UTC = "in_session_creation_marked_utc"

# ERÖFFNUNGSZEITEN: im Repo NICHT vorhanden — `MARKET_SESSIONS` kennt nur den
# Schluss (er ist der Anker des Wächters aus #75). Hiermit festgelegt (Easy,
# 07.08.2026) und hier zentral, damit es keine zweite Fassung gibt.
# Die SCHLUSSZEITEN kommen weiterhin aus `cal.MARKET_SESSIONS` — eine Quelle,
# kein Nachbau; ändert jemand dort den Schluss, wandert dieser Marker mit.
MARKET_OPEN = {
    "US": _dt.time(9, 30),    # NYSE 09:30 America/New_York
    "DE": _dt.time(9, 0),     # Xetra 09:00 Europe/Berlin
}

# GRENZEN laut Auftrag: exklusiv Eröffnung, exklusiv Schluss.
# Der Schluss deckt sich damit mit `cal.sitzung_beendet` (dort `>=`: genau auf
# der Marke gilt die Sitzung als beendet) — kein zweiter Begriff von „Schluss".
# Verglichen wird die volle Ortszeit inkl. Sekunden, NICHT ein (Stunde, Minute)-
# Tupel: 09:30:30 liegt sonst auf (9, 30) und fiele fälschlich aus dem Fenster.


def _parse_utc(stempel) -> Optional[_dt.datetime]:
    """ISO-Stempel (``…Z`` oder mit Offset) -> aware datetime. None = unlesbar."""
    if isinstance(stempel, _dt.datetime):
        return stempel if stempel.tzinfo else None
    if not isinstance(stempel, str) or not stempel.strip():
        return None
    roh = stempel.strip()
    try:
        dt = _dt.datetime.fromisoformat(roh.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def ist_in_sitzung(markt, stempel) -> Optional[bool]:
    """Lag ``stempel`` in der regulären Sitzung von ``markt``?

    ``None`` = NICHT BERECHENBAR (unbekannter Markt, unlesbarer/naiver Stempel,
    fehlende tzdata). Der Aufrufer muss diesen Fall LAUT behandeln — nie still
    als „nicht in Sitzung" verbuchen, sonst verschwindet ein Marker geräuschlos.
    """
    schluss_cfg = cal.MARKET_SESSIONS.get(str(markt or "").upper())
    oeffnung = MARKET_OPEN.get(str(markt or "").upper())
    dt = _parse_utc(stempel)
    if schluss_cfg is None or oeffnung is None or dt is None:
        return None
    try:
        from zoneinfo import ZoneInfo

        lokal = dt.astimezone(ZoneInfo(schluss_cfg["tz"]))
    except Exception:  # noqa: BLE001 — fehlende tzdata o. Ä. -> fail-soft
        return None
    h, m = schluss_cfg["close"]
    schluss = _dt.time(h, m)
    jetzt = lokal.time()
    return oeffnung < jetzt < schluss


def record_key(rec: Dict) -> Tuple:
    """Identität wie bei ``mark_stale_market_records`` — NICHT ``episode_id``
    (die kollidiert real, z. B. zweimal ``ADS.DE@2026-07-24``)."""
    return (rec.get("ticker"), rec.get("created_utc"))


def betroffene_records(records: Sequence[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """(zu markieren, nicht berechenbar) — rein, deterministisch, ohne I/O.

    Das Kriterium braucht ausschließlich ``created_utc`` und ``market`` des
    Records. ``created_utc`` IST der Report-Stempel des anlegenden Laufs; dass
    das über den gesamten Bestand gilt, prüft ein eigener Test gegen die
    committete Report-Historie (kein Vertrauen, ein Beleg).
    """
    treffer: List[Dict] = []
    unklar: List[Dict] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        urteil = ist_in_sitzung(rec.get("market"), rec.get("created_utc"))
        if urteil is None:
            unklar.append(rec)
        elif urteil:
            treffer.append(rec)
    return treffer, unklar


def markiere(records: Sequence[Dict], marked_utc: str) -> Tuple[int, List[Dict]]:
    """Setzt den Marker in-place. Ändert AUSSCHLIESSLICH die zwei Marker-Felder.

    Idempotent: ein bereits markierter Record behält seinen URSPRÜNGLICHEN
    ``marked_utc``-Stempel — die Markierung ist ein Ereignis, das genau einmal
    stattgefunden hat, und darf sich nicht bei jedem Lauf neu datieren.
    Rückgabe: (neu gesetzt, nicht berechenbare Records).
    """
    treffer, unklar = betroffene_records(records)
    gesetzt = 0
    for rec in treffer:
        if rec.get(MARKER) is True:
            continue
        rec[MARKER] = True
        rec.setdefault(MARKER_UTC, marked_utc)
        gesetzt += 1
    for rec in unklar:
        log.warning(
            "in_session nicht berechenbar (Record bleibt unmarkiert, "
            "Anlage NICHT blockiert): ticker=%s market=%r created_utc=%r",
            rec.get("ticker"), rec.get("market"), rec.get("created_utc"))
    return gesetzt, unklar


def entferne_marker(records: Sequence[Dict]) -> int:
    """RÜCKWEG: entfernt beide Marker-Felder restlos. Sonst nichts."""
    entfernt = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        weg = False
        for feld in (MARKER, MARKER_UTC):
            if feld in rec:
                del rec[feld]
                weg = True
        entfernt += bool(weg)
    return entfernt


def markiere_neue_records(coll: Dict, run_utc: str) -> Tuple[int, List[Dict]]:
    """LAUFENDE Markierung (Teil B): nur die in DIESEM Lauf angelegten Records.

    Aufruf in ``elliott_pipeline.main()`` nach ``update_forward_collection`` und
    vor ``write_collection``. ``run_utc`` ist derselbe Stempel, den
    ``_new_record`` als ``created_utc`` schreibt — die Auswahl ist damit exakt
    „was dieser Lauf angelegt hat", ohne Vorher/Nachher-Vergleich.

    Kein Gate, kein Blockieren: der Record entsteht in jedem Fall, auch wenn der
    Vergleich scheitert — dann steht eine Warnung im Log.
    """
    neu = [r for r in (coll.get("records") or [])
           if isinstance(r, dict) and r.get("created_utc") == run_utc]
    return markiere(neu, run_utc)
