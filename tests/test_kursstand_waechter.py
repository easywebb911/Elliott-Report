"""Der Report darf nie wieder still auf veralteten Kursen rechnen.

ANLASS (Befund 04.08.2026): am 04.08. standen **beide** Märkte auf dem
Kursstand vom 31.07. — die Montags-Zeile kam von der Quelle nicht-finit und
wurde von der Härtung zu Recht verworfen. Danach rechneten Score, Filter und
Anzeige auf Freitags-Kursen, je ein Ticker fiel dadurch aus den Top 5 — und der
Health-Check meldete ``status: ok``. Er prüfte Kandidatenzahl, Fetch-Fehler und
tote Ticker, aber **nicht das Bar-Datum**; ``cal.is_stale`` misst den
Report-Zeitstempel, nicht die Kurse.

Zwei Netze, beide hier:
  (a) die Health-Regel ``check_bar_freshness`` — Befund im Lauf-Status und im
      normalen Befund-Push, mit dem üblichen Flanken-Verhalten;
  (b) der Frontend-Hinweis an „Kurse vom" — er liest die FERTIGE Zahl aus dem
      Report, damit der Handelskalender nicht ein zweites Mal in JavaScript
      existiert.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import health_check as hc  # noqa: E402
import market_calendar as cal  # noqa: E402

HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")

# 2026: Mo 03.08. · Di 04.08. · Fr 31.07. · Sa 01.08. · So 02.08.
# Karfreitag 2026 = 03.04. (gemeinsamer Voll-Schließtag).


def _report(run_ts: str, **bar_dates) -> dict:
    return {"run_timestamp_utc": run_ts,
            "markets": {k: {"diag": {"last_bar_date": v}}
                        for k, v in bar_dates.items()}}


# ---------------------------------------------------------------------------
# 1) Der Kalender-Kern — Sollwerte von Hand
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bar, bis, soll", [
    ("2026-08-04", "2026-08-04", 0),   # Di-Stand am Di
    ("2026-08-03", "2026-08-04", 1),   # Mo-Stand am Di
    ("2026-07-31", "2026-08-04", 2),   # Fr-Stand am Di
    ("2026-07-30", "2026-08-04", 3),   # Do-Stand am Di
    ("2026-07-31", "2026-08-01", 0),   # Fr-Stand am SAMSTAG -> kein Rückstand
    ("2026-07-31", "2026-08-02", 0),   # Fr-Stand am SONNTAG -> kein Rückstand
    ("2026-07-31", "2026-08-03", 1),   # Fr-Stand am Mo
    ("2026-04-01", "2026-04-06", 2),   # über Karfreitag: Do 02. + Mo 06.
    ("2026-04-02", "2026-04-03", 0),   # Karfreitag selbst ist kein Handelstag
    ("2026-08-05", "2026-08-04", 0),   # Stand in der ZUKUNFT -> nicht negativ
])
def test_rueckstand_von_hand_nachgerechnet(bar, bis, soll):
    assert cal.handelstage_rueckstand(bar, bis) == soll


@pytest.mark.parametrize("tag, soll", [
    ("2026-08-04", "2026-08-04"),   # Dienstag -> er selbst
    ("2026-08-01", "2026-07-31"),   # Samstag -> Freitag
    ("2026-08-02", "2026-07-31"),   # Sonntag -> Freitag
    ("2026-04-03", "2026-04-02"),   # Karfreitag -> Donnerstag
    ("2026-04-05", "2026-04-02"),   # Ostersonntag -> Donnerstag davor
])
def test_letzter_handelstag_von_hand(tag, soll):
    assert cal.letzter_handelstag(tag).isoformat() == soll


def test_unlesbare_daten_ergeben_None_statt_alarm():
    assert cal.letzter_handelstag("quatsch") is None
    assert cal.handelstage_rueckstand("quatsch", "2026-08-04") is None
    assert cal.handelstage_rueckstand("2026-08-04", None) is None


# ---------------------------------------------------------------------------
# 2) Die Health-Regel — die vier Lagen aus dem Auftrag
# ---------------------------------------------------------------------------
def test_freitags_stand_am_dienstag_ist_CRIT():
    f = hc.check_bar_freshness(
        _report("2026-08-04T21:45:00Z", DE="2026-07-31", US="2026-07-31"))
    assert [x["severity"] for x in f] == ["crit", "crit"]
    assert all(x["detail"]["lag_trading_days"] == 2 for x in f)
    assert all(x["detail"]["expected_bar_date"] == "2026-08-04" for x in f)
    assert "DE: Kurse 2 Handelstage zurück" in f[0]["message"]
    assert "erwartet 2026-08-04, tatsächlich 2026-07-31" in f[0]["message"]


def test_montags_stand_am_dienstag_ist_WARN():
    f = hc.check_bar_freshness(_report("2026-08-04T21:45:00Z", DE="2026-08-03"))
    assert len(f) == 1 and f[0]["severity"] == "warn"
    assert f[0]["detail"]["lag_trading_days"] == 1
    assert "1 Handelstag zurück" in f[0]["message"]   # Singular, nicht „Handelstage"


def test_aktueller_stand_meldet_NICHTS():
    assert hc.check_bar_freshness(
        _report("2026-08-04T21:45:00Z", DE="2026-08-04", US="2026-08-04")) == []


@pytest.mark.parametrize("lauf_tag", ["2026-08-01", "2026-08-02"])
def test_am_wochenende_KEIN_fehlalarm(lauf_tag):
    """Freitags-Stand am Samstag/Sonntag: der letzte Handelstag IST der
    Freitag. Genau hier hätte ein naiver Kalendertags-Vergleich Alarm
    geschlagen — der Staleness-Wächter ist an derselben Frage schon einmal
    gescheitert und rechnet seither kalenderbewusst."""
    assert hc.check_bar_freshness(
        _report(f"{lauf_tag}T21:45:00Z", DE="2026-07-31", US="2026-07-31")) == []


def test_am_feiertag_KEIN_fehlalarm():
    """Karfreitag 2026 (03.04.) ist gemeinsamer Voll-Schließtag."""
    assert hc.check_bar_freshness(
        _report("2026-04-03T21:45:00Z", DE="2026-04-02", US="2026-04-02")) == []
    # Und über die Osterbrücke hinweg: Dienstag nach Ostern, Donnerstags-Stand.
    f = hc.check_bar_freshness(_report("2026-04-07T21:45:00Z", DE="2026-04-02"))
    assert f and f[0]["detail"]["lag_trading_days"] == 2   # Mo 06. + Di 07.


def test_VORMITTAGS_LAUF_meldet_NICHTS_MEHR():
    """DER FEHLALARM IST WEG (05.08.2026) — vorher stand hier das Gegenteil.

    Bis zum Sitzungs-Ende-Anker las die Regel vom Lauf-Zeitstempel nur das
    **Datum** und erwartete deshalb am Vormittag eine Bar für **heute** — die es
    zu dem Zeitpunkt gar nicht geben kann. ECHT PASSIERT: die Hand-Dispatches am
    31.07. um 11:16 und 11:22 UTC; die NYSE öffnet erst 13:30 UTC, US stand
    folglich auf dem 30.07., und die Regel meldete zweimal einen Rückstand.

    Jetzt erwartet die Regel den letzten Handelstag, dessen Sitzung zur
    LAUF-ZEIT beendet war. Am Vormittag ist das der Vortag — der 30.07.-Stand
    ist damit aktuell, nicht verspätet.
    """
    # Freitag 31.07., 11:16 UTC — US hat noch nicht geöffnet, Xetra läuft noch.
    f = hc.check_bar_freshness(
        _report("2026-07-31T11:16:07Z", DE="2026-07-31", US="2026-07-30"))
    assert f == [], f"Fehlalarm ist zurück: {f}"
    f2 = hc.check_bar_freshness(
        _report("2026-07-31T11:22:00Z", DE="2026-07-31", US="2026-07-30"))
    assert f2 == []
    # Der ABEND-Lauf desselben Tages meldet unverändert — dort zu Recht, denn
    # beide Sitzungen sind vorbei und die US-Bar von Donnerstag fehlt wirklich.
    abends = hc.check_bar_freshness(
        _report("2026-07-31T22:40:44Z", DE="2026-07-31", US="2026-07-30"))
    assert [x["market"] for x in abends] == ["US"]
    assert abends[0]["severity"] == "warn"
    assert abends[0]["detail"]["expected_bar_date"] == "2026-07-31"


def test_ein_lauf_KURZ_NACH_schluss_meldet_wieder():
    """Die Gegenprobe zum Vormittag: eine Minute nach Xetra-Schluss ist die
    Tages-Bar fällig. Ohne diesen Test wäre „meldet nie mehr" ununterscheidbar
    von „meldet zum richtigen Zeitpunkt"."""
    # 31.07., 17:31 Ortszeit Berlin = 15:31 UTC (Sommerzeit) — Xetra ist zu,
    # die NYSE handelt noch. Erwartet: DE gemeldet, US still.
    f = hc.check_bar_freshness(
        _report("2026-07-31T15:31:00Z", DE="2026-07-30", US="2026-07-30"))
    assert [x["market"] for x in f] == ["DE"], f
    assert f[0]["detail"]["expected_bar_date"] == "2026-07-31"


