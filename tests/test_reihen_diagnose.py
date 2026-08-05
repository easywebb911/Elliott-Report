"""Reihen-Diagnose: was hat der Lauf TATSÄCHLICH an Kursreihe bekommen?

ANLASS (TKA.DE-Befund, 05.08.2026): am 03.08. lieferten zwei Läufe **elf
Minuten** auseinander denselben ``last_bar_date`` (2026-08-03), dieselbe Zahl
gefundener Kandidaten (32) — und trotzdem einen anderen gültigen Kandidatensatz
(``no_valid_count`` 50 vs. 49; TKA.DE drin bzw. draußen). Aus dem Report war
nicht rekonstruierbar, warum: ``last_bar_date`` ist das JÜNGSTE Bar-Datum über
alle Ticker. Es sagt nichts darüber, wie viele Ticker dort ankommen und wie
lang ihre Reihen sind — und genau das entscheidet, ob der ZigZag einen Pivot
schon bestätigt (``ZIGZAG_WINDOW`` Bars danach).

Die Felder sind REIN BESCHREIBEND. Kein Score, kein Filter, kein Ranking, kein
Gate liest sie. Ein eigener Test hält das fest.

Zwei Netze:
  (a) Werte an KONSTRUIERTEN Reihen, Soll von Hand nachgerechnet;
  (b) Frontend-Pins + node-Läufe für den Karten-Hinweis (kein zweiter
      Handelskalender in JavaScript).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import elliott_pipeline as pipe  # noqa: E402

HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) Verteilungswerte — Soll von Hand nachgerechnet
# ---------------------------------------------------------------------------
def test_gleich_lange_reihen_ergeben_gleiche_kennzahlen():
    """Drei Ticker, je 500 Bars, identischer Zeitraum: min = Median = max."""
    q = pipe.series_summary({
        "A": (500, "2024-08-05", "2026-08-04"),
        "B": (500, "2024-08-05", "2026-08-04"),
        "C": (500, "2024-08-05", "2026-08-04"),
    })
    assert q["tickers"] == 3
    assert (q["bars_min"], q["bars_median"], q["bars_max"]) == (500, 500, 500)
    assert q["first_bar_min"] == q["first_bar_max"] == "2024-08-05"
    assert q["last_bar_min"] == q["last_bar_max"] == "2026-08-04"
    assert q["tickers_at_last_bar"] == 3
    assert q["schema"] == 1


def test_eine_kurze_reihe_faellt_auf():
    """Der Fall, für den es die Diagnose gibt: einer ist deutlich kürzer, das
    JÜNGSTE Bar-Datum sieht davon nichts.

    Von Hand: Längen sortiert [120, 500, 500] -> min 120, Median (Index
    (3-1)//2 = 1) 500, max 500. Alle drei enden am selben Tag — genau deshalb
    hätte `last_bar_date` allein hier nichts gemeldet."""
    q = pipe.series_summary({
        "A": (500, "2024-08-05", "2026-08-04"),
        "B": (500, "2024-08-05", "2026-08-04"),
        "KURZ": (120, "2026-02-10", "2026-08-04"),
    })
    assert (q["bars_min"], q["bars_median"], q["bars_max"]) == (120, 500, 500)
    assert q["first_bar_min"] == "2024-08-05" and q["first_bar_max"] == "2026-02-10"
    assert q["last_bar_min"] == q["last_bar_max"] == "2026-08-04"
    assert q["tickers_at_last_bar"] == 3, "trotz kurzer Reihe erreichen alle den jüngsten Bar"


def test_eine_sehr_kurze_und_eine_zurueckhaengende_reihe():
    """Vier Ticker, davon einer sehr kurz UND einer einen Tag zurück.

    Von Hand: Längen sortiert [5, 118, 500, 500] -> min 5; unterer Median ist
    Index (4-1)//2 = 1 -> 118 (ein Wert, den ein Ticker WIRKLICH hat, kein
    gemittelter 309); max 500. Enddaten: drei am 04.08., einer am 03.08."""
    q = pipe.series_summary({
        "A": (500, "2024-08-05", "2026-08-04"),
        "B": (500, "2024-08-05", "2026-08-04"),
        "KURZ": (118, "2026-02-10", "2026-08-04"),
        "MINI": (5, "2026-07-29", "2026-08-03"),
    })
    assert (q["bars_min"], q["bars_median"], q["bars_max"]) == (5, 118, 500)
    assert q["last_bar_min"] == "2026-08-03" and q["last_bar_max"] == "2026-08-04"
    assert q["tickers_at_last_bar"] == 3, "MINI hängt zurück und zählt nicht mit"


@pytest.mark.parametrize("laengen, soll_median", [
    ([7], 7),                       # n=1 -> der einzige Wert
    ([4, 9], 4),                    # n=2 -> UNTERER Median, nicht 6.5
    ([1, 2, 3], 2),
    ([1, 2, 3, 4], 2),              # n=4 -> Index 1
    ([10, 20, 30, 40, 50], 30),
    ([5, 5, 5, 5, 5, 900], 5),      # Ausreißer nach oben zieht den Median nicht
])
def test_der_median_ist_der_untere_und_immer_ein_echter_wert(laengen, soll_median):
    """Für eine Bar-ANZAHL ist ein gemittelter Median eine Zahl, die kein
    Ticker hat. Der untere Median ist immer eine echte Reihenlänge."""
    q = pipe.series_summary({f"T{i}": (n, "2026-01-01", "2026-08-04")
                             for i, n in enumerate(laengen)})
    assert q["bars_median"] == soll_median
    assert q["bars_median"] in laengen, "der Median muss ein vorkommender Wert sein"


def test_leerer_eingang_ergibt_None():
    """Kein leerer Block im Report, wenn der Markt nichts geliefert hat."""
    assert pipe.series_summary({}) is None


def test_die_kennzahlen_sind_von_der_reihenfolge_unabhaengig():
    a = pipe.series_summary({"A": (10, "2026-01-01", "2026-08-04"),
                             "B": (20, "2026-02-01", "2026-08-04")})
    b = pipe.series_summary({"B": (20, "2026-02-01", "2026-08-04"),
                             "A": (10, "2026-01-01", "2026-08-04")})
    assert a == b


# ---------------------------------------------------------------------------
# Der Abdruck — die eigentliche Antwort auf die Elf-Minuten-Frage
# ---------------------------------------------------------------------------
def test_gleiche_reihenform_ergibt_denselben_abdruck():
    """Zwei Läufe mit derselben Eingangsform sind am Abdruck erkennbar — ohne
    dass man 110 Felder von Hand vergleichen muss."""
    form = {"A": (500, "2024-08-05", "2026-08-04"), "B": (499, "2024-08-06", "2026-08-04")}
    assert pipe.series_summary(form)["shape_digest"] == pipe.series_summary(dict(form))["shape_digest"]


@pytest.mark.parametrize("aenderung", [
    {"A": (499, "2024-08-05", "2026-08-04")},                 # eine Zeile weniger
    {"A": (500, "2024-08-06", "2026-08-04")},                 # anderer Reihenstart
    {"A": (500, "2024-08-05", "2026-08-03")},                 # anderes Ende
])
def test_jede_formaenderung_aendert_den_abdruck(aenderung):
    basis = {"A": (500, "2024-08-05", "2026-08-04"), "B": (499, "2024-08-06", "2026-08-04")}
    anders = dict(basis); anders.update(aenderung)
    assert pipe.series_summary(basis)["shape_digest"] != pipe.series_summary(anders)["shape_digest"]


def test_ein_zusaetzlicher_ticker_aendert_den_abdruck():
    basis = {"A": (500, "2024-08-05", "2026-08-04")}
    mehr = dict(basis); mehr["B"] = (500, "2024-08-05", "2026-08-04")
    assert pipe.series_summary(basis)["shape_digest"] != pipe.series_summary(mehr)["shape_digest"]


def test_der_abdruck_ist_kurz_und_hexadezimal():
    q = pipe.series_summary({"A": (1, "2026-08-04", "2026-08-04")})
    assert len(q["shape_digest"]) == 12
    assert all(c in "0123456789abcdef" for c in q["shape_digest"])


# ---------------------------------------------------------------------------
# Im Lauf verdrahtet — und REIN BESCHREIBEND
# ---------------------------------------------------------------------------
def _fetcher(reihen):
    def f(ticker):
        d = reihen.get(ticker)
        if d is None:
            return pipe.FetchOutcome(None, pipe.EMPTY_DATA, "leer")
        return pipe.FetchOutcome(d)
    return f


def _reihe(n, ende="2026-08-04"):
    import datetime as _dt
    e = _dt.date.fromisoformat(ende)
    tage, kurse = [], []
    for i in range(n):
        tage.append(str(e - _dt.timedelta(days=n - 1 - i)))
        kurse.append(100.0 + (i % 7))
    return (tage, kurse)


def test_scan_market_fuellt_den_sink_mit_der_verwertbaren_reihe():
    reihen = {"A": _reihe(60), "B": _reihe(30, "2026-08-03"), "TOT": None}
    sink = {}
    pipe._scan_market(list(reihen), _fetcher(reihen), None, None, sink)
    assert set(sink) == {"A", "B"}, "tote Ticker haben keine Reihe"
    assert sink["A"][0] == 60 and sink["B"][0] == 30
    assert sink["A"][2] == "2026-08-04" and sink["B"][2] == "2026-08-03"


def test_der_sink_ist_optional_und_veraendert_nichts():
    """Ohne Sink läuft der Scan wie vorher — die Diagnose darf das Ergebnis
    nicht anfassen."""
    reihen = {"A": _reihe(60), "B": _reihe(60)}
    ohne = pipe._scan_market(list(reihen), _fetcher(reihen))
    mit = pipe._scan_market(list(reihen), _fetcher(reihen), None, None, {})
    assert ohne[0] == mit[0], "Kandidaten unterscheiden sich"
    assert ohne[1] == mit[1], "Skip-Zähler unterscheiden sich"
    assert ohne[5] == mit[5], "letztes Bar-Datum unterscheidet sich"


def test_kein_score_kein_filter_liest_die_neuen_felder():
    """Die harte Zusage: rein beschreibend. Wer `series` in einer Rechnung
    liest, hebelt genau die Trennung aus, die diesen PR harmlos macht."""
    verboten = ("score", "filter", "rank")
    for f in sorted((ROOT / "scripts").glob("*.py")):
        text = f.read_text(encoding="utf-8")
        for i, zeile in enumerate(text.split("\n"), 1):
            if "series_summary" in zeile or '"series"' in zeile or "shape_digest" in zeile:
                assert not any(v in zeile.lower() for v in verboten), \
                    f"{f.name}:{i} mischt die Diagnose in eine Rechnung: {zeile.strip()}"
    # und die Sammlung fasst sie gar nicht erst an
    fc = (ROOT / "scripts/forward_collection.py").read_text(encoding="utf-8")
    for feld in ("series_summary", "shape_digest", "bars_median", "tickers_at_last_bar"):
        assert feld not in fc, f"die Sammlung liest {feld}"


def test_watchlist_eintraege_tragen_den_markt_schluessel():
    """Für den Karten-Hinweis braucht die Watchlist-Karte den Markt — die
    Zuordnung passiert in Python, nicht im Frontend."""
    assert pipe._market_of("SAP.DE") in ("DE", None)
    # ein Ticker aus dem echten Universum wird zugeordnet …
    de = list(pipe.config.MARKETS["DE"]["universe"])[:1]
    us = list(pipe.config.MARKETS["US"]["universe"])[:1]
    assert pipe._market_of(de[0]) == "DE"
    assert pipe._market_of(us[0]) == "US"
    assert pipe._market_of(de[0].lower()) == "DE", "Groß-/Kleinschreibung darf nicht entscheiden"
    # … ein fremder bleibt ohne Markt (kein Hinweis aus einem fremden Markt)
    assert pipe._market_of("GIBTESNICHT.XY") is None
    assert pipe._market_of("") is None and pipe._market_of(None) is None


def test_der_journal_knopf_bleibt_unberuehrt():
    """`market_key` heißt bewusst NICHT `market`: die Karten geben dem
    Journal-Knopf `c.market || ''` mit. Ein Feld `market` würde still ändern,
    was ins Journal geschrieben wird — das wäre eine Datenänderung."""
    assert 'e["market_key"] = _market_of(tk)' in \
        (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    assert "tjAddBtn(c, c.market || '')" in HTML
    assert "tjAddBtn(c, c.market_key" not in HTML


# ---------------------------------------------------------------------------
# (b) Frontend
# ---------------------------------------------------------------------------
def test_kein_zweiter_handelskalender_in_javascript():
    """Die harte Vorgabe. Der Hinweis darf NUR formatieren, was der Report
    fertig mitbringt — sonst laufen zwei Kalender beim nächsten Feiertag
    auseinander."""
    start = HTML.index("    function standHinweis(stand) {")
    koerper = HTML[start:HTML.index("\n    }", start)]
    assert "stand.lag" in koerper and "Number(stand.lag)" in koerper
    for verboten in ("getDay()", "getDate()", "new Date(", "Feiertag", "holiday",
                     "handelstag", "trading_day", "setDate("):
        assert verboten not in koerper, f"Kalender-Code im Karten-Hinweis: {verboten}"


def test_der_hinweis_liest_die_fertige_zahl_aus_dem_report():
    start = HTML.index("    function marktStand(market) {")
    koerper = HTML[start:HTML.index("\n    }", start)]
    assert "d.bar_lag_trading_days" in koerper and "d.last_bar_date" in koerper


def test_der_hinweis_haengt_an_allen_drei_kartenarten():
    assert "function card(c, rank, stand) {" in HTML
    assert "${standHinweis(stand)}" in HTML                      # volle Karte
    assert "${right}${isErr ? '' : standHinweis(stand)}" in HTML  # Kompaktkachel
    assert "return card(c, '☆', stand);" in HTML                 # aufgeklappte WL-Karte
    assert "card(c, i + 1, stand)" in HTML                       # Markt-Karten


def test_die_lauf_status_zeile_existiert_und_rechnet_nicht():
    start = HTML.index("      function seriesRow(d) {")
    koerper = HTML[start:HTML.index("\n      }", start)]
    for feld in ("q.tickers", "q.bars_min", "q.bars_median", "q.bars_max",
                 "q.tickers_at_last_bar", "q.last_bar_max", "q.first_bar_min",
                 "q.shape_digest"):
        assert feld in koerper, f"{feld} fehlt in der Lauf-Status-Zeile"
    assert "${seriesRow(d)}" in HTML


_NODE = shutil.which("node") or shutil.which("nodejs")


def _fn(name: str, tiefe: str = "    ") -> str:
    marke = f"{tiefe}function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken dieselben Fälle")
    # `esc` wird AUS DER SEITE gezogen, nicht nachgebaut (Guardian-Nit
    # 05.08.2026): ein handgeschriebener Double war hier ohne null-Guard und
    # damit freundlicher als das Original — ein Test soll nie an einer
    # Nachbildung vorbeimessen.
    quelle = "\n".join([_fn("esc"), _fn("standHinweis"), _fn("marktStand"),
                        _fn("seriesRow", "      ")])
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("lag", [0, None, "", "keine-zahl", -1, float("nan")])
def test_ohne_rueckstand_ist_der_hinweis_unsichtbar(lag):
    """Rückstand 0 -> nichts. Auch kaputte/fehlende Werte erzeugen keinen Text
    (ein Hinweis, der immer da ist, sagt nichts mehr)."""
    v = "NaN" if isinstance(lag, float) else json.dumps(lag)
    assert _js(f"console.log(JSON.stringify(standHinweis("
               f"{{date:'2026-08-04', lag:{v}}})))") == ""


def test_ohne_stand_ueberhaupt_kein_hinweis():
    """Älterer Report ohne die Felder -> kein „undefined", kein Absturz."""
    for eingang in ("null", "undefined", "{}", "{date:null, lag:undefined}"):
        erg = _js(f"console.log(JSON.stringify(standHinweis({eingang})))")
        assert erg == ""


