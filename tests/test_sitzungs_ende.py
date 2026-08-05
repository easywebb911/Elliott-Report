"""Sitzungs-Ende als Erwartungs-Anker — NUR für den Wächter.

ANLASS: der Kurs-Stand-Wächter (#71) rechnete gegen den letzten Handelstag
**bis einschließlich des Lauf-Datums**. Ein Lauf am Vormittag erwartete damit
eine Bar des laufenden Tages, dessen Sitzung noch gar nicht beendet war —
belegt an den Läufen vom 31.07. 11:16/11:22 UTC (US, gemeldet, obwohl die NYSE
zu der Zeit noch nicht geöffnet hatte).

DIE HARTE ZUSAGE DIESES PRs: das Sammlungs-Gate (#72) bleibt am
Kalendertag-Anker. Wäre es mitgelockert worden, wären Tages-Läufe wieder
sammelfähig — und da #68 den ERSTEN Lauf eines Kalendertags einfrieren lässt,
bestimmte ein Mittags-Recalculate den ``entry_close`` statt des Abend-Crons.
Ein eigener Abschnitt hält fest, dass das Gate diese Funktionen nicht anfasst.

Alle Soll-Werte sind von Hand nachgerechnet und im Docstring hergeleitet.
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import forward_collection as fc  # noqa: E402
import health_check as hc  # noqa: E402
import market_calendar as cal  # noqa: E402

UTC = _dt.timezone.utc


def _utc(text: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# 1 · Die Schwelle selbst — eine Minute davor / genau drauf / eine danach
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("markt, zone, schluss", [
    ("US", "America/New_York", (16, 0)),
    ("DE", "Europe/Berlin", (17, 30)),
])
@pytest.mark.parametrize("tag", ["2026-07-31", "2026-01-15"])   # Sommer + Winter
def test_die_schwelle_liegt_exakt_auf_der_schlusszeit(markt, zone, schluss, tag):
    """Von Hand: Sitzung gilt AB der Schlusszeit als beendet (>=), die
    Schlussauktion liegt auf der Marke."""
    d = _dt.date.fromisoformat(tag)
    h, m = schluss
    genau = _dt.datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo(zone))
    vorher = genau - _dt.timedelta(minutes=1)      # 16:00 -> 15:59, nicht 16:-1
    nachher = genau + _dt.timedelta(minutes=1)
    assert cal.sitzung_beendet(markt, vorher) is False
    assert cal.sitzung_beendet(markt, genau) is True
    assert cal.sitzung_beendet(markt, nachher) is True
    # … und der Erwartungs-Anker springt an derselben Stelle um einen Tag
    assert cal.letzter_beendeter_handelstag(markt, vorher) < d
    assert cal.letzter_beendeter_handelstag(markt, genau) == d
    assert cal.letzter_beendeter_handelstag(markt, nachher) == d


def test_die_maerkte_schliessen_zu_verschiedenen_zeiten():
    """31.07. 16:00 UTC = 18:00 Berlin (Xetra zu) = 12:00 New York (NYSE
    handelt noch). Genau dieser Versatz ist der Grund für markt-eigene Anker."""
    t = _utc("2026-07-31T16:00:00Z")
    assert cal.sitzung_beendet("DE", t) is True
    assert cal.sitzung_beendet("US", t) is False
    assert cal.letzter_beendeter_handelstag("DE", t) == _dt.date(2026, 7, 31)
    assert cal.letzter_beendeter_handelstag("US", t) == _dt.date(2026, 7, 30)


# ---------------------------------------------------------------------------
# 2 · Zeitzonen: echte Zonen, keine festen UTC-Abstände
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("markt, tag, sommer_utc, winter_utc", [
    # NYSE 16:00 lokal: Sommer (EDT, UTC-4) = 20:00 UTC · Winter (EST, UTC-5) = 21:00
    ("US", None, 20, 21),
    # Xetra 17:30 lokal: Sommer (CEST, UTC+2) = 15:30 UTC · Winter (CET, +1) = 16:30
    ("DE", None, 15, 16),
])
def test_die_schlusszeit_in_UTC_verschiebt_sich_mit_der_sommerzeit(
        markt, tag, sommer_utc, winter_utc):
    """Ein fester UTC-Abstand wäre ein halbes Jahr lang falsch."""
    # Sommer: 15. Juli
    sommer = _dt.datetime(2026, 7, 15, sommer_utc, 30 if markt == "DE" else 0, tzinfo=UTC)
    assert cal.sitzung_beendet(markt, sommer) is True
    assert cal.sitzung_beendet(markt, sommer - _dt.timedelta(minutes=1)) is False
    # Winter: 15. Januar
    winter = _dt.datetime(2026, 1, 15, winter_utc, 30 if markt == "DE" else 0, tzinfo=UTC)
    assert cal.sitzung_beendet(markt, winter) is True
    assert cal.sitzung_beendet(markt, winter - _dt.timedelta(minutes=1)) is False


def test_die_ZWISCHENWOCHE_mit_abweichendem_US_EU_abstand():
    """DER Fall, an dem ein fester Abstand auffliegt.

    Die USA stellen am **2. Sonntag im März** um (2026: 08.03.), die EU erst am
    **letzten Sonntag im März** (2026: 29.03.). Dazwischen liegt New York auf
    EDT (UTC−4), Berlin noch auf CET (UTC+1) — der Abstand ist **5** Stunden
    statt der sonst üblichen 6.

    Von Hand für Mittwoch, 18.03.2026:
      NYSE-Schluss 16:00 EDT  = 20:00 UTC
      Xetra-Schluss 17:30 CET = 16:30 UTC
    """
    tag = _dt.date(2026, 3, 18)
    ny = ZoneInfo("America/New_York"); be = ZoneInfo("Europe/Berlin")
    assert _dt.datetime(2026, 3, 18, 12, tzinfo=ny).utcoffset() == _dt.timedelta(hours=-4)
    assert _dt.datetime(2026, 3, 18, 12, tzinfo=be).utcoffset() == _dt.timedelta(hours=1)

    assert cal.sitzung_beendet("DE", _dt.datetime(2026, 3, 18, 16, 30, tzinfo=UTC)) is True
    assert cal.sitzung_beendet("DE", _dt.datetime(2026, 3, 18, 16, 29, tzinfo=UTC)) is False
    assert cal.sitzung_beendet("US", _dt.datetime(2026, 3, 18, 20, 0, tzinfo=UTC)) is True
    assert cal.sitzung_beendet("US", _dt.datetime(2026, 3, 18, 19, 59, tzinfo=UTC)) is False
    # Um 17:00 UTC ist Xetra zu, die NYSE handelt noch — ein Zustand, den ein
    # fester 6-Stunden-Abstand an diesem Tag falsch abbilden würde.
    t = _dt.datetime(2026, 3, 18, 17, 0, tzinfo=UTC)
    assert cal.letzter_beendeter_handelstag("DE", t) == tag
    assert cal.letzter_beendeter_handelstag("US", t) == _dt.date(2026, 3, 17)


def test_die_HERBST_zwischenwoche_ebenso():
    """EU stellt am letzten Sonntag im Oktober zurück (2026: 25.10.), die USA
    erst am 1. Sonntag im November (2026: 01.11.). Dazwischen: New York noch
    EDT (UTC−4), Berlin schon CET (UTC+1) — wieder 5 Stunden."""
    ny = ZoneInfo("America/New_York"); be = ZoneInfo("Europe/Berlin")
    assert _dt.datetime(2026, 10, 28, 12, tzinfo=ny).utcoffset() == _dt.timedelta(hours=-4)
    assert _dt.datetime(2026, 10, 28, 12, tzinfo=be).utcoffset() == _dt.timedelta(hours=1)
    assert cal.sitzung_beendet("US", _dt.datetime(2026, 10, 28, 20, 0, tzinfo=UTC)) is True
    assert cal.sitzung_beendet("DE", _dt.datetime(2026, 10, 28, 16, 30, tzinfo=UTC)) is True


# ---------------------------------------------------------------------------
# 3 · Wochenende, Feiertag, Rückstands-Zählung
# ---------------------------------------------------------------------------
def test_am_wochenende_ist_der_freitag_der_anker():
    """Samstag 01.08.2026, 09:00 UTC — die letzte beendete Sitzung ist Freitag."""
    t = _utc("2026-08-01T09:00:00Z")
    for markt in ("US", "DE"):
        assert cal.letzter_beendeter_handelstag(markt, t) == _dt.date(2026, 7, 31)
        assert cal.handelstage_rueckstand_sitzung("2026-07-31", markt, t) == 0


def test_montag_frueh_haengt_am_freitag():
    """Montag 03.08., 06:00 UTC: noch keine Sitzung beendet -> Freitag."""
    t = _utc("2026-08-03T06:00:00Z")
    for markt in ("US", "DE"):
        assert cal.letzter_beendeter_handelstag(markt, t) == _dt.date(2026, 7, 31)
    # Ein Freitags-Stand ist damit AKTUELL, ein Donnerstags-Stand 1 zurück.
    assert cal.handelstage_rueckstand_sitzung("2026-07-31", "US", t) == 0
    assert cal.handelstage_rueckstand_sitzung("2026-07-30", "US", t) == 1


def test_der_voll_schliesstag_wird_uebersprungen():
    """25.12.2026 (Freitag) ist gemeinsamer Voll-Schließtag. Am 26.12. früh ist
    die letzte beendete Sitzung der **24.12.**"""
    assert cal.is_full_closure(_dt.date(2026, 12, 25)) is not None
    t = _dt.datetime(2026, 12, 26, 8, 0, tzinfo=UTC)
    for markt in ("US", "DE"):
        assert cal.letzter_beendeter_handelstag(markt, t) == _dt.date(2026, 12, 24)


@pytest.mark.parametrize("bar, soll", [
    ("2026-07-31", 0),   # Freitag = der Anker selbst
    ("2026-07-30", 1),
    ("2026-07-29", 2),
    ("2026-08-05", 0),   # Zukunft ergibt 0, nie negativ
])
def test_die_rueckstands_zaehlung_ist_dieselbe_wie_beim_kalender_anker(bar, soll):
    """Von Hand ab Freitag 31.07. rückwärts. Wichtig: es entsteht KEIN zweiter
    Begriff von „Handelstag zurück" — beide Anker zählen mit derselben
    Hilfsfunktion."""
    t = _utc("2026-07-31T20:30:00Z")   # nach beiden Schlusszeiten
    assert cal.handelstage_rueckstand_sitzung(bar, "US", t) == soll
    # Gegenprobe: der Kalendertag-Anker kommt am Abend auf dasselbe
    assert cal.handelstage_rueckstand(bar, "2026-07-31") == soll


# ---------------------------------------------------------------------------
# 4 · Fail-soft — nie raten, nie stumm werden
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("markt", ["XX", "", None, "us "])
def test_ein_unbekannter_markt_ergibt_None_statt_einer_annahme(markt):
    t = _utc("2026-07-31T20:00:00Z")
    assert cal.sitzung_beendet(markt, t) is None
    assert cal.letzter_beendeter_handelstag(markt, t) is None
    assert cal.handelstage_rueckstand_sitzung("2026-07-30", markt, t) is None


@pytest.mark.parametrize("jetzt", [
    None, "2026-07-31T20:00:00Z", 12345,
    _dt.datetime(2026, 7, 31, 20, 0),           # NAIV -> keine Zone -> None
])
def test_ohne_zeitzonen_behaftete_zeit_wird_nicht_geraten(jetzt):
    assert cal.sitzung_beendet("US", jetzt) is None
    assert cal.letzter_beendeter_handelstag("US", jetzt) is None


def test_der_waechter_faellt_auf_den_kalender_anker_zurueck():
    """Ist das Sitzungs-Ende nicht bestimmbar (hier: unbekannter Markt), prüft
    die Regel weiter — mit dem bisherigen Anker. Nie „gar keine Prüfung"."""
    r = {"run_timestamp_utc": "2026-08-04T22:42:32Z",
         "markets": {"XX": {"diag": {"last_bar_date": "2026-07-31"}}}}
    f = hc.check_bar_freshness(r)
    assert len(f) == 1 and f[0]["market"] == "XX"
    assert f[0]["detail"]["expected_bar_date"] == "2026-08-04"
    assert f[0]["detail"]["lag_trading_days"] == 2