def test_EINZELMARKT_feiertag_erzeugt_ein_warn_das_sich_selbst_heilt():
    """BEKANNTE GRENZE, hier festgenagelt statt versteckt (04.08.2026).

    ``FULL_CLOSURE`` listet bewusst nur die **gemeinsamen** Voll-Schließtage
    (NYSE ∩ Xetra). Einzelmarkt-Feiertage — Ostermontag und 1. Mai (nur Xetra),
    Thanksgiving und July 4 (nur NYSE) — stehen dort nicht, weil der Report an
    diesen Tagen normal läuft und der offene Markt liefert. Für den geschlossenen
    Markt gibt es dann aber **keine neue Bar**, und der Wächter sieht das als
    einen Handelstag Rückstand.

    Folge: am Abend eines Einzelmarkt-Feiertags ein ``warn`` für den
    geschlossenen Markt — inhaltlich richtig („die Kurse sind von gestern"),
    nur nicht handlungsbedürftig. Am nächsten Handelstag ist es weg, weil
    dessen Bar wieder existiert. Rund 6–8 solcher Tage im Jahr je Markt, dank
    Flanken-Logik je ein einzelner Push.

    Wird das je zu laut, ist der saubere Weg eine **markt-eigene**
    Schließtags-Liste — das ändert die Bedeutung von „erwartet" je Markt und
    braucht eine eigene datierte Entscheidung, keinen Test-Patch hier.
    """
    # Ostermontag 06.04.2026 (nur Xetra zu), DE-Stand vom Gründonnerstag.
    f = hc.check_bar_freshness(_report("2026-04-06T21:45:00Z", DE="2026-04-02"))
    assert len(f) == 1 and f[0]["severity"] == "warn"
    assert f[0]["detail"]["lag_trading_days"] == 1
    # Am Folgetag liegt die Dienstags-Bar vor -> still.
    assert hc.check_bar_freshness(
        _report("2026-04-07T21:45:00Z", DE="2026-04-07")) == []


