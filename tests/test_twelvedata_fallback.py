"""Twelve-Data-Notfall-Fallback (Diagnose #132/#133, NUR US-Ticker).

Deckt den AUFTRAG direkt ab:
  - Wert-Test mit den 5 echten US-Tickern aus der Diagnose (AAPL, MSFT,
    NVDA, AVGO, ORCL): der Adapter liefert korrekte, aufsteigend sortierte
    Float-Reihen aus Twelve Datas absteigend sortierter String-Antwort.
  - Regressionstest: ein normaler yfinance-Erfolg nutzt WEITERHIN nur
    yfinance — Twelve Data wird dabei nie angefasst.
  - DE-Ticker und fehlendes Secret lösen NIE einen Fallback-Versuch aus.
  - Rate-Limit: nur einzelne fehlgeschlagene Ticker nutzen den Fallback,
    nie das ganze Universum (Obergrenze je Lauf).
  - Transparenz: erfolgreiche Fallback-Ticker sind im Report klar markiert
    (`data_source`), ohne Score/Ranking zu berühren.

Kein Netz: `pipe._twelvedata_get` wird ersetzt (Muster wie `notify._post` in
test_notify.py) — dieselbe Isolation wie überall sonst im Repo.
"""
import config
import elliott_pipeline as pipe

US_TICKER_DIAGNOSE = ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL"]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _td_values(n=120, start_close=100.0):
    """Twelve-Data-typische `values`: ABSTEIGEND sortiert, alle Werte als
    STRINGS (exakt die Form aus der Live-Diagnose #133)."""
    import datetime as _dt

    out = []
    tag = _dt.date(2026, 1, 1) + _dt.timedelta(days=n)
    for i in range(n):
        close = start_close + (n - 1 - i)  # aufsteigende Ramp über die Zeit
        out.append({
            "datetime": tag.isoformat(),
            "open": f"{close - 0.5:.4f}",
            "high": f"{close + 1:.4f}",
            "low": f"{close - 1:.4f}",
            "close": f"{close:.4f}",
            "volume": str(1000 + i),
        })
        tag -= _dt.timedelta(days=1)
    return out  # index 0 = jüngster Tag (absteigend), wie echt bei Twelve Data


def _set_key(monkeypatch, value="dummy-key"):
    monkeypatch.setenv("TWELVE_DATA_API_KEY", value)


# ---------------------------------------------------------------------------
# fetch_twelvedata + Adapter — Wert-Test mit den 5 echten US-Tickern
# ---------------------------------------------------------------------------
def test_fetch_twelvedata_erfolg_fuer_alle_5_diagnose_ticker(monkeypatch):
    _set_key(monkeypatch)
    for ticker in US_TICKER_DIAGNOSE:
        values = _td_values(n=120, start_close=100.0)
        monkeypatch.setattr(
            pipe, "_twelvedata_get",
            lambda params, timeout, _v=values: _FakeResponse({"values": _v}),
        )
        outcome = pipe.fetch_twelvedata(ticker)
        assert outcome.reason is None, (ticker, outcome.detail)
        assert outcome.data is not None
        dates, closes = outcome.data
        assert len(closes) == 120
        # ABSTEIGEND rein -> AUFSTEIGEND raus (Adapter-Kernaufgabe).
        assert dates == sorted(dates)
        # Strings korrekt zu float konvertiert, exakte Ramp erhalten.
        assert closes[0] == 100.0
        assert closes[-1] == 219.0
        assert all(isinstance(c, float) for c in closes)
        # Transparenz-Kennzeichnung NUR bei Erfolg gesetzt.
        assert outcome.source == "twelvedata_fallback"


def test_fetch_twelvedata_kein_api_key_ist_fail_soft(monkeypatch):
    # Fixture räumt TWELVE_DATA_API_KEY bereits weg — hier nochmal explizit,
    # falls die Fixture-Reihenfolge sich je ändert.
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    outcome = pipe.fetch_twelvedata("AAPL")
    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR
    assert "TWELVE_DATA_API_KEY" in outcome.detail
    assert outcome.source == "yfinance"  # Default unverändert


def test_fetch_twelvedata_api_fehlermeldung(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        pipe, "_twelvedata_get",
        lambda params, timeout: _FakeResponse(
            {"code": 400, "message": "unbekanntes Symbol", "status": "error"}
        ),
    )
    outcome = pipe.fetch_twelvedata("XXXNOPE")
    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR
    assert "unbekanntes Symbol" in outcome.detail


