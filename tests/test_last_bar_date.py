"""`last_bar_date` — der WERT, nicht nur die Anwesenheit des Feldes.

Guardian-Nit zu diesem PR: `test_schema.py` hielt nur fest, dass der Schlüssel
im Diag-Vertrag steht. Die Mutation `dates[0]` statt `dates[-1]` — ein stiller
Vertausch von ERSTEM und LETZTEM Handelstag — blieb damit über alle Tests
grün. Genau dieselbe Klasse wie der #59-Nit (Quelltext-Nähe statt Laufzeit).

Deshalb hier: unterschiedlich endende Reihen, deren ERSTE Daten absichtlich in
umgekehrter Reihenfolge liegen. Wer `dates[0]` nimmt, bekommt zwangsläufig ein
anderes Ergebnis.
"""
import datetime as _dt

import config
import elliott_pipeline as pipe


def _reihe(ticker: str, letzter_tag: str, laenge: int):
    """Synthetische Kursreihe, die auf `letzter_tag` endet.

    Die Kurse kommen unverändert aus `fetch_synthetic` (gültige Elliott-Form),
    nur die Datumsachse wird neu gelegt — Werktage rückwärts vom Ende.
    """
    _d, closes = pipe.fetch_synthetic(ticker).data
    closes = list(closes)[-laenge:]
    ende = _dt.date.fromisoformat(letzter_tag)
    dates: list[str] = []
    tag = ende
    while len(dates) < len(closes):
        if tag.weekday() < 5:
            dates.append(tag.isoformat())
        tag -= _dt.timedelta(days=1)
    dates.reverse()
    return dates, closes


def test_last_bar_date_ist_der_JUENGSTE_handelstag_im_markt():
    # AAA endet am spätesten, beginnt aber am FRÜHESTEN (längste Reihe);
    # CCC endet am frühesten, beginnt am SPÄTESTEN (kürzeste Reihe).
    reihen = {
        "AAA": _reihe("AAA", "2026-07-29", 32),
        "BBB": _reihe("BBB", "2026-07-28", 24),
        "CCC": _reihe("CCC", "2026-07-24", 16),
    }
    erste = {t: d[0] for t, (d, _c) in reihen.items()}
    letzte = {t: d[-1] for t, (d, _c) in reihen.items()}
    # Vorbedingung des Tests: erste und letzte Daten ordnen GEGENLÄUFIG.
    assert max(letzte.values()) == letzte["AAA"]
    assert min(erste.values()) == erste["AAA"]
    assert max(erste.values()) == erste["CCC"]

    def fetcher(ticker):
        d, c = reihen[ticker]
        return pipe.FetchOutcome(data=(list(d), list(c)))

    *_rest, letztes_bar = pipe._scan_market(list(reihen), fetcher)

    assert letztes_bar == "2026-07-29"
    # Und ausdrücklich NICHT das erste Datum irgendeiner Reihe (die Mutation).
    assert letztes_bar not in set(erste.values())


def test_last_bar_date_zaehlt_auch_ticker_ohne_kandidat():
    """Der Kursstand des Marktes hängt an den DATEN, nicht an der Kandidatur.

    Ein Ticker, der die Elliott-Prüfung nicht besteht, hat trotzdem aktuelle
    Kurse geliefert — sonst würde ein Markt mit lauter Absagen als „keine
    Kurse" dastehen.
    """
    gut_d, gut_c = _reihe("GUT", "2026-07-27", 400)
    spaet_d, _c = _reihe("SPAET", "2026-07-29", 400)
    flach = [100.0] * len(spaet_d)  # flache Reihe -> kein gültiger Count

    def fetcher(ticker):
        if ticker == "GUT":
            return pipe.FetchOutcome(data=(list(gut_d), list(gut_c)))
        return pipe.FetchOutcome(data=(list(spaet_d), list(flach)))

    candidates, _rc, _s, _dead, _bad, letztes_bar = pipe._scan_market(
        ["GUT", "FLACH"], fetcher)

    assert [c["ticker"] for c in candidates] == ["GUT"]
    assert letztes_bar == "2026-07-29"  # aus dem Ticker OHNE Kandidat


def test_last_bar_date_ist_None_wenn_kein_ticker_kurse_liefert():
    def fetcher(ticker):
        return pipe.FetchOutcome(data=None, reason=pipe.EMPTY_DATA,
                                 detail="leer")

    candidates, _rc, _s, dead, _bad, letztes_bar = pipe._scan_market(
        ["X", "Y"], fetcher)

    assert candidates == []
    assert len(dead) == 2
    assert letztes_bar is None


def test_last_bar_date_meldet_das_letzte_GUELTIGE_bar():
    """Verworfene Zeilen dürfen den Kursstand nicht vordatieren.

    `_extract_bars` filtert nicht-endliche Bars heraus; was danach als
    `data` ankommt, ist die bereinigte Reihe. Der Report muss den Tag melden,
    der wirklich angekommen ist — nicht den, den die Quelle nominell hatte.
    """
    dates, closes = _reihe("TEIL", "2026-07-29", 400)
    # Die letzten zwei Zeilen fallen weg (der DE-Fall vom 29.07.).
    bereinigt_d, bereinigt_c = dates[:-2], closes[:-2]

    def fetcher(ticker):
        return pipe.FetchOutcome(data=(list(bereinigt_d), list(bereinigt_c)),
                                 dropped_bars=2,
                                 dropped_dates=tuple(dates[-2:]),
                                 dropped_last_row=1, dropped_mid_row=1)

    *_rest, letztes_bar = pipe._scan_market(["TEIL"], fetcher)

    assert letztes_bar == bereinigt_d[-1]
    assert letztes_bar != dates[-1]  # NICHT der nominelle letzte Tag


def test_last_bar_date_landet_unveraendert_im_report(monkeypatch):
    """Vom Scan bis in den Report: derselbe Wert, kein zweiter Pfad."""
    reihen = {
        "R1": _reihe("R1", "2026-07-29", 32),
        "R2": _reihe("R2", "2026-07-23", 24),
    }
    markt_cfg = dict(config.MARKETS["US"], universe=list(reihen))
    monkeypatch.setitem(config.MARKETS, "US", markt_cfg)

    def fetcher(ticker):
        d, c = reihen[ticker]
        return pipe.FetchOutcome(data=(list(d), list(c)))

    markt = pipe.build_market("US", fetcher)

    assert markt["diag"]["last_bar_date"] == "2026-07-29"
    # Gegenprobe: es ist nicht irgendein Datum aus der Reihe, sondern das Ende.
    assert markt["diag"]["last_bar_date"] == reihen["R1"][0][-1]