def test_die_maerkte_werden_EINZELN_bewertet():
    f = hc.check_bar_freshness(
        _report("2026-08-04T21:45:00Z", DE="2026-07-31", US="2026-08-04"))
    assert len(f) == 1 and f[0]["market"] == "DE"


# ---------------------------------------------------------------------------
# 3) Fail-soft: kein Alarm aus Unwissen
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("report", [
    {"markets": {"DE": {"diag": {"last_bar_date": "2026-07-31"}}}},   # kein ts
    _report("2026-08-04T21:45:00Z", DE=None),                          # kein Datum
    _report("2026-08-04T21:45:00Z", DE="unlesbar"),
    {"run_timestamp_utc": "2026-08-04T21:45:00Z", "markets": {}},
    {"run_timestamp_utc": "kaputt", "markets": {"DE": {"diag": {}}}},
])
def test_fehlende_angaben_melden_NICHTS(report):
    """Ein Wächter, der bei fehlender Angabe Alarm schlägt, färbt alte
    Report-Stände und Fixtures grundlos rot."""
    assert hc.check_bar_freshness(report) == []


def test_ein_markt_OHNE_diag_schluessel_bricht_die_regel_nicht():
    """Guardian-Fund 04.08.2026: der `or {}`-Guard in Zeile
    ``(market.get("diag") or {})`` war ungetestet — kein Test baute einen Markt
    ohne den Schlüssel (nur mit kaputtem Wert, den fängt der `isinstance`-Guard
    davor ab). Ohne ihn stürzt die Regel bei einem Report-Stand aus der Zeit vor
    dem `diag`-Feld mit ``AttributeError`` ab, statt fail-soft zu schweigen —
    schlimmer als der Fehlalarm, den die Docstring ausschließen will."""
    r = {"run_timestamp_utc": "2026-08-04T21:45:00Z",
         "markets": {"DE": {}, "US": {"diag": {"last_bar_date": "2026-07-31"}}}}
    f = hc.check_bar_freshness(r)
    assert len(f) == 1 and f[0]["market"] == "US"