def test_ein_kaputter_zeitstempel_laesst_die_regel_nicht_verstummen():
    r = {"run_timestamp_utc": "2026-08-04",      # Datum ohne Uhrzeit
         "markets": {"DE": {"diag": {"last_bar_date": "2026-07-31"}}}}
    f = hc.check_bar_freshness(r)
    assert len(f) == 1, "ohne Uhrzeit gilt der Kalendertag-Anker"
    assert f[0]["detail"]["expected_bar_date"] == "2026-08-04"


# ---------------------------------------------------------------------------
# 5 · KEINE Karenzzeit
# ---------------------------------------------------------------------------
def test_direkt_nach_schluss_wird_die_fehlende_bar_SOFORT_gemeldet():
    """Eine Karenz würde den GRACE_HOURS-Fehler wiederholen: falscher Anker,
    Warnung gedämpft. Dass die Quelle noch nichts liefert, ist ein QUELLEN-
    Problem und bleibt ein gemeldeter Rückstand.

    31.07. 15:31 UTC = 17:31 Berlin, eine Minute nach Xetra-Schluss."""
    r = {"run_timestamp_utc": "2026-07-31T15:31:00Z",
         "markets": {"DE": {"diag": {"last_bar_date": "2026-07-30"}}}}
    f = hc.check_bar_freshness(r)
    assert len(f) == 1 and f[0]["detail"]["lag_trading_days"] == 1
    assert f[0]["detail"]["expected_bar_date"] == "2026-07-31"