def test_fetch_twelvedata_api_fehlermeldung_redigiert_key_falls_enthalten(monkeypatch):
    """Konsistenz-Fix (Guardian-Nit aus #136): dieselbe Redaction-Probe wie
    bei Alpha Vantages 'Error Message'-Zweig, hier für Twelve Datas
    status=='error'-Zweig — die API-Fehlerantwort selbst enthaelt den Key
    normalerweise nicht, aber falls Twelve Data ihn je in 'message'
    spiegelt (z. B. eine ungueltige Anfrage zitiert zurueck), darf er nicht
    durchrutschen."""
    geheim = "sk-super-geheimer-td-key"
    _set_key(monkeypatch, value=geheim)
    monkeypatch.setattr(
        pipe, "_twelvedata_get",
        lambda params, timeout: _FakeResponse(
            {"code": 400, "message": f"ungueltige Anfrage mit apikey={geheim}",
             "status": "error"}
        ),
    )
    outcome = pipe.fetch_twelvedata("XXXNOPE")
    assert outcome.data is None
    assert geheim not in outcome.detail
    assert "***" in outcome.detail


def test_fetch_twelvedata_leere_values(monkeypatch):
    _set_key(monkeypatch)
    monkeypatch.setattr(
        pipe, "_twelvedata_get",
        lambda params, timeout: _FakeResponse({"values": []}),
    )
    outcome = pipe.fetch_twelvedata("AAPL")
    assert outcome.data is None
    assert outcome.reason == pipe.EMPTY_DATA


def test_fetch_twelvedata_netzfehler_ist_fail_soft(monkeypatch):
    _set_key(monkeypatch)

    def _raise(params, timeout):
        raise ConnectionError("kein Netz")

    monkeypatch.setattr(pipe, "_twelvedata_get", _raise)
    outcome = pipe.fetch_twelvedata("AAPL")
    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR
    assert "ConnectionError" in outcome.detail


def test_fetch_twelvedata_netzfehler_redigiert_den_api_key(monkeypatch):
    """Guardian-Nit: eine requests/urllib3-Exception kann die VOLLE Request-
    URL inkl. `apikey=...` in ihrer Message tragen — die darf nicht
    unredigiert im detail (-> Actions-Log) landen."""
    geheim = "sk-super-geheimer-twelvedata-key"
    _set_key(monkeypatch, value=geheim)

    def _raise(params, timeout):
        raise ConnectionError(
            f"Connection refused: https://api.twelvedata.com/time_series"
            f"?symbol=AAPL&apikey={geheim}"
        )

    monkeypatch.setattr(pipe, "_twelvedata_get", _raise)
    outcome = pipe.fetch_twelvedata("AAPL")
    assert outcome.data is None
    assert geheim not in outcome.detail
    assert "***" in outcome.detail


# ---------------------------------------------------------------------------
# _make_yfinance_with_td_fallback — WANN springt der Fallback ein?
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


def _stub_twelvedata_spy(monkeypatch, calls):
    def _fake(ticker):
        calls.append(ticker)
        d, c = pipe.fetch_synthetic(ticker).data
        return pipe.FetchOutcome(data=(d, c), source="twelvedata_fallback")

    monkeypatch.setattr(pipe, "fetch_twelvedata", _fake)


def test_fallback_greift_bei_fehlgeschlagenem_us_ticker(monkeypatch):
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_twelvedata_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_td_fallback()
    outcome = fetcher("AAPL")

    assert calls == ["AAPL"]
    assert outcome.data is not None
    assert outcome.source == "twelvedata_fallback"


def test_regression_erfolgreiches_yfinance_nutzt_KEINEN_fallback(monkeypatch):
    """Kern-Regressionstest des Auftrags: normaler Erfolg bleibt reines
    yfinance — Twelve Data wird dabei nicht einmal ANGEFASST."""
    _set_key(monkeypatch)
    _stub_yfinance_success(monkeypatch)
    calls = []
    _stub_twelvedata_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_td_fallback()
    outcome = fetcher("AAPL")

    assert calls == []  # Twelve Data NIE aufgerufen
    assert outcome.source == "yfinance"


def test_fallback_NICHT_fuer_de_ticker(monkeypatch):
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_twelvedata_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_td_fallback()
    outcome = fetcher("SAP.DE")

    assert calls == []  # Grenzen des Auftrags: DE bleibt außen vor
    assert outcome.data is None
    assert outcome.reason == pipe.EMPTY_DATA
    assert outcome.source == "yfinance"