@pytest.mark.parametrize("lag, datum, soll", [
    (1, "2026-08-03", "Kurse vom 03.08. — 1 Handelstag zurück"),
    (2, "2026-07-31", "Kurse vom 31.07. — 2 Handelstage zurück"),
    (5, "2026-07-28", "Kurse vom 28.07. — 5 Handelstage zurück"),
    (1, None, "1 Handelstag zurück"),          # ohne Datum: nur der Rückstand
])
def test_der_hinweistext_ist_von_hand_gegengelesen(lag, datum, soll):
    erg = _js(f"console.log(JSON.stringify(standHinweis("
              f"{{date:{json.dumps(datum)}, lag:{lag}}})))")
    assert soll in erg
    assert "undefined" not in erg and "NaN" not in erg and "null" not in erg
    assert 'class="bar-stand"' in erg


def test_ein_unerwartetes_datumsformat_wird_unveraendert_gezeigt():
    """Lieber roh als falsch umgeformt."""
    erg = _js("console.log(JSON.stringify(standHinweis({date:'04.08.2026', lag:1})))")
    assert "04.08.2026" in erg


def test_marktStand_liest_nur_was_da_ist():
    erg = _js("""console.log(JSON.stringify([
      marktStand(null), marktStand({}), marktStand({diag:{}}),
      marktStand({diag:{last_bar_date:'2026-08-03', bar_lag_trading_days:1}})]))""")
    assert erg[0] is None and erg[1] is None
    assert erg[2] == {"date": None}          # kein lag -> Feld fehlt/undefined
    assert erg[3] == {"date": "2026-08-03", "lag": 1}