def test_es_gibt_keine_karenz_konstante():
    quelle = (ROOT / "scripts/market_calendar.py").read_text(encoding="utf-8")
    gesundheit = (ROOT / "scripts/health_check.py").read_text(encoding="utf-8")
    for wort in ("KARENZ", "SESSION_GRACE", "BAR_GRACE"):
        assert wort not in quelle and wort not in gesundheit


# ---------------------------------------------------------------------------
# 6 · Verkürzte Handelstage: datierte Grenze, Richtung festgenagelt
# ---------------------------------------------------------------------------
def test_verkuerzte_handelstage_wirken_nur_NACHSICHTIG():
    """Bewusst nicht abgebildet (Registry 05.08.2026). Die NYSE schließt am Tag
    nach Thanksgiving (27.11.2026) um 13:00 ET; wir nehmen 16:00 an.

    Folge, hier festgenagelt: um 14:00 ET gilt die Sitzung als NICHT beendet,
    der Anker ist der Vortag — die Erwartung ist also **zu nachsichtig**. Sie
    kann an diesen Tagen KEINEN Fehlalarm erzeugen, nur eine Meldung um
    Stunden verzögern. Ein Test, der die Richtung offenlässt, wäre wertlos.
    """
    t = _dt.datetime(2026, 11, 27, 14, 0, tzinfo=ZoneInfo("America/New_York"))
    assert cal.sitzung_beendet("US", t) is False
    assert cal.letzter_beendeter_handelstag("US", t) == _dt.date(2026, 11, 26)
    # Ein Stand von gestern erzeugt damit KEINEN Rückstand (nachsichtig) …
    assert cal.handelstage_rueckstand_sitzung("2026-11-26", "US", t) == 0
    # … und der Abend-Cron (21:45 UTC = 16:45 ET) liegt nach JEDEM dieser
    # Schlüsse, ist also nicht betroffen.
    abends = _dt.datetime(2026, 11, 27, 21, 45, tzinfo=UTC)
    assert cal.sitzung_beendet("US", abends) is True
    assert cal.letzter_beendeter_handelstag("US", abends) == _dt.date(2026, 11, 27)


