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


def _als_datum(wert) -> Optional[_dt.date]:
    """'YYYY-MM-DD' oder date -> date. None bei allem anderen (fail-soft)."""
    if isinstance(wert, _dt.date) and not isinstance(wert, _dt.datetime):
        return wert
    if isinstance(wert, _dt.datetime):
        return wert.date()
    try:
        return _dt.date.fromisoformat(str(wert))
    except Exception:  # noqa: BLE001
        return None


def letzter_handelstag(bis) -> Optional[_dt.date]:
    """Der jüngste Handelstag <= ``bis`` (``bis`` selbst zählt mit).

    Für die Frage „von welchem Tag SOLLTEN die Kurse stammen?" (04.08.2026).
    An einem Samstag/Sonntag/Voll-Schließtag ist das der letzte davorliegende
    Werktag — deshalb erzeugt ein Freitags-Kursstand am Wochenende **keinen**
    Rückstand und damit keinen Fehlalarm.
    """
    d = _als_datum(bis)      # nimmt date ODER 'YYYY-MM-DD' (ein Eingang)
    if d is None:
        return None
    for _ in range(30):          # 30 Tage decken jede Feiertagsbrücke ab
        if is_trading_day(d):
            return d
        d -= _dt.timedelta(days=1)
    return None                  # pragma: no cover — defensiv


def handelstage_rueckstand(bar_datum, bis) -> Optional[int]:
    """Wie viele HANDELSTAGE liegt ein Kursstand zurück?

    Gezählt werden die Handelstage **nach** ``bar_datum`` bis einschließlich
    des letzten Handelstags <= ``bis``. Beispiele (``bis`` = Dienstag):
      Dienstags-Stand -> 0 · Montags-Stand -> 1 · Freitags-Stand -> 2.
    Am Sonntag mit Freitags-Stand -> 0 (der letzte Handelstag IST der Freitag).

    Ein Kursstand in der Zukunft ergibt 0, nicht negativ: das wäre kein
    Rückstand, und ein Alarm dafür gehört einer anderen Regel.
    None = nicht bestimmbar (unlesbares Datum) -> der Aufrufer meldet nichts.
    """
    bar = _als_datum(bar_datum)
    ziel = _als_datum(bis)
    if bar is None or ziel is None:
        return None
    erwartet = letzter_handelstag(ziel)
    if erwartet is None:
        return 0
    return _zaehle_handelstage(bar, erwartet)


def _zaehle_handelstage(bar: _dt.date, erwartet: _dt.date) -> int:
    """Handelstage NACH ``bar`` bis einschließlich ``erwartet``.

    Ausgelagert (05.08.2026), damit der Sitzungs-Ende-Anker exakt DIESELBE
    Zählweise benutzt — sonst entstünden zwei Begriffe von „Handelstag zurück".
    """
    if bar >= erwartet:
        return 0
    n, d = 0, bar + _dt.timedelta(days=1)
    while d <= erwartet:
        if is_trading_day(d):
            n += 1
        d += _dt.timedelta(days=1)
    return n


# ---------------------------------------------------------------------------
# SITZUNGS-ENDE (05.08.2026) — Erwartungs-Anker NUR für den Wächter
# ---------------------------------------------------------------------------
# Anlass: der Kurs-Stand-Wächter rechnete gegen den letzten Handelstag BIS
# EINSCHLIESSLICH des Lauf-Datums. Ein Lauf am Vormittag erwartete damit eine
# Bar des laufenden Tages, dessen Sitzung noch gar nicht beendet war — belegt
# an den Läufen vom 31.07. 11:16/11:22 (US, crit), zu denen die NYSE noch nicht
# einmal geöffnet hatte.
#
# ERGÄNZUNG, KEIN ERSATZ: `is_trading_day` bleibt die EINE Definition von
# „Handelstag". Hier kommt nur die Frage dazu, ob die Sitzung dieses Tages zur
# Lauf-Zeit schon vorbei war.
#
# DAS GATE (#72) BENUTZT DIESE FUNKTIONEN NICHT — es bleibt am Kalendertag-Anker
# (`letzter_handelstag`). Siehe validation_registry.md, Eintrag vom 05.08.2026:
# ein gelockertes Gate machte Mittags-Läufe sammelfähig, und da der ERSTE Lauf
# eines Kalendertags den `entry_close` einfriert, kämen ältere Einfrier-Kurse in
# die Validierungs-Population.
#
# ZEITZONEN über zoneinfo, NICHT über feste UTC-Abstände: USA und EU stellen die
# Sommerzeit an verschiedenen Terminen um (US: 2. So März / 1. So Nov; EU:
# letzter So März / letzter So Okt). In den Zwischenwochen wäre jeder feste
# Abstand falsch.
#
# DATIERTE GRENZE: verkürzte Handelstage (NYSE 13:00 ET am Tag nach Thanksgiving
# und an Heiligabend; Xetra früher am 24./31.12.) sind NICHT abgebildet. Die
# Abweichung wirkt nur in EINE Richtung — die Erwartung ist dort zu nachsichtig,
# nie zu streng, kann also keinen Fehlalarm erzeugen (Test hält das fest).
MARKET_SESSIONS = {
    "US": {"tz": "America/New_York", "close": (16, 0)},    # NYSE 16:00 ET
    "DE": {"tz": "Europe/Berlin", "close": (17, 30)},      # Xetra 17:30 Ortszeit
}


