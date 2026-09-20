"""Alpha-Vantage-Notfall-Fallback (Diagnose #132/#134/#135, NUR DE-Ticker).

Deckt den AUFTRAG direkt ab:
  - Wert-Test mit den 5 echten DE-Tickern aus der Diagnose (SAP.DE, SIE.DE,
    ALV.DE, DTE.DE, AIR.DE): der eigene Adapter liefert korrekte,
    aufsteigend sortierte Float-Reihen aus Alpha Vantages verschachteltem
    "1. open"-Dict.
  - Regressionstest: ein normaler yfinance-Erfolg nutzt WEITERHIN nur
    yfinance — Alpha Vantage wird dabei nie angefasst.
  - US-Ticker und fehlendes Secret lösen NIE einen Fallback-Versuch aus.
  - Rate-Limit: nur einzelne fehlgeschlagene Ticker nutzen den Fallback,
    nie das ganze Universum (Obergrenze je Lauf).
  - Symbol-Kandidaten: scheitert das erste Format, wird das nächste
    probiert (Diagnose #135).
  - Key-Exposure: der API-Key wird NIE unredigiert in einer Fehlerausgabe
    sichtbar — inkl. Netzfehler UND strukturierter API-Fehlerantworten
    (Error Message/Note/Information).
  - get_fetcher(): DE- und US-Ticker landen beim jeweils richtigen
    Fallback, ohne doppelten yfinance-Call.
  - Transparenz: erfolgreiche Fallback-Ticker sind im Report klar markiert
    (`data_source`), konsistent mit #134.

Kein Netz: `pipe._alphavantage_get` wird ersetzt (Muster wie
`pipe._twelvedata_get` in test_twelvedata_fallback.py).
"""
import config
import elliott_pipeline as pipe

DE_TICKER_DIAGNOSE = ["SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE"]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _av_time_series(n=100, start_close=100.0):
    """Alpha-Vantage-typische 'Time Series (Daily)': verschachteltes Dict,
    numerisch präfigierte Spaltennamen, alle Werte als STRINGS (exakt die
    Form aus der Live-Diagnose #135)."""
    import datetime as _dt

    out = {}
    tag = _dt.date(2026, 1, 1) + _dt.timedelta(days=n)
    for i in range(n):
        close = start_close + (n - 1 - i)  # aufsteigende Ramp über die Zeit
        out[tag.isoformat()] = {
            "1. open": f"{close - 0.5:.4f}",
            "2. high": f"{close + 1:.4f}",
            "3. low": f"{close - 1:.4f}",
            "4. close": f"{close:.4f}",
            "5. volume": str(1000 + i),
        }
        tag -= _dt.timedelta(days=1)
    return out  # jüngster Tag zuerst (Dict-Reihenfolge wie live beobachtet)


def _set_key(monkeypatch, value="dummy-av-key"):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", value)


# ---------------------------------------------------------------------------
# fetch_alphavantage + Adapter — Wert-Test mit den 5 echten DE-Tickern
# ---------------------------------------------------------------------------
def test_fetch_alphavantage_erfolg_fuer_alle_5_diagnose_ticker(monkeypatch):
    _set_key(monkeypatch)
    for ticker in DE_TICKER_DIAGNOSE:
        ts = _av_time_series(n=100, start_close=100.0)
        monkeypatch.setattr(
            pipe, "_alphavantage_get",
            lambda params, timeout, _ts=ts: _FakeResponse(
                {"Time Series (Daily)": _ts}
            ),
        )
        outcome = pipe.fetch_alphavantage(ticker)
        assert outcome.reason is None, (ticker, outcome.detail)
        assert outcome.data is not None
        dates, closes = outcome.data
        assert len(closes) == 100
        # ABSTEIGEND rein -> AUFSTEIGEND raus (Adapter-Kernaufgabe).
        assert dates == sorted(dates)
        # "1. open"-Praefix korrekt auf Open/Close etc. gemappt + float.
        assert closes[0] == 100.0
        assert closes[-1] == 199.0
        assert all(isinstance(c, float) for c in closes)
        assert outcome.source == "alphavantage_fallback"