# ---------------------------------------------------------------------------
# 7 · DAS GATE BLEIBT UNBERÜHRT — die Populations-Garantie
# ---------------------------------------------------------------------------
def test_das_gate_kennt_die_sitzungs_funktionen_nicht():
    """Statischer Beleg: die Sammlung liest weder Sitzungs-Ende noch Zeitzonen."""
    quelle = (ROOT / "scripts/forward_collection.py").read_text(encoding="utf-8")
    for name in ("sitzung_beendet", "letzter_beendeter_handelstag",
                 "handelstage_rueckstand_sitzung", "MARKET_SESSIONS", "zoneinfo"):
        assert name not in quelle, f"die Sammlung greift auf {name} zu"


def test_das_gate_liest_weiter_das_unveraenderte_diag_feld():
    quelle = (ROOT / "scripts/forward_collection.py").read_text(encoding="utf-8")
    assert 'lag = (market.get("diag") or {}).get("bar_lag_trading_days")' in quelle
    pipeline = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    assert 'diag["bar_lag_trading_days"] = cal.handelstage_rueckstand(' in pipeline
    assert "handelstage_rueckstand_sitzung" not in pipeline, \
        "die Pipeline darf den Wächter-Anker NICHT in diag schreiben"


@pytest.mark.parametrize("ts, bar, soll", [
    # Genau die Läufe, deren WÄCHTER-Bewertung dieser PR ändert — das Gate
    # entscheidet dort unverändert. Von Hand: Kalendertag-Anker.
    ("2026-07-31T11:16:07Z", "2026-07-30", ["US"]),   # Vormittag: Gate sperrt weiter
    ("2026-08-04T04:46:23Z", "2026-07-31", ["US"]),
    ("2026-07-31T22:40:44Z", "2026-07-30", ["US"]),   # Abend: unverändert
])
def test_das_gate_entscheidet_bei_den_geaenderten_laeufen_gleich(ts, bar, soll):
    r = {"run_timestamp_utc": ts,
         "markets": {"US": {"diag": {"last_bar_date": bar,
                                     "bar_lag_trading_days":
                                         cal.handelstage_rueckstand(bar, ts[:10])}}}}
    assert sorted(fc.stale_markets(r)) == soll