@pytest.mark.parametrize("wert, soll", [
    (_dt.date(2026, 8, 4), "2026-08-04"),
    (_dt.datetime(2026, 8, 4, 12, 30), "2026-08-04"),   # Guardian-Fund: ungetestet
    ("2026-08-04", "2026-08-04"),
])
def test_als_datum_nimmt_date_datetime_und_string(wert, soll):
    """Der ``datetime``-Zweig war ungetestet. Fällt er weg, liefert ``_als_datum``
    ein datetime zurück — und ``date < datetime`` wirft in Python ``TypeError``
    (nachgemessen). Aus fail-soft würde ein Absturz."""
    assert cal._als_datum(wert).isoformat() == soll
    assert isinstance(cal._als_datum(wert), _dt.date)
    assert not isinstance(cal._als_datum(wert), _dt.datetime)


def test_der_rueckstand_rechnet_auch_mit_datetime_objekten():
    assert cal.handelstage_rueckstand(
        _dt.datetime(2026, 7, 31, 22, 0), _dt.datetime(2026, 8, 4, 4, 46)) == 2


def test_ein_markt_ohne_diag_bricht_die_regel_nicht():
    r = {"run_timestamp_utc": "2026-08-04T21:45:00Z",
         "markets": {"DE": "kaputt", "US": {"diag": {"last_bar_date": "2026-07-31"}}}}
    f = hc.check_bar_freshness(r)
    assert len(f) == 1 and f[0]["market"] == "US"


# ---------------------------------------------------------------------------
# 4) Der ECHTE Fall vom 04.08. — damals ok gemeldet
# ---------------------------------------------------------------------------
def _echter_report(sha: str) -> dict:
    roh = subprocess.run(["git", "show", f"{sha}:data/report.json"],
                         cwd=ROOT, capture_output=True, text=True)
    if roh.returncode != 0:
        pytest.skip(f"Report-Stand {sha} nicht in der Historie (flacher Klon?)")
    return json.loads(roh.stdout)


