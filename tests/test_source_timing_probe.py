"""Wegwerf-Messung der Quellen-Zeiten — sie darf NUR messen.

Die drei Zusagen, die diese Datei festnagelt:
  1. **Dieselbe Abruf-Funktion wie die Pipeline** — eine zweite Fassung würde
     etwas anderes messen als der Tageslauf sieht.
  2. **Der ECHTE Abrufzeitpunkt** wird protokolliert, nie die Cron-Sollzeit.
     GitHub verzögert geplante Läufe um 53–57 min; eine Zeile mit der Sollzeit
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


def test_ein_messlauf_laesst_report_sammlung_und_health_BYTE_IDENTISCH(tmp_path):
    """Der harte Isolations-Nachweis: Prüfsummen vor und nach einem echten
    Schreibvorgang der Sonde."""
    import hashlib

    def summe(p):
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

    wachen = [ROOT / "data/report.json", ROOT / "docs/data/report.json",
              ROOT / "data/forward_collection.json",
              ROOT / "docs/data/forward_collection.json",
              ROOT / "data/health_state.json"]
    vorher = {p: summe(p) for p in wachen}

    ziel = tmp_path / "probe.jsonl"
    plan = {"A": _reihe(30, "2026-08-06")}
    z = probe.probe_markt("DE", ["A"], _fetcher(plan),
                          jetzt=_dt.datetime(2026, 8, 6, 21, 45,
                                             tzinfo=_dt.timezone.utc))
    probe._anhaengen([z], ziel)

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
    assert "git rebase --abort" in text


def test_die_cron_eintraege_liegen_55_minuten_vor_den_zielzeiten():
    """Von Hand: Verzögerung 53–57 min (21:45 -> 22:37:51 / 22:40:53 /
    22:41:59). Ziel 20:10 -> Cron 19:15, Ziel 21:45 -> 20:50, Ziel 22:15 ->
    21:20; dazu zwei Zwischenpunkte für eine 15-Minuten-Auflösung."""
    text = WF.read_text(encoding="utf-8")
    for eintrag in ('cron: "15 19 * * 1-5"', 'cron: "50 20 * * 1-5"',
                    'cron: "5 21 * * 1-5"', 'cron: "20 21 * * 1-5"',
                    'cron: "35 21 * * 1-5"'):
        assert eintrag in text, f"{eintrag} fehlt"
    assert text.count("- cron:") == 5


def test_der_tageslauf_bleibt_unangetastet():
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert 'cron: "45 21 * * 1-5"' in daily
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