def test_die_lauf_status_zeile_bleibt_bei_altem_report_leer():
    for eingang in ("{}", "{series:null}", "{series:'kaputt'}", "{series:{}}",
                    "{series:{tickers:0}}"):
        assert _js(f"console.log(JSON.stringify(seriesRow({eingang})))") == ""


def test_die_lauf_status_zeile_zeigt_die_werte_aus_dem_report():
    erg = _js("""console.log(JSON.stringify(seriesRow({series:{
      schema:1, tickers:117, bars_min:120, bars_median:500, bars_max:502,
      first_bar_min:'2024-08-05', last_bar_max:'2026-08-04',
      tickers_at_last_bar:1, shape_digest:'3f9a1c2b4d5e'}})))""")
    for teil in ("117 Ticker", "120 / 500 / 502", "(min / Median / max)",
                 "jüngster Bar 2026-08-04 bei 1 von 117",
                 "ältester Reihenstart 2024-08-05", "Abdruck 3f9a1c2b4d5e"):
        assert teil in erg, f"fehlt: {teil}"
    assert "undefined" not in erg and "NaN" not in erg


def test_eine_LEERE_reihe_landet_nicht_im_sink_und_wirft_nicht():
    """Nachgezogen (Mutationsprobe 5 hatte überlebt): die Wache `and dates`
    fängt den Fall „Outcome vorhanden, Reihe aber leer". Ohne sie greift
    `dates[0]` ins Leere und der ganze Lauf stirbt an einem Ticker — genau die
    Sorte Absturz, die eine reine Diagnose niemals auslösen darf."""
    reihen = {"LEER": ([], []), "GUT": _reihe(40)}
    sink = {}
    ergebnis = pipe._scan_market(list(reihen), _fetcher(reihen), None, None, sink)
    assert set(sink) == {"GUT"}, "die leere Reihe darf keinen Eintrag erzeugen"
    assert sink["GUT"][0] == 40
    assert ergebnis is not None, "der Lauf muss weiterlaufen"
    # und die Zusammenfassung bleibt rechenbar
    q = pipe.series_summary(sink)
    assert q["tickers"] == 1 and q["bars_min"] == 40


def test_der_hinweis_maskiert_report_werte():
    """Die Werte kommen aus einer Datei im Repo — sie gehen durch `esc`, bevor
    sie HTML werden. Geprüft mit der ECHTEN `esc`-Funktion der Seite."""
    erg = _js("""console.log(JSON.stringify(standHinweis(
      {date:'<img src=x onerror=alert(1)>', lag:2})))""")
    assert "<img" not in erg and "&lt;img" in erg


def test_die_lauf_status_zeile_maskiert_den_abdruck():
    erg = _js("""console.log(JSON.stringify(seriesRow({series:{
      tickers:2, bars_min:1, bars_median:1, bars_max:1,
      last_bar_max:'<b>x</b>', tickers_at_last_bar:1,
      first_bar_min:'2026-01-01', shape_digest:'<script>'}})))""")
    assert "<b>" not in erg and "&lt;b&gt;" in erg
    assert "<script>" not in erg