def test_der_echte_04_08_fall_meldet_jetzt_WARN_statt_crit():
    """Lauf 30878626833, 04.08. 04:46 UTC — beide Märkte auf 2026-07-31.

    Damals: ``status: ok``, ``findings: []``. Genau das war die Lücke, die #71
    geschlossen hat (dort: 2× ``crit``).

    HERABSTUFUNG durch den Sitzungs-Ende-Anker (05.08.2026), ausdrücklich
    gewollt: um 04:46 UTC war die letzte BEENDETE Sitzung die vom **Montag,
    03.08.** — nicht die vom Dienstag, den es zu dieser Uhrzeit noch nicht gab.
    Der Rückstand ist damit **1** statt 2 Handelstage, und 1 ist ``warn``.
    Sachlich richtiger: die Kurse waren einen beendeten Handelstag alt, nicht
    zwei. Gemeldet wird weiterhin — nur ehrlicher eingestuft.
    """
    r = _echter_report("ed4770c")
    assert r["run_timestamp_utc"] == "2026-08-04T04:46:23Z"
    assert r["health"]["status"] == "ok" and r["health"]["findings"] == [], \
        "Voraussetzung: der echte Lauf meldete nichts"
    f = hc.check_bar_freshness(r)
    assert {x["market"] for x in f} == {"DE", "US"}
    assert [x["severity"] for x in f] == ["warn", "warn"]
    assert all(x["detail"] == {"expected_bar_date": "2026-08-03",
                               "last_bar_date": "2026-07-31",
                               "lag_trading_days": 1, "crit_ab": 2} for x in f)


def test_der_gesunde_lauf_vom_03_08_bleibt_still():
    """Gegenprobe am echten Bestand: 21:29 UTC, beide Märkte auf Montag."""
    r = _echter_report("8f20f85")
    assert r["run_timestamp_utc"] == "2026-08-03T21:29:19Z"
    assert hc.check_bar_freshness(r) == []


def test_der_DE_nebenbefund_vom_03_08_abend_wird_erkannt():
    """Im Cron-Lauf 22:38 stand DE auf Donnerstag (30.07.), obwohl nur die
    Montags-Zeile verworfen wurde — die Freitags-Zeile fehlte in der Quelle.
    Auch das ist ein Rückstand und soll gemeldet werden."""
    r = _echter_report("c58daf7")
    f = hc.check_bar_freshness(r)
    assert len(f) == 1 and f[0]["market"] == "DE" and f[0]["severity"] == "crit"
    assert f[0]["detail"]["last_bar_date"] == "2026-07-30"


# ---------------------------------------------------------------------------
# 5) Einbindung: normaler Health-Pfad, kein neuer Kanal
# ---------------------------------------------------------------------------
def test_die_regel_haengt_im_normalen_befund_pfad():
    r = _report("2026-08-04T21:45:00Z", DE="2026-07-31")
    r["markets"]["DE"]["candidates"] = [{"ticker": "X"}] * 5
    r["markets"]["DE"]["candidates_found"] = 5
    findings = hc.collect_findings(r, None, [], None, None, has_agent_key=False)
    regeln = {f["rule"] for f in findings}
    assert "bar_freshness" in regeln, "die Regel läuft nicht im Sammel-Pfad"
    assert hc.overall_status(findings) == "crit"


def test_die_schwelle_steht_im_report_block():
    assert hc.BAR_LAG_CRIT == 2
    quelle = (ROOT / "scripts/health_check.py").read_text(encoding="utf-8")
    assert '"bar_lag_crit": BAR_LAG_CRIT,' in quelle