def test_fallback_ohne_secret_ist_no_op(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_twelvedata_spy(monkeypatch, calls)

    fetcher = pipe._make_yfinance_with_td_fallback()
    outcome = fetcher("AAPL")

    assert calls == []
    assert outcome.data is None


def test_fallback_selbst_fehlgeschlagen_gibt_original_yfinance_grund_zurueck(monkeypatch):
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch, reason=pipe.FETCH_ERROR)
    monkeypatch.setattr(
        pipe, "fetch_twelvedata",
        lambda ticker: pipe.FetchOutcome(reason=pipe.FETCH_ERROR, detail="auch tot"),
    )

    fetcher = pipe._make_yfinance_with_td_fallback()
    outcome = fetcher("AAPL")

    assert outcome.data is None
    assert outcome.reason == pipe.FETCH_ERROR
    assert outcome.detail == "yfinance leer"  # der URSPRÜNGLICHE Grund, nicht überschrieben


# ---------------------------------------------------------------------------
# Rate-Limit: NUR einzelne Ticker, nie das ganze Universum
# ---------------------------------------------------------------------------
def test_fallback_rate_limit_deckelt_calls_pro_lauf(monkeypatch):
    monkeypatch.setattr(config, "TWELVE_DATA_MAX_FALLBACK_CALLS", 2)
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_twelvedata_spy(monkeypatch, calls)

    # EIN Fetcher (eine Closure) über mehrere Ticker desselben Laufs.
    fetcher = pipe._make_yfinance_with_td_fallback()
    outcomes = [fetcher(t) for t in ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL"]]

    assert len(calls) == 2  # gedeckelt, NICHT alle 5
    # Die ersten beiden kamen über den Fallback durch, der Rest bleibt beim
    # (fehlgeschlagenen) yfinance-Ergebnis — kein Absturz, kein Extra-Call.
    assert outcomes[0].source == "twelvedata_fallback"
    assert outcomes[1].source == "twelvedata_fallback"
    assert outcomes[2].data is None
    assert outcomes[3].data is None
    assert outcomes[4].data is None


def test_fallback_zaehler_ist_PRO_FETCHER_nicht_global(monkeypatch):
    """Zwei get_fetcher()-Läufe (z. B. zwei Pipeline-Läufe im selben Prozess,
    etwa Test-Suite) teilen sich KEINEN Zähler — jede Closure startet bei 0."""
    monkeypatch.setattr(config, "TWELVE_DATA_MAX_FALLBACK_CALLS", 1)
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_twelvedata_spy(monkeypatch, calls)

    fetcher_a = pipe._make_yfinance_with_td_fallback()
    fetcher_a("AAPL")
    fetcher_b = pipe._make_yfinance_with_td_fallback()
    fetcher_b("MSFT")

    assert calls == ["AAPL", "MSFT"]  # beide kamen durch — getrennte Klausuren


# ---------------------------------------------------------------------------
# get_fetcher()-Verdrahtung
# ---------------------------------------------------------------------------
def test_get_fetcher_nutzt_den_fallback_wrapper(monkeypatch):
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)
    _set_key(monkeypatch)
    _stub_yfinance_fail(monkeypatch)
    calls = []
    _stub_twelvedata_spy(monkeypatch, calls)

    fetcher = pipe.get_fetcher()
    outcome = fetcher("AAPL")

    assert calls == ["AAPL"]
    assert outcome.source == "twelvedata_fallback"


def test_get_fetcher_offline_bleibt_synthetisch_ohne_fallback(monkeypatch):
    monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
    assert pipe.get_fetcher() is pipe.fetch_synthetic


# ---------------------------------------------------------------------------
# Transparenz im Report: data_source auf dem Kandidaten-Eintrag
# ---------------------------------------------------------------------------
def test_scan_market_markiert_fallback_kandidaten_transparent(monkeypatch):
    _set_key(monkeypatch)
    d_ok, c_ok = pipe.fetch_synthetic("YF").data
    d_fb, c_fb = pipe.fetch_synthetic("FB").data

    def fetcher(ticker):
        if ticker == "YF":
            return pipe.FetchOutcome(data=(list(d_ok), list(c_ok)))
        return pipe.FetchOutcome(
            data=(list(d_fb), list(c_fb)), source="twelvedata_fallback",
        )

    candidates, *_rest = pipe._scan_market(["YF", "FB"], fetcher)
    by_ticker = {c["ticker"]: c for c in candidates}

    assert by_ticker["YF"]["data_source"] == "yfinance"
    assert by_ticker["FB"]["data_source"] == "twelvedata_fallback"
    # Additiv: Score/Ranking-Felder unberührt vorhanden, kein Schema-Bruch.
    assert "score_heuristic" in by_ticker["FB"]
