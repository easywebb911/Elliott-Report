"""Wegwerf-Messung der Quellen-Zeiten — sie darf NUR messen.

Die drei Zusagen, die diese Datei festnagelt:
  1. **Dieselbe Abruf-Funktion wie die Pipeline** — eine zweite Fassung würde
     etwas anderes messen als der Tageslauf sieht.
  2. **Der ECHTE Abrufzeitpunkt** wird protokolliert, nie die Cron-Sollzeit.
     GitHub verzögert geplante Läufe (gemessen 52–60 min, einmal 3:19 h);
     eine Zeile mit der Sollzeit
     wäre eine Zeile über einen Zeitpunkt, zu dem nichts abgerufen wurde.
  3. **Isolation**: Report, Sammlung, Health-Zustand und `docs/` bleiben
     unberührt.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import elliott_pipeline as pipe  # noqa: E402
import source_timing_probe as probe  # noqa: E402

WF = ROOT / ".github/workflows/source_timing_probe.yml"
SKRIPT = (ROOT / "scripts/source_timing_probe.py").read_text(encoding="utf-8")


def _nur_code(quelle: str) -> str:
    """Python ohne Kommentare und Zeichenketten/Docstrings.

    Ein Verbots-Test gegen den ROHTEXT verbietet auch, das Verbotene zu
    ERKLÄREN — dieser Test wurde prompt an der eigenen Dokumentation rot
    („inklusive ``auto_adjust``", „``docs/`` bleiben unberührt"). Geprüft wird
    deshalb, was wirklich ausgeführt wird.
    """
    import io
    import tokenize
    raus = []
    for tok in tokenize.generate_tokens(io.StringIO(quelle).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        raus.append(tok.string)
    return " ".join(raus)


def _yaml_ohne_kommentare(quelle: str) -> str:
    zeilen = []
    for z in quelle.split("\n"):
        ohne = z.split(" #", 1)[0] if " #" in z else z
        if ohne.strip().startswith("#"):
            continue
        zeilen.append(ohne)
    return "\n".join(zeilen)


CODE = _nur_code(SKRIPT)


# ---------------------------------------------------------------------------
# 1 · Dieselbe Abruf-Funktion wie die Pipeline
# ---------------------------------------------------------------------------
def test_die_messung_ruft_die_PIPELINE_funktion_auf():
    """Kein zweiter yfinance-Aufruf, kein eigenes Parsen, kein eigenes
    Finit-Prädikat — sonst misst die Sonde etwas anderes als der Tageslauf."""
    assert "pipe . fetch_yfinance" in CODE
    for eigenbau in ("yf . download", "import yfinance", "auto_adjust",
                     "parse_download_df", "def fetch_", "isfinite"):
        assert eigenbau not in CODE, f"eigene Abruf-/Parse-Fassung: {eigenbau}"
    # … und die Kennzahlen kommen aus derselben Zusammenfassung wie im Report
    assert "pipe . series_summary" in CODE


def test_die_stichprobe_stammt_aus_dem_echten_universum():
    for markt, tickers in probe.PROBE_TICKERS.items():
        universum = {str(t).upper() for t in config.MARKETS[markt]["universe"]}
        fremd = [t for t in tickers if t.upper() not in universum]
        assert not fremd, f"{markt}: nicht im Universum -> {fremd}"
        assert len(tickers) == 10, f"{markt}: {len(tickers)} statt 10"
        assert len(set(tickers)) == len(tickers), f"{markt}: Dublette"


def test_der_aufwand_ist_beziffert_und_klein():
    """20 Abrufe je Lauf gegen 353 im Tageslauf — die Messung darf die Quelle
    nicht nennenswert zusätzlich belasten."""
    gesamt = sum(len(t) for t in probe.PROBE_TICKERS.values())
    assert gesamt == 20
    tageslauf = sum(len(config.MARKETS[m]["universe"]) for m in config.MARKETS)
    assert gesamt < tageslauf * 0.1, f"{gesamt} von {tageslauf} ist zu viel"


# ---------------------------------------------------------------------------
# 2 · Werte an konstruierten Reihen — Soll von Hand
# ---------------------------------------------------------------------------
def _reihe(n, ende):
    e = _dt.date.fromisoformat(ende)
    return ([str(e - _dt.timedelta(days=n - 1 - i)) for i in range(n)],
            [100.0 + (i % 7) for i in range(n)])


def _fetcher(bauplan):
    def f(ticker):
        eintrag = bauplan[ticker]
        if eintrag is None:
            return pipe.FetchOutcome(None, pipe.EMPTY_DATA, "leer")
        if isinstance(eintrag, dict):
            return pipe.FetchOutcome(**eintrag)
        return pipe.FetchOutcome(eintrag)
    return f


def test_endliche_letzte_zeile_ergibt_das_AKTUELLE_datum():
    """Der gesunde Fall: alle drei tragen den 06.08., nichts verworfen."""
    tickers = ["A", "B", "C"]
    plan = {t: _reihe(40, "2026-08-06") for t in tickers}
    z = probe.probe_markt("DE", tickers, _fetcher(plan),
                          jetzt=_dt.datetime(2026, 8, 6, 21, 45,
                                             tzinfo=_dt.timezone.utc))
    assert z["last_bar_date"] == "2026-08-06"
    assert z["tickers_at_last_bar"] == 3
    assert z["dropped_last_row"] == 0
    assert z["tickers_with_series"] == 3 and z["errors"] == []


def test_NICHT_finite_letzte_zeile_faellt_auf_den_VORTAG_zurueck():
    """Der DE-Abendfall: die Quelle liefert die 06.08.-Zeile, aber unbrauchbar.
    Der Parser verwirft sie -> die Reihe endet am 05.08., und die Sonde
    protokolliert genau das, samt Zähler."""
    tickers = ["A", "B", "C"]
    plan = {}
    for t in tickers:
        tage, kurse = _reihe(40, "2026-08-06")
        plan[t] = {"data": (tage[:-1], kurse[:-1]), "dropped_bars": 1,
                   "dropped_dates": (tage[-1],), "dropped_last_row": 1}
    z = probe.probe_markt("DE", tickers, _fetcher(plan),
                          jetzt=_dt.datetime(2026, 8, 6, 22, 40,
                                             tzinfo=_dt.timezone.utc))
    assert z["last_bar_date"] == "2026-08-05", "Rückfall auf den Vortag"
    assert z["dropped_last_row"] == 3, "drei verworfene letzte Zeilen"
    assert z["tickers_at_last_bar"] == 3


def test_ein_gespaltener_markt_wird_als_solcher_sichtbar():
    """Zwei tragen den 06.08., einer hängt zurück — genau die Lage, die
    `last_bar_date` allein verschluckt."""
    plan = {"A": _reihe(40, "2026-08-06"), "B": _reihe(40, "2026-08-06"),
            "C": _reihe(39, "2026-08-05")}
    z = probe.probe_markt("US", ["A", "B", "C"], _fetcher(plan),
                          jetzt=_dt.datetime(2026, 8, 6, 20, 10,
                                             tzinfo=_dt.timezone.utc))
    assert z["last_bar_date"] == "2026-08-06" and z["last_bar_min"] == "2026-08-05"
    assert z["tickers_at_last_bar"] == 2


def test_ein_toter_ticker_wird_benannt_und_kippt_die_zeile_nicht():
    plan = {"A": _reihe(40, "2026-08-06"), "B": None}
    z = probe.probe_markt("US", ["A", "B"], _fetcher(plan),
                          jetzt=_dt.datetime(2026, 8, 6, 20, 10,
                                             tzinfo=_dt.timezone.utc))
    assert z["tickers_with_series"] == 1 and z["tickers_probed"] == 2
    assert z["errors"] == ["B:empty_data"]
    assert z["last_bar_date"] == "2026-08-06"


# ---------------------------------------------------------------------------
# 3 · Der ECHTE Zeitstempel
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ist_zeit", [
    _dt.datetime(2026, 8, 6, 20, 8, tzinfo=_dt.timezone.utc),
    _dt.datetime(2026, 8, 6, 22, 31, tzinfo=_dt.timezone.utc),
])
def test_protokolliert_wird_die_IST_zeit_nicht_die_sollzeit(ist_zeit):
    """Der Kern der Messung. Läuft der Job um 22:31 statt der Sollzeit 21:35,
    MUSS 22:31 in der Zeile stehen — sonst ist die Messung wertlos."""
    plan = {"A": _reihe(30, "2026-08-06")}
    z = probe.probe_markt("DE", ["A"], _fetcher(plan), jetzt=ist_zeit)
    assert z["fetched_utc"] == ist_zeit.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_ohne_vorgabe_kommt_die_echte_uhr(monkeypatch):
    """Im Betrieb gibt es keine Vorgabe — dann muss die Wanduhr her, und zwar
    zum Zeitpunkt des Abrufs."""
    gerufen = {}

    class _Uhr(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            gerufen["ja"] = True
            return _dt.datetime(2026, 8, 6, 22, 17, tzinfo=tz)

    monkeypatch.setattr(probe._dt, "datetime", _Uhr)
    plan = {"A": _reihe(30, "2026-08-06")}
    z = probe.probe_markt("DE", ["A"], _fetcher(plan))
    assert gerufen.get("ja") is True
    assert z["fetched_utc"] == "2026-08-06T22:17:00Z"


def test_finished_utc_ist_ein_ZWEITER_spaeterer_uhrenblick(monkeypatch):
    """`finished_utc` ist keine Kopie von `fetched_utc`, sondern die Uhr NACH
    den Abrufen. Erst dadurch ist an der Zeile ablesbar, ob sie über einen
    Zeitpunkt spricht oder über einen langen Zeitraum — bei einer gesuchten
    Auflösung von ~15 min ist das der Unterschied zwischen Messung und
    Vermutung."""
    takte = iter([_dt.datetime(2026, 8, 6, 22, 15, 0, tzinfo=_dt.timezone.utc),
                  _dt.datetime(2026, 8, 6, 22, 16, 42, tzinfo=_dt.timezone.utc)])

    class _Uhr(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return next(takte)

    monkeypatch.setattr(probe._dt, "datetime", _Uhr)
    plan = {t: _reihe(30, "2026-08-06") for t in ("A", "B")}
    z = probe.probe_markt("DE", ["A", "B"], _fetcher(plan))
    assert z["fetched_utc"] == "2026-08-06T22:15:00Z"
    assert z["finished_utc"] == "2026-08-06T22:16:42Z", "zweiter Uhrenblick fehlt"


def test_die_zeile_traegt_alle_geforderten_felder():
    plan = {"A": _reihe(30, "2026-08-06")}
    z = probe.probe_markt("DE", ["A"], _fetcher(plan),
                          jetzt=_dt.datetime(2026, 8, 6, 21, 45,
                                             tzinfo=_dt.timezone.utc))
    for feld in ("fetched_utc", "market", "last_bar_date",
                 "tickers_at_last_bar", "dropped_last_row", "shape_digest"):
        assert feld in z, f"{feld} fehlt"
    assert json.loads(json.dumps(z)) == z, "die Zeile muss JSON-fähig sein"


# ---------------------------------------------------------------------------
# 4 · Isolation
# ---------------------------------------------------------------------------
def test_die_messung_kennt_KEINE_produktionsdatei():
    for verboten in ("report.json", "forward_collection", "health_state",
                     "docs", "validation_milestone"):
        assert verboten not in CODE, f"die Sonde fasst {verboten} an"
    assert probe.PROBE_PATH == "data/source_timing_probe.jsonl"


def test_ein_messlauf_laesst_report_sammlung_und_health_BYTE_IDENTISCH(tmp_path,
                                                                      monkeypatch):
    """Der harte Isolations-Nachweis: Prüfsummen vor und nach einem echten
    Schreibvorgang der Sonde.

    Verschoben wird die WURZEL (`REPO_ROOT`), nicht der Zielpfad. Ein Test, der
    `_anhaengen` einen tmp-Pfad in die Hand drückt, prüft nur, dass ein
    übergebener Pfad benutzt wird — er sagt nichts darüber, wohin die Sonde im
    Betrieb schreibt. Hier läuft die ECHTE Pfadberechnung
    (`REPO_ROOT / PROBE_PATH`) durch, nur eben unter einer Wurzel, in der es
    keine Produktionsdatei zu treffen gäbe.
    """
    import hashlib

    def summe(p):
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

    wachen = [ROOT / "data/report.json", ROOT / "docs/data/report.json",
              ROOT / "data/forward_collection.json",
              ROOT / "docs/data/forward_collection.json",
              ROOT / "data/health_state.json"]
    vorher = {p: summe(p) for p in wachen}

    monkeypatch.setattr(probe, "REPO_ROOT", tmp_path)
    plan = {"A": _reihe(30, "2026-08-06")}
    z = probe.probe_markt("DE", ["A"], _fetcher(plan),
                          jetzt=_dt.datetime(2026, 8, 6, 21, 45,
                                             tzinfo=_dt.timezone.utc))
    ziel = probe._anhaengen([z])

    assert ziel == tmp_path / probe.PROBE_PATH, "andere Datei als angekündigt"
    assert ziel.exists() and ziel.read_text(encoding="utf-8").count("\n") == 1
    for p in wachen:
        assert summe(p) == vorher[p], f"{p.name} wurde verändert"


def test_angehaengt_wird_nur_gehaengt_nie_ueberschrieben(tmp_path):
    ziel = tmp_path / "probe.jsonl"
    probe._anhaengen([{"a": 1}], ziel)
    probe._anhaengen([{"a": 2}, {"a": 3}], ziel)
    zeilen = [json.loads(z) for z in ziel.read_text(encoding="utf-8").splitlines()]
    assert zeilen == [{"a": 1}, {"a": 2}, {"a": 3}]


# ---------------------------------------------------------------------------
# 5 · Der Workflow
# ---------------------------------------------------------------------------
def test_eigene_concurrency_gruppe_nicht_die_des_tageslaufs():
    text = WF.read_text(encoding="utf-8")
    assert "group: source-timing-probe" in text
    assert "daily-elliott" not in text.split("concurrency:")[1][:200]


def test_der_workflow_committet_NUR_die_messdatei():
    text = _yaml_ohne_kommentare(WF.read_text(encoding="utf-8"))
    assert "git add data/source_timing_probe.jsonl" in text
    assert "git add -A" not in text and "git add ." not in text
    for verboten in ("report.json", "forward_collection", "health_state", "docs/"):
        assert f"git add {verboten}" not in text
    assert "if: github.ref == 'refs/heads/main'" in text


def test_der_rebase_abort_liegt_IM_wiederholungs_schleifenkoerper():
    """Nicht bloß irgendwo in der Datei.

    Eine Mutationsprobe (06.08.2026) hat den Abort AUS DER SCHLEIFE entfernt
    und die Testreihe blieb grün — `"git rebase --abort" in text` fand noch die
    Aufräumzeile hinter der Schleife. Genau das war aber der Fehler aus
    daily.yml vom 31.07.2026: bleibt ein Rebase hängen, bricht `git pull` bei
    unmerged files sofort ab, und Versuch 2 und 3 sind keine Versuche.
    """
    text = _yaml_ohne_kommentare(WF.read_text(encoding="utf-8"))
    assert "for i in 1 2 3; do" in text, "Wiederholungsschleife fehlt"
    koerper = text.split("for i in 1 2 3; do", 1)[1].split("done", 1)[0]
    assert "git rebase --abort" in koerper, "Abort steht nicht IN der Schleife"
    assert koerper.index("git rebase --abort") < koerper.index("git pull"), \
        "der Abort muss VOR dem pull stehen, sonst räumt er nichts auf"


def test_die_cron_eintraege_liegen_55_minuten_vor_den_zielzeiten():
    """Von Hand: Verzögerung 52–60 min über acht geplante Läufe (28.07.–06.08.,
    Soll 21:45). Ziel 20:10 -> Cron 19:15, Ziel 21:45 -> 20:50, Ziel 22:15 ->
    21:20; dazu zwei Zwischenpunkte für eine 15-Minuten-Auflösung.

    Der gemessene Ausreißer von 3:19 h (Nacht zum 07.08.) ist bewusst NICHT
    eingerechnet: gegen drei Stunden Verzug hilft kein Raster, ein solcher Tag
    liefert keinen Ertrag und wird verworfen. Siehe Kopf der Workflow-Datei."""
    text = WF.read_text(encoding="utf-8")
    for eintrag in ('cron: "15 19 * * 1-5"', 'cron: "50 20 * * 1-5"',
                    'cron: "5 21 * * 1-5"', 'cron: "20 21 * * 1-5"',
                    'cron: "35 21 * * 1-5"'):
        assert eintrag in text, f"{eintrag} fehlt"
    assert text.count("- cron:") == 5


def test_der_tageslauf_bleibt_unangetastet():
    """Cron-Soll-Wert seit 22.08.2026: 22:45 UTC (vorher 21:45) — die
    Sonden-Rohdaten DIESES Moduls waren der Beleg für die Verschiebung (DE-
    Rückzug an 5/10 Tagen zwischen 4. und 5. Tageslauf, gedeckt durch den
    Live-Vorfall vom 21./22.08.). Der Name dieses Tests bezieht sich auf den
    STRUKTURELLEN Schutz vor unbeabsichtigten Nebenwirkungen der Sonde auf
    daily.yml (Concurrency-Gruppe, Cron-Anzahl) — nicht auf den Zeit-WERT
    selbst, der hier bewusst per separatem Auftrag geändert wurde."""
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert 'cron: "45 22 * * 1-5"' in daily
    assert daily.count("- cron:") == 1
    assert "group: daily-elliott" in daily


# ---------------------------------------------------------------------------
# 6 · Wegwerf
# ---------------------------------------------------------------------------
def test_das_enddatum_steht_im_code_und_schaltet_ab():
    assert probe.PROBE_END_DATE == _dt.date(2026, 8, 21)
    assert probe.abgelaufen(_dt.date(2026, 8, 21)) is False, "am Stichtag noch aktiv"
    assert probe.abgelaufen(_dt.date(2026, 8, 22)) is True
    assert probe.abgelaufen(_dt.date(2026, 8, 6)) is False


def test_nach_ablauf_wird_NICHTS_abgerufen_und_nichts_geschrieben(monkeypatch, capsys):
    monkeypatch.setattr(probe, "abgelaufen", lambda heute=None: True)

    def _darf_nicht(*a, **k):
        raise AssertionError("nach Ablauf darf kein Abruf stattfinden")

    monkeypatch.setattr(pipe, "fetch_yfinance", _darf_nicht)
    monkeypatch.setattr(probe, "_anhaengen", _darf_nicht)
    assert probe.main() == 0
    ausgabe = capsys.readouterr().out
    assert "Messfenster beendet" in ausgabe
    assert "gelöscht werden" in ausgabe


def test_offline_misst_nicht(monkeypatch, capsys):
    """Prüft den OFFLINE-Zweig in `main()` — der greift erst NACH der
    Ablauf-Prüfung (`if abgelaufen(): ...; if OFFLINE: ...`), deshalb muss
    dieser Test wie seine Geschwister weiter unten (`test_bei_einem_fehler_
    wird_SOFORT_aufgehoert` u. a.) `abgelaufen` explizit auf False fixieren.

    OHNE diese Fixierung lief der Test bis 21.08.2026 zufällig richtig, weil
    die WIRKLICHE Kalenderuhr zufällig noch vor `PROBE_END_DATE` lag — er hat
    also nie wirklich den OFFLINE-Zweig isoliert geprüft, sondern nur, dass
    HEUTE ≤ PROBE_END_DATE war. Seit 22.08.2026 ist der Stichtag planmäßig
    verstrichen (das ist die WEGWERF-Bestimmung des Moduls selbst, s. Kopf-
    Docstring von `source_timing_probe.py`, und read-only bestätigt: ein
    echter, ungemockter `main()`-Lauf am 22.08.2026 druckt exakt „Messfenster
    beendet … kein Abruf, nichts geschrieben" und lässt
    `data/source_timing_probe.jsonl` byte-identisch) — seither griff im Test
    ungewollt der ABLAUF-Zweig zuerst und maskierte den OFFLINE-Zweig, den der
    Test eigentlich prüfen soll. Das ist die geplante Abschaltung, kein neuer
    Fehler in `main()` — die Fixierung macht den Test wieder unabhängig vom
    Kalender, wie alle Nachbartests in diesem Abschnitt."""
    monkeypatch.setattr(probe, "abgelaufen", lambda heute=None: False)
    monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
    monkeypatch.setattr(pipe, "fetch_yfinance",
                        lambda t: (_ for _ in ()).throw(AssertionError("kein Abruf")))
    assert probe.main() == 0
    assert "OFFLINE" in capsys.readouterr().out


def test_bei_einem_fehler_wird_SOFORT_aufgehoert(monkeypatch, capsys, tmp_path):
    """Rate-Limit-Regel: kein Retry-Sturm. Der Abbruch steht im Log, und es
    wird keine halbe Zeile geschrieben."""
    monkeypatch.setattr(probe, "abgelaufen", lambda heute=None: False)
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)
    aufrufe = {"n": 0}

    def _kracht(markt, tickers, fetcher, jetzt=None):
        aufrufe["n"] += 1
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(probe, "probe_markt", _kracht)
    geschrieben = []
    monkeypatch.setattr(probe, "_anhaengen", lambda z, p=None: geschrieben.append(z))
    assert probe.main() == 0
    ausgabe = capsys.readouterr().out
    assert "kein Retry" in ausgabe and "429" in ausgabe
    assert aufrufe["n"] == 1, "nach dem ersten Fehler ist Schluss"
    assert geschrieben == [], "keine Zeile bei Abbruch"


def test_ein_markt_OHNE_JEDE_reihe_ist_ein_ausfall_keine_messung(monkeypatch,
                                                                 capsys):
    """Der realistische Rate-Limit-Fall — und er läuft NICHT über `except`.

    `fetch_yfinance` fängt Ausnahmen selbst ab und liefert
    `FetchOutcome(reason=FETCH_ERROR)`. Ohne eigenen Wächter entstünde also
    eine vollständig leere Zeile, die bei der Auswertung wie „die Quelle hatte
    um 22:15 keine Daten" aussähe — und damit genau die Cron-Entscheidung
    verfälschte, für die hier gemessen wird.
    """
    monkeypatch.setattr(probe, "abgelaufen", lambda heute=None: False)
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)
    versuche = {"n": 0}

    def _blockiert(ticker):
        versuche["n"] += 1
        return pipe.FetchOutcome(None, pipe.FETCH_ERROR, "429 Too Many Requests")

    monkeypatch.setattr(pipe, "fetch_yfinance", _blockiert)
    geschrieben = []
    monkeypatch.setattr(probe, "_anhaengen", lambda z, p=None: geschrieben.append(z))

    assert probe.main() == 0
    ausgabe = capsys.readouterr().out
    assert "Abruf-Ausfall" in ausgabe, "der Ausfall muss laut im Log stehen"
    assert geschrieben == [], "eine leere Zeile wäre eine Falschaussage über die Quelle"
    # Nur der erste Markt wird versucht — danach ist Schluss, kein zweiter
    # Anlauf gegen eine Quelle, die gerade dichtmacht.
    assert versuche["n"] == len(probe.PROBE_TICKERS["DE"])


def test_faellt_ein_markt_aus_bleibt_die_gelungene_zeile_stehen(monkeypatch,
                                                                capsys):
    """Teil-Messung ist ABSICHT: die DE-Zeile ist ein vollwertiger Datenpunkt
    für DE, auch wenn US danach ausfällt. Sie wegzuwerfen würde eine Messung
    vernichten, die mit dem Ausfall nichts zu tun hat."""
    monkeypatch.setattr(probe, "abgelaufen", lambda heute=None: False)
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)

    def _halb(ticker):
        if ticker.endswith(".DE"):
            return pipe.FetchOutcome(_reihe(30, "2026-08-06"))
        return pipe.FetchOutcome(None, pipe.FETCH_ERROR, "429")

    monkeypatch.setattr(pipe, "fetch_yfinance", _halb)
    geschrieben = []

    def _sammelt(zeilen, pfad=None):
        geschrieben.append(zeilen)
        return probe.REPO_ROOT / probe.PROBE_PATH  # wie das Original: der Pfad

    monkeypatch.setattr(probe, "_anhaengen", _sammelt)

    assert probe.main() == 0
    ausgabe = capsys.readouterr().out
    assert len(geschrieben) == 1, "genau ein Schreibvorgang"
    assert [z["market"] for z in geschrieben[0]] == ["DE"]
    assert geschrieben[0][0]["last_bar_date"] == "2026-08-06"
    assert "Teil-Messung" in ausgabe and "US" in ausgabe