# ---------------------------------------------------------------------------
# 6) Flanken-Verhalten — kein Push-Spam bei unverändertem Rückstand
# ---------------------------------------------------------------------------
def test_gleicher_rueckstand_am_folgetag_pusht_NICHT_erneut():
    """Der bekannte Ein-Tag-Versatz besteht Tag für Tag: der Kursstand wandert
    mit, der Rückstand bleibt 1. Der erste Lauf meldet, die folgenden
    schweigen — sonst käme jeden Abend derselbe Push und der Alarm verlöre
    seine Bedeutung.

    Von Hand: Mo-Stand am Di = 1 · Di-Stand am Mi = 1 — gleiche Lage, gleicher
    Schweregrad.
    """
    tag1 = hc.check_bar_freshness(_report("2026-08-04T21:45:00Z", DE="2026-08-03"))
    assert tag1[0]["severity"] == "warn" and tag1[0]["detail"]["lag_trading_days"] == 1
    to_push, state = hc.evaluate_edges(tag1, None, "2026-08-04")
    assert len(to_push) == 1, "der erste Befund muss raus"

    tag2 = hc.check_bar_freshness(_report("2026-08-05T21:45:00Z", DE="2026-08-04"))
    assert tag2[0]["severity"] == "warn" and tag2[0]["detail"]["lag_trading_days"] == 1
    to_push2, _ = hc.evaluate_edges(tag2, state, "2026-08-05")
    assert to_push2 == [], "unveränderter Rückstand darf nicht erneut pushen"


def test_eine_verbesserung_pusht_nicht():
    """crit -> warn: der Stand holt auf. Kein neuer Push, der Zustand steht im
    Lauf-Status."""
    crit = hc.check_bar_freshness(_report("2026-08-04T21:45:00Z", DE="2026-07-31"))
    assert crit[0]["severity"] == "crit"
    _, state = hc.evaluate_edges(crit, None, "2026-08-04")
    warn = hc.check_bar_freshness(_report("2026-08-05T21:45:00Z", DE="2026-08-04"))
    assert warn[0]["severity"] == "warn"
    to_push, _ = hc.evaluate_edges(warn, state, "2026-08-05")
    assert to_push == []


def test_unveraenderter_crit_am_folgetag_ist_still():
    tag1 = hc.check_bar_freshness(_report("2026-08-04T21:45:00Z", DE="2026-07-31"))
    _, state = hc.evaluate_edges(tag1, None, "2026-08-04")
    tag2 = hc.check_bar_freshness(_report("2026-08-05T21:45:00Z", DE="2026-07-31"))
    assert tag2[0]["severity"] == "crit"
    to_push, _ = hc.evaluate_edges(tag2, state, "2026-08-05")
    assert to_push == [], "unveränderter crit darf nicht erneut pushen"


def test_verschlechterung_warn_zu_crit_pusht_doch():
    warn = hc.check_bar_freshness(_report("2026-08-04T21:45:00Z", DE="2026-08-03"))
    _, state = hc.evaluate_edges(warn, None, "2026-08-04")
    crit = hc.check_bar_freshness(_report("2026-08-05T21:45:00Z", DE="2026-07-31"))
    assert crit[0]["severity"] == "crit"
    to_push, _ = hc.evaluate_edges(crit, state, "2026-08-05")
    assert len(to_push) == 1, "warn -> crit ist eine Flanke und MUSS pushen"


# ---------------------------------------------------------------------------
# 7) Frontend: der Hinweis erscheint nur bei Rückstand
# ---------------------------------------------------------------------------
_NODE = shutil.which("node") or shutil.which("nodejs")


def _fn(name: str, einrueckung: str = "      ") -> str:
    start = HTML.index(f"{einrueckung}function {name}(")
    return HTML[start:HTML.index(f"\n{einrueckung}}}", start) + len(f"\n{einrueckung}}}")]


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken den Rest")
    quelle = _fn("esc", "    ") + "\n" + _fn("barDateRow")
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_frontend_zeigt_bei_aktuellem_stand_KEIN_warnzeichen():
    """Kein Dauer-⚠: ohne Rückstand ist die Zeile exakt die alte."""
    html = _js("""console.log(JSON.stringify([
      barDateRow({last_bar_date: '2026-08-04', bar_lag_trading_days: 0,
                  expected_bar_date: '2026-08-04'}),
      barDateRow({last_bar_date: '2026-08-04'}),
      barDateRow({last_bar_date: '2026-08-04', bar_lag_trading_days: null})]))""")
    for zeile in html:
        assert zeile == ('<span class="k">Kurse vom</span>'
                         '<span class="v">2026-08-04</span>')
        assert "⚠" not in zeile and "bar-lag" not in zeile


