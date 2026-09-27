"""Pipeline-Verdrahtung für Intraday-MFE/MAE (26.09.2026): FetchOutcome.highs/
lows, hilo_sink (Muster wie volume_sink), Durchreichung bis update_forward_
collection(). Die eigentliche Berechnung (mature_record) ist separat in
tests/test_mfe_mae_intraday.py geprüft.

Diagnose bestätigt: High/Low liefen schon durch denselben yfinance/Twelve-
Data/Alpha-Vantage-Download wie Close, wurden aber nur für atr14() genutzt
und danach verworfen (s. tests/test_atr_volatility.py). Dieser PR macht sie
zusätzlich additiv verfügbar — KEIN Extra-Fetch, KEINE neue Quelle.
"""
from __future__ import annotations

import pytest

import elliott_pipeline as pipe
import forward_collection as fc

pd = pytest.importorskip("pandas")


def _mk_df(closes, highs, lows):
    n = len(closes)
    rows = [[closes[i], highs[i], lows[i], closes[i], 1000 + i] for i in range(n)]
    cols = ["Close", "High", "Low", "Open", "Volume"]
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame(rows, index=idx, columns=cols)


CLOSES = [100.0 + i for i in range(80)]
HIGHS = [c + 2.0 for c in CLOSES]
LOWS = [c - 2.0 for c in CLOSES]


def test_parse_download_df_exponiert_highs_lows_aligned():
    df = _mk_df(CLOSES, HIGHS, LOWS)
    out = pipe.parse_download_df(df)
    assert out.data is not None
    assert out.highs == HIGHS
    assert out.lows == LOWS
    assert len(out.highs) == len(out.data[1]) == len(out.lows)


def test_parse_download_df_ohne_high_low_spalte_highs_lows_none():
    df = pd.DataFrame({"Close": CLOSES, "Volume": [1000.0] * len(CLOSES)},
                      index=pd.date_range("2023-01-01", periods=len(CLOSES), freq="D"))
    out = pipe.parse_download_df(df)
    assert out.data is not None
    assert out.highs is None and out.lows is None


def test_scan_market_befuellt_hilo_sink_wie_volume_sink():
    def fetcher(ticker):
        return pipe.parse_download_df(_mk_df(CLOSES, HIGHS, LOWS))

    hilo_sink: dict = {}
    candidates, *_ = pipe._scan_market(["AAA"], fetcher, None, None, None, None,
                                       hilo_sink)
    assert hilo_sink.get("AAA") == (HIGHS, LOWS)


def test_scan_market_ohne_hilo_sink_wirft_nicht():
    # Bestehende Aufrufer (5 oder 6 Positionsargumente, kein hilo_sink) bleiben
    # unveraendert lauffaehig -- reine Rueckwaertskompatibilitaet.
    def fetcher(ticker):
        return pipe.parse_download_df(_mk_df(CLOSES, HIGHS, LOWS))

    candidates, *_ = pipe._scan_market(["AAA"], fetcher, None, None, None, None)
    assert isinstance(candidates, list)


def test_build_report_befuellt_hilo_sink_end_to_end():
    hilo_sink: dict = {}
    price_sink: dict = {}
    pipe.build_report(pipe.fetch_synthetic, "2026-09-26T00:00:00Z",
                      pipe.fetch_synthetic_weekly, None, price_sink, None,
                      hilo_sink)
    # fetch_synthetic liefert bewusst KEIN High/Low (s. test_atr_volatility.py,
    # "Offline-/Demo-Fetcher bekommt KEIN synthetisches High/Low") -- der Sink
    # bleibt also leer, der Lauf darf aber nicht abstuerzen.
    assert hilo_sink == {}
    assert price_sink  # Markt-Kandidaten wurden trotzdem geladen


def test_update_forward_collection_reicht_hilo_data_an_mature_record_durch():
    # End-to-End bis in die Sammlung: eine neue Episode wird angelegt, dann
    # reift sie mit uebergebenem hilo_data -- mfe_high_10d/mae_low_10d muessen
    # in der Sammlung ankommen, nicht nur in mature_record() isoliert.
    entry = {
        "ticker": "AAPL", "close": 100.0, "count_label": "Impuls 1–5 · Long-Setup am Ende W4 (W5 erwartet)",
        "score_heuristic": 70.0,
        "target_zone": {"low": 120.0, "high": 130.0},
        "target_zone_extended": {"low": 140.0, "high": 150.0},
        "invalidation_price": 90.0, "direction": "long",
    }
    report = {"markets": {"US": {"candidates": [entry]}}}
    coll = {"schema_version": fc.SCHEMA_VERSION, "last_run_date": None,
           "updated_utc": None, "records": []}
    dates = ["2026-07-22"]
    closes = [100.0]
    price_data = {"AAPL": (dates, closes)}
    hilo_data = {"AAPL": ([100.0], [100.0])}
    fc.update_forward_collection(coll, report, price_data, {"US": "risk_on"},
                                 "2026-07-22", "2026-07-22T00:00:00Z", hilo_data)
    assert len(coll["records"]) == 1
    rec = coll["records"][0]
    assert rec["mfe_high_10d"] is None    # noch keine Folgetage -> unresolved
    assert rec["mae_low_10d"] is None

    # Zweiter Lauf: Folgetage mit High/Low kommen dazu -> Felder muessen sich
    # ueber update_forward_collection() genauso fuellen wie in mature_record().
    # Leere Kandidaten-Liste -> Schritt 1 (Anlage/Verlaengerung) tut nichts;
    # nur Schritt 2 (Reifung ALLER offenen Records) ist hier relevant.
    report_no_new = {"markets": {"US": {"candidates": []}}}
    dates2 = ["2026-07-22"] + [f"d{i}" for i in range(10)]
    closes2 = [100.0, 102, 105, 108, 112, 116, 121, 123, 124, 125, 125]
    highs2 = [100.0, 104, 108, 112, 118, 130, 124, 126, 127, 128, 127]
    lows2 = [100.0, 99, 101, 104, 108, 112, 118, 120, 121, 95, 122]
    price_data2 = {"AAPL": (dates2, closes2)}
    hilo_data2 = {"AAPL": (highs2, lows2)}
    fc.update_forward_collection(coll, report_no_new, price_data2, {"US": "risk_on"},
                                 "2026-07-23", "2026-07-23T00:00:00Z", hilo_data2)
    rec = coll["records"][0]
    assert rec["mfe_high_10d"] == 30.0
    assert rec["mae_low_10d"] == -5.0