def test_fetch_alphavantage_kein_api_key_ist_fail_soft(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    outcome = pipe.fetch_alphavantage("SAP.DE")
    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR
    assert "ALPHA_VANTAGE_API_KEY" in outcome.detail
    assert outcome.source == "yfinance"  # Default unverändert


# ---------------------------------------------------------------------------
# Symbol-Kandidaten (Diagnose #135: welches Format greift)
# ---------------------------------------------------------------------------
def test_fetch_alphavantage_faellt_auf_naechsten_symbol_kandidaten_zurueck(monkeypatch):
    _set_key(monkeypatch)
    ts = _av_time_series(n=100)
    tried = []

    def _fake(params, timeout):
        tried.append(params["symbol"])
        if params["symbol"] == "SAP.DE":
            return _FakeResponse({"Error Message": "Invalid API call"})
        if params["symbol"] == "SAP.DEX":
            return _FakeResponse({"Time Series (Daily)": ts})
        raise AssertionError("dritter Kandidat haette nicht gebraucht werden duerfen")

    monkeypatch.setattr(pipe, "_alphavantage_get", _fake)
    outcome = pipe.fetch_alphavantage("SAP.DE")

    assert tried == ["SAP.DE", "SAP.DEX"]
    assert outcome.data is not None
    assert outcome.source == "alphavantage_fallback"


def test_fetch_alphavantage_alle_kandidaten_scheitern(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        pipe, "_alphavantage_get",
        lambda params, timeout: _FakeResponse({"Error Message": "Invalid API call"}),
    )
    outcome = pipe.fetch_alphavantage("SAP.DE")
    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR


def test_alphavantage_candidates_nur_fuer_de_ticker_mehrere():
    assert pipe._alphavantage_candidates("SAP.DE") == ["SAP.DE", "SAP.DEX", "XETRA:SAP"]
    assert pipe._alphavantage_candidates("AAPL") == ["AAPL"]


# ---------------------------------------------------------------------------
# Key-Exposure — von Anfang an, nicht nachträglich (Lehre aus #134)
# ---------------------------------------------------------------------------
def test_fetch_alphavantage_netzfehler_redigiert_den_api_key(monkeypatch):
    geheim = "sk-super-geheimer-av-key"
    _set_key(monkeypatch, value=geheim)

    def _raise(params, timeout):
        raise ConnectionError(
            f"Connection refused: https://www.alphavantage.co/query"
            f"?symbol=SAP.DE&apikey={geheim}"
        )

    monkeypatch.setattr(pipe, "_alphavantage_get", _raise)
    outcome = pipe.fetch_alphavantage("SAP.DE")
    assert outcome.data is None
    assert geheim not in outcome.detail
    assert "***" in outcome.detail


def test_fetch_alphavantage_api_fehlermeldung_redigiert_key_falls_enthalten(monkeypatch):
    """Die API-Fehlerantwort selbst enthaelt den Key normalerweise nicht --
    aber falls Alpha Vantage ihn je in "Error Message"/"Note"/"Information"
    spiegelt (z. B. Rate-Limit-Text mit dem eigenen Query), darf er nicht
    durchrutschen."""
    geheim = "sk-super-geheimer-av-key"
    _set_key(monkeypatch, value=geheim)
    monkeypatch.setattr(
        pipe, "_alphavantage_get",
        lambda params, timeout: _FakeResponse(
            {"Note": f"Rate limit erreicht fuer Key {geheim}, bitte spaeter erneut."}
        ),
    )
    outcome = pipe.fetch_alphavantage("SAP.DE")
    assert outcome.data is None
    assert geheim not in outcome.detail
    assert "***" in outcome.detail


def test_fetch_alphavantage_information_feld_wird_erkannt(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        pipe, "_alphavantage_get",
        lambda params, timeout: _FakeResponse(
            {"Information": "Thank you for using Alpha Vantage! Premium erforderlich."}
        ),
    )
    outcome = pipe.fetch_alphavantage("SAP.DE")
    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR
    assert "Premium" in outcome.detail


def test_fetch_alphavantage_leere_time_series(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        pipe, "_alphavantage_get",
        lambda params, timeout: _FakeResponse({}),
    )
    outcome = pipe.fetch_alphavantage("SAP.DE")
    assert outcome.data is None
    assert outcome.reason == pipe.EMPTY_DATA


# ---------------------------------------------------------------------------
# _make_yfinance_with_av_fallback — WANN springt der Fallback ein?
# ---------------------------------------------------------------------------
def _stub_yfinance_fail(monkeypatch, reason=None):
    reason = reason or pipe.EMPTY_DATA
    monkeypatch.setattr(
        pipe, "fetch_yfinance",
        lambda ticker: pipe.FetchOutcome(reason=reason, detail="yfinance leer"),
    )


def _stub_yfinance_success(monkeypatch):
    d, c = pipe.fetch_synthetic("OK").data
    monkeypatch.setattr(
        pipe, "fetch_yfinance",
        lambda ticker: pipe.FetchOutcome(data=(d, c)),
    )


def _stub_alphavantage_spy(monkeypatch, calls):
    def _fake(ticker):
        calls.append(ticker)
        d, c = pipe.fetch_synthetic(ticker).data
        return pipe.FetchOutcome(data=(d, c), source="alphavantage_fallback")

    monkeypatch.setattr(pipe, "fetch_alphavantage", _fake)


def test_fallback_greift_bei_fehlgeschlagenem_de_ticker(monkeypatch):
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_alphavantage_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_av_fallback()
    outcome = fetcher("SAP.DE")

    assert calls == ["SAP.DE"]
    assert outcome.data is not None
    assert outcome.source == "alphavantage_fallback"


def test_regression_erfolgreiches_yfinance_nutzt_KEINEN_fallback(monkeypatch):
    """Kern-Regressionstest des Auftrags: normaler Erfolg bleibt reines
    yfinance — Alpha Vantage wird dabei nicht einmal ANGEFASST."""
    _set_key(monkeypatch)
    _stub_yfinance_success(monkeypatch)
    calls = []
    _stub_alphavantage_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_av_fallback()
    outcome = fetcher("SAP.DE")

    assert calls == []  # Alpha Vantage NIE aufgerufen
    assert outcome.source == "yfinance"


def test_fallback_NICHT_fuer_us_ticker(monkeypatch):
    """Grenzen des Auftrags: US bleibt #134 vorbehalten."""
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_alphavantage_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_av_fallback()
    outcome = fetcher("AAPL")

    assert calls == []
    assert outcome.data is None
    assert outcome.source == "yfinance"


def test_fallback_ohne_secret_ist_no_op(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_alphavantage_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_av_fallback()
    outcome = fetcher("SAP.DE")

    assert calls == []
    assert outcome.data is None


def test_fallback_selbst_fehlgeschlagen_gibt_original_yfinance_grund_zurueck(monkeypatch):
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch, reason=pipe.FETCH_ERROR)
    monkeypatch.setattr(
        pipe, "fetch_alphavantage",
        lambda ticker: pipe.FetchOutcome(reason=pipe.FETCH_ERROR, detail="auch tot"),
    )

    fetcher = pipe._make_yfinance_with_av_fallback()
    outcome = fetcher("SAP.DE")

    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR
    assert outcome.detail == "yfinance leer"  # der URSPRÜNGLICHE Grund, nicht überschrieben


# ---------------------------------------------------------------------------
# Rate-Limit: NUR einzelne Ticker, nie das ganze Universum
# ---------------------------------------------------------------------------
def test_fallback_rate_limit_deckelt_calls_pro_lauf(monkeypatch):
    monkeypatch.setattr(config, "ALPHA_VANTAGE_MAX_FALLBACK_CALLS", 2)
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_alphavantage_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_av_fallback()
    de_tickers = ["SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE"]
    outcomes = [fetcher(t) for t in de_tickers]

    assert len(calls) == 2  # gedeckelt, NICHT alle 5
    assert outcomes[0].source == "alphavantage_fallback"
    assert outcomes[1].source == "alphavantage_fallback"
    assert outcomes[2].data is None
    assert outcomes[3].data is None
    assert outcomes[4].data is None


def test_fallback_zaehler_ist_PRO_FETCHER_nicht_global(monkeypatch):
    monkeypatch.setattr(config, "ALPHA_VANTAGE_MAX_FALLBACK_CALLS", 1)
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_alphavantage_spy(monkeypatch, calls)

    fetcher_a = pipe._make_yfinance_with_av_fallback()
    fetcher_a("SAP.DE")
    fetcher_b = pipe._make_yfinance_with_av_fallback()
    fetcher_b("SIE.DE")

    assert calls == ["SAP.DE", "SIE.DE"]  # beide kamen durch — getrennte Klausuren


# ---------------------------------------------------------------------------
# get_fetcher()-Verdrahtung: US -> Twelve Data, DE -> Alpha Vantage, EIN
# yfinance-Call je Ticker
# ---------------------------------------------------------------------------
def test_get_fetcher_dispatcht_de_an_alphavantage(monkeypatch):
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)
    _set_key(monkeypatch)
    yf_calls = []

    def _yf(ticker):
        yf_calls.append(ticker)
        return pipe.FetchOutcome(reason=pipe.EMPTY_DATA, detail="leer")

    monkeypatch.setattr(pipe, "fetch_yfinance", _yf)
    av_calls = []
    _stub_alphavantage_spy(monkeypatch, av_calls)
    td_calls = []
    monkeypatch.setattr(
        pipe, "fetch_twelvedata",
        lambda ticker: (td_calls.append(ticker) or pipe.FetchOutcome(
            data=pipe.fetch_synthetic(ticker).data, source="twelvedata_fallback",
        )),
    )

    fetcher = pipe.get_fetcher()
    outcome = fetcher("SAP.DE")

    assert yf_calls == ["SAP.DE"]  # GENAU EINMAL yfinance versucht
    assert av_calls == ["SAP.DE"]
    assert td_calls == []  # Twelve Data nie angefasst fuer einen DE-Ticker
    assert outcome.source == "alphavantage_fallback"