def test_frontend_zeigt_den_rueckstand_mit_warnfarbe():
    eins, zwei = _js("""console.log(JSON.stringify([
      barDateRow({last_bar_date: '2026-08-03', bar_lag_trading_days: 1,
                  expected_bar_date: '2026-08-04'}),
      barDateRow({last_bar_date: '2026-07-31', bar_lag_trading_days: 2,
                  expected_bar_date: '2026-08-04'})]))""")
    assert '⚠ 1 Handelstag zurück' in eins and 'class="bar-lag"' in eins
    assert '⚠ 2 Handelstage zurück' in zwei
    assert 'erwartet 2026-08-04' in zwei          # im Tooltip
    for z in (eins, zwei):
        assert 'Kurse vom' in z


def test_frontend_ohne_bar_datum_bleibt_leer():
    leer = _js("console.log(JSON.stringify([barDateRow({}), "
               "barDateRow({bar_lag_trading_days: 3})]))")
    assert leer == ["", ""]


def test_die_warnfarbe_ist_ora_und_bringt_keine_gut_schlecht_semantik():
    start = HTML.index("    .bar-lag {")
    block = HTML[start:HTML.index("}", start)]
    assert "var(--ora)" in block
    for verboten in ("--grn", "--red", "green", "red"):
        assert verboten not in block, f"Farb-Semantik eingeschleppt: {verboten}"


def test_das_frontend_rechnet_den_kalender_NICHT_selbst_nach():
    """Der Handelskalender darf nicht ein zweites Mal in JavaScript existieren
    — sonst laufen beide beim nächsten Feiertag auseinander. Das Frontend liest
    ausschließlich die fertige Zahl aus dem Report."""
    zeile = _fn("barDateRow")
    assert "bar_lag_trading_days" in zeile
    for verboten in ("Karfreitag", "getDay()", "FULL_CLOSURE", "Neujahr",
                     "Weihnachtstag"):
        assert verboten not in zeile, f"Kalenderlogik im Frontend: {verboten}"


# ---------------------------------------------------------------------------
# 8) Die Pipeline schreibt die beiden Diagnose-Felder
# ---------------------------------------------------------------------------
def test_die_pipeline_annotiert_beide_felder():
    import elliott_pipeline as pipe
    markt = {"diag": {"last_bar_date": "2026-07-31"}}
    pipe._annotiere_bar_rueckstand(markt, "2026-08-04T04:46:23Z")
    assert markt["diag"]["expected_bar_date"] == "2026-08-04"
    assert markt["diag"]["bar_lag_trading_days"] == 2


def test_die_annotation_ist_fail_soft():
    import elliott_pipeline as pipe
    for markt in ({"diag": "kaputt"}, {}, {"diag": {}}):
        pipe._annotiere_bar_rueckstand(markt, "2026-08-04T04:46:23Z")   # kein Wurf
    leer = {"diag": {}}
    pipe._annotiere_bar_rueckstand(leer, "2026-08-04T04:46:23Z")
    assert leer["diag"]["bar_lag_trading_days"] is None


def test_health_und_frontend_lesen_DIESELBE_zahl():
    """Der Health-Befund und das Diagnose-Feld müssen übereinstimmen — sonst
    stünde im Lauf-Status eine andere Zahl als im Push."""
    import elliott_pipeline as pipe
    r = _report("2026-08-04T21:45:00Z", DE="2026-07-31")
    pipe._annotiere_bar_rueckstand(r["markets"]["DE"], r["run_timestamp_utc"])
    f = hc.check_bar_freshness(r)
    assert f[0]["detail"]["lag_trading_days"] == \
        r["markets"]["DE"]["diag"]["bar_lag_trading_days"]
    assert f[0]["detail"]["expected_bar_date"] == \
        r["markets"]["DE"]["diag"]["expected_bar_date"]