def _sitzung(markt) -> Optional[dict]:
    return MARKET_SESSIONS.get(str(markt or "").upper())


def sitzung_beendet(markt, jetzt) -> Optional[bool]:
    """War die Sitzung des LOKALEN Kalendertags von ``jetzt`` schon beendet?

    ``jetzt``: aware datetime (UTC oder beliebige Zone). None = nicht
    bestimmbar (unbekannter Markt, naives/unlesbares Datum) — der Aufrufer
    fällt dann auf den Kalendertag-Anker zurück, statt zu raten.

    Genau ZUR Schlusszeit gilt die Sitzung als beendet (>=): die Schlussauktion
    liegt auf der Marke, danach ist der Tag zu.
    """
    cfg = _sitzung(markt)
    if cfg is None or not isinstance(jetzt, _dt.datetime) or jetzt.tzinfo is None:
        return None
    try:
        from zoneinfo import ZoneInfo
        lokal = jetzt.astimezone(ZoneInfo(cfg["tz"]))
    except Exception:  # noqa: BLE001 — fehlende tzdata o. Ä. -> fail-soft
        return None
    h, m = cfg["close"]
    return (lokal.hour, lokal.minute) >= (h, m)


def letzter_beendeter_handelstag(markt, jetzt):
    """Der jüngste Handelstag, dessen Sitzung zu ``jetzt`` BEENDET war.

    Das ist der Erwartungs-Anker des Wächters: von diesem Tag darf eine fertige
    Tages-Bar verlangt werden. Läuft der Report vormittags, ist es der VORTAG —
    und der bekannte Fehlalarm entfällt.

    None = nicht bestimmbar; der Aufrufer nimmt dann ``letzter_handelstag``.
    """
    cfg = _sitzung(markt)
    if cfg is None or not isinstance(jetzt, _dt.datetime) or jetzt.tzinfo is None:
        return None
    try:
        from zoneinfo import ZoneInfo
        lokal = jetzt.astimezone(ZoneInfo(cfg["tz"]))
    except Exception:  # noqa: BLE001
        return None
    heute = lokal.date()
    fertig = sitzung_beendet(markt, jetzt)
    # Ist heute ein Handelstag, dessen Sitzung noch LÄUFT (oder noch nicht
    # begonnen hat), zählt er nicht — dann ab dem Vortag suchen.
    if is_trading_day(heute) and not fertig:
        return letzter_handelstag(heute - _dt.timedelta(days=1))
    return letzter_handelstag(heute)


def handelstage_rueckstand_sitzung(bar_datum, markt, jetzt) -> Optional[int]:
    """Rückstand gegen das SITZUNGS-ENDE statt gegen den Kalendertag.

    Dieselbe Zählweise wie ``handelstage_rueckstand`` — nur der Ziel-Tag kommt
    aus ``letzter_beendeter_handelstag``. None = nicht bestimmbar.
    """
    bar = _als_datum(bar_datum)
    erwartet = letzter_beendeter_handelstag(markt, jetzt)
    if bar is None or erwartet is None:
        return None
    return _zaehle_handelstage(bar, erwartet)


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