def test_get_fetcher_dispatcht_us_an_twelvedata(monkeypatch):
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "dummy-td-key")
    _set_key(monkeypatch)
    yf_calls = []

    def _yf(ticker):
        yf_calls.append(ticker)
        return pipe.FetchOutcome(reason=pipe.EMPTY_DATA, detail="leer")

    monkeypatch.setattr(pipe, "fetch_yfinance", _yf)
    av_calls = []
    _stub_alphavantage_spy(monkeypatch, av_calls)
    td_calls = []
    monkeypatch.setattr(
        pipe, "fetch_twelvedata",
        lambda ticker: (td_calls.append(ticker) or pipe.FetchOutcome(
            data=pipe.fetch_synthetic(ticker).data, source="twelvedata_fallback",
        )),
    )

    fetcher = pipe.get_fetcher()
    outcome = fetcher("AAPL")

    assert yf_calls == ["AAPL"]  # GENAU EINMAL yfinance versucht
    assert td_calls == ["AAPL"]
    assert av_calls == []  # Alpha Vantage nie angefasst fuer einen US-Ticker
    assert outcome.source == "twelvedata_fallback"


def test_get_fetcher_offline_bleibt_synthetisch_ohne_fallback(monkeypatch):
    monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
    assert pipe.get_fetcher() is pipe.fetch_synthetic


# ---------------------------------------------------------------------------
# Transparenz im Report: data_source auf dem Kandidaten-Eintrag
# ---------------------------------------------------------------------------
def test_scan_market_markiert_alphavantage_fallback_kandidaten_transparent(monkeypatch):
    _set_key(monkeypatch)
    d_ok, c_ok = pipe.fetch_synthetic("YF").data
    d_fb, c_fb = pipe.fetch_synthetic("FB.DE").data

    def fetcher(ticker):
        if ticker == "YF":
            return pipe.FetchOutcome(data=(list(d_ok), list(c_ok)))
        return pipe.FetchOutcome(
            data=(list(d_fb), list(c_fb)), source="alphavantage_fallback",
        )

    candidates, *_rest = pipe._scan_market(["YF", "FB.DE"], fetcher)
    by_ticker = {c["ticker"]: c for c in candidates}

    assert by_ticker["YF"]["data_source"] == "yfinance"
    assert by_ticker["FB.DE"]["data_source"] == "alphavantage_fallback"
    assert "score_heuristic" in by_ticker["FB.DE"]
