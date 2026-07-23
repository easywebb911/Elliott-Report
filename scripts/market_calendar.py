"""Handelskalender — Wochenend-/Feiertags-Gate + kalenderbewusste Staleness.

EINE gemeinsame Quelle für beide Mechaniken, damit sie nicht divergieren:
  - Das Feiertags-Gate (Pipeline) überspringt gemeinsame Voll-Schließtage.
  - Der Staleness-Wächter (notify.py) rechnet gegen den letzten ERWARTETEN Lauf
    (statt fix 30 h) → keine Wochenend-/Feiertags-Fehlalarme.

VOLL-SCHLIESSTAGE (beide Märkte zu): nur die Schnittmenge von NYSE UND Xetra.
Einzelmarkt-Feiertage (z. B. Ostermontag/1. Mai = nur Xetra zu; Thanksgiving/
July 4 = nur NYSE zu) sind hier NICHT gelistet — dann läuft der Report normal,
der offene Markt liefert, fail-soft deckt den geschlossenen ab.

Quelle: NYSE-Handelskalender + Deutsche-Börse-(Xetra)-Handelskalender,
Schnittmenge der ganztägigen Schließungen. Stand: 23.07.2026 (Wissensbasis).
Gemeinsame Voll-Schließtage sind faktisch: Neujahr (1.1.), Karfreitag,
1. Weihnachtstag (25.12.). Andere Tage sind Einzelmarkt-Feiertage.

WARTUNG (Squeeze-Lektion 6b — Liste läuft sonst still aus): ab
HOLIDAY_LIST_EXPIRES loggt der Lauf eine Erneuerungs-Warnung.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

# Tägliche Lauf-Zeit (UTC), passend zu daily.yml-Cron "45 21 * * 1-5".
RUN_HOUR = 21
RUN_MIN = 45
# Zeitpuffer, bis ein erwarteter Lauf als abgeschlossen/committet gilt.
GRACE_HOURS = 6
# Toleranz, ab der ein Report als "vor dem letzten erwarteten Lauf" gilt.
TOLERANCE_HOURS = 6

# Gemeinsame Voll-Schließtage NYSE ∩ Xetra (ISO-Datum -> Name). Nur diese
# überspringt das Gate; sie fließen auch in den erwarteten-Lauf-Kalender ein.
FULL_CLOSURE = {
    "2026-01-01": "Neujahr",
    "2026-04-03": "Karfreitag",
    "2026-12-25": "1. Weihnachtstag",
    "2027-01-01": "Neujahr",
    "2027-03-26": "Karfreitag",
    "2027-12-25": "1. Weihnachtstag",
}
# Ab hier ist die Liste bald erschöpft -> Erneuerungs-Warnung im Lauf.
HOLIDAY_LIST_EXPIRES = _dt.date(2027, 12, 1)


def is_full_closure(d: _dt.date) -> Optional[str]:
    """Name des gemeinsamen Voll-Schließtags oder None."""
    return FULL_CLOSURE.get(d.isoformat())


def holiday_list_expiring(today: _dt.date) -> bool:
    """True, wenn die Feiertagsliste erneuert werden muss (>= Ablauf-Datum)."""
    return today >= HOLIDAY_LIST_EXPIRES


def is_trading_day(d: _dt.date) -> bool:
    """Werktag (Mo–Fr) und kein gemeinsamer Voll-Schließtag."""
    return d.weekday() < 5 and is_full_closure(d) is None


def parse_ts(ts_iso) -> Optional[_dt.datetime]:
    """Report-Zeitstempel '%Y-%m-%dT%H:%M:%SZ' -> aware UTC. None wenn kaputt."""
    if not ts_iso:
        return None
    try:
        return _dt.datetime.strptime(ts_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def last_expected_run(now: _dt.datetime) -> Optional[_dt.datetime]:
    """Zeitpunkt des jüngsten ERWARTETEN Daily-Laufs vor `now`.

    = jüngster vergangener Handelstag (Mo–Fr, kein Voll-Schließtag) um RUN_HOUR:
    RUN_MIN UTC, dessen Fertigstellungs-Puffer (GRACE_HOURS) bereits verstrichen
    ist. Wochenenden/Feiertage werden übersprungen → an Mo-früh ist der letzte
    erwartete Lauf der Freitag, kein Fehlalarm. None, falls (theoretisch) keiner
    in ~1 Jahr gefunden wird.
    """
    grace = _dt.timedelta(hours=GRACE_HOURS)
    cand = now.replace(hour=RUN_HOUR, minute=RUN_MIN, second=0, microsecond=0)
    for _ in range(400):  # Sicherheits-Schranke (~1 Jahr zurück)
        if cand + grace <= now and is_trading_day(cand.date()):
            return cand
        cand -= _dt.timedelta(days=1)
    return None


def is_stale(report_ts_iso, now: _dt.datetime) -> bool:
    """Kalenderbewusst: Report älter als der letzte ERWARTETE Lauf?

    - unlesbarer/fehlender Zeitstempel -> True (Staleness-Signal).
    - kein erwarteter Lauf bestimmbar -> False (nie fälschlich alarmieren).
    - sonst: stale, wenn report_ts mehr als TOLERANCE_HOURS VOR dem letzten
      erwarteten Lauf liegt (d. h. dieser Lauf hat nicht frisch committet).
    """
    ts = parse_ts(report_ts_iso)
    if ts is None:
        return True
    exp = last_expected_run(now)
    if exp is None:
        return False
    return ts < exp - _dt.timedelta(hours=TOLERANCE_HOURS)


def age_hours(report_ts_iso, now: _dt.datetime) -> Optional[float]:
    ts = parse_ts(report_ts_iso)
    if ts is None:
        return None
    return (now - ts).total_seconds() / 3600.0