def test_gate_identitaet_ueber_die_REALE_historie():
    """Das Gate entscheidet über die REALE Historie unverändert.

    Jeder committete Report läuft durch ``fc.stale_markets``; das Ergebnis muss
    exakt dem entsprechen, was ``diag.bar_lag_trading_days >= 1`` liefert.

    GENAU GENOMMEN (Guardian-Nit 05.08.2026): dieser Test belegt, dass
    ``stale_markets`` sein VERHALTEN nicht geändert hat — nicht, dass
    ``bar_lag_trading_days`` richtig gerechnet wird. Das Zweite deckt
    ``test_das_gate_liest_weiter_das_unveraenderte_diag_feld`` ab (die Pipeline
    schreibt das Feld weiter aus ``handelstage_rueckstand``). Erst beide
    zusammen sind die Populations-Garantie; ein Test allein verspräche zu viel.
    """
    shas = subprocess.run(["git", "log", "--format=%H", "--", "docs/data/report.json"],
                          capture_output=True, text=True, cwd=ROOT).stdout.split()
    gesehen, geprueft = set(), 0
    for sha in reversed(shas):
        roh = subprocess.run(["git", "show", f"{sha}:docs/data/report.json"],
                             capture_output=True, text=True, cwd=ROOT).stdout
        if not roh.strip():
            continue
        try:
            r = json.loads(roh)
        except Exception:  # noqa: BLE001
            continue
        ts = r.get("run_timestamp_utc")
        if not ts or ts in gesehen:
            continue
        gesehen.add(ts)
        geprueft += 1
        erwartet = sorted(
            k for k, m in (r.get("markets") or {}).items()
            if isinstance(m, dict)
            and isinstance((m.get("diag") or {}).get("bar_lag_trading_days"), int)
            and (m["diag"]["bar_lag_trading_days"] or 0) >= 1)
        assert sorted(fc.stale_markets(r)) == erwartet, \
            f"{ts}: Gate weicht vom Kalendertag-Anker ab"
    assert geprueft >= 60, f"nur {geprueft} Läufe geprüft — Historie unerwartet kurz"
