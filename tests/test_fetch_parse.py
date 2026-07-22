"""Tests für die yfinance-Download-Verarbeitung (parse_download_df).

Lehre aus dem 99/99-Skip-Bug: der Offline-Mock muss die ECHTE yfinance-Form
spiegeln. yfinance >= 0.2.5x liefert MULTIINDEX-Spalten
([('Close','AAPL'), ...]) auch bei Einzel-Tickern — genau das prüft der
MultiIndex-Test hier. Der Flach-Test sichert die Abwärts-/Vorwärtskompatibilität.
"""
import pytest

import config
import elliott_pipeline as pipe

pd = pytest.importorskip("pandas")

N = 120  # >= config.MIN_BARS
CLOSES = [100.0 + i for i in range(N)]  # bekannte Ramp zum Assert


def _rows():
    # [Close, High, Low, Open, Volume] je Zeile
    return [[CLOSES[i], CLOSES[i] + 1, CLOSES[i] - 1, CLOSES[i], 1000 + i] for i in range(N)]


def _index():
    return pd.date_range("2023-01-01", periods=N, freq="D")


def test_parse_multiindex_columns():
    # EXAKT die im Diag-Log beobachtete Form (yfinance 0.2.66, Einzel-Ticker).
    cols = pd.MultiIndex.from_tuples(
        [("Close", "AAPL"), ("High", "AAPL"), ("Low", "AAPL"),
         ("Open", "AAPL"), ("Volume", "AAPL")]
    )
    df = pd.DataFrame(_rows(), index=_index(), columns=cols)
    assert df.columns.nlevels == 2  # sicherstellen, dass wir wirklich MultiIndex testen

    outcome = pipe.parse_download_df(df)

    assert outcome.reason is None, outcome.detail
    assert outcome.data is not None
    dates, closes = outcome.data
    assert len(closes) == N
    assert closes == CLOSES            # korrekte Close-Series extrahiert
    assert dates[0] == "2023-01-01"
    assert dates[-1] == "2023-04-30"


def test_parse_flat_columns():
    # Klassische flache Spalten (ältere yfinance / anderes Format).
    cols = ["Close", "High", "Low", "Open", "Volume"]
    df = pd.DataFrame(_rows(), index=_index(), columns=cols)
    assert df.columns.nlevels == 1

    outcome = pipe.parse_download_df(df)

    assert outcome.reason is None, outcome.detail
    assert outcome.data is not None
    dates, closes = outcome.data
    assert closes == CLOSES


def test_parse_empty_dataframe():
    outcome = pipe.parse_download_df(pd.DataFrame())
    assert outcome.data is None
    assert outcome.reason == pipe.EMPTY_DATA


def test_parse_too_few_bars():
    short = 30  # < MIN_BARS
    idx = pd.date_range("2023-01-01", periods=short, freq="D")
    df = pd.DataFrame(
        [[100.0 + i] for i in range(short)], index=idx, columns=["Close"]
    )
    outcome = pipe.parse_download_df(df)
    assert outcome.data is None
    assert outcome.reason == pipe.EMPTY_DATA
    assert str(config.MIN_BARS) in outcome.detail


def test_parse_multiindex_matches_flat():
    # Beide Welten liefern identische Close-Liste -> der Fix vereinheitlicht.
    mi = pd.DataFrame(
        _rows(), index=_index(),
        columns=pd.MultiIndex.from_tuples(
            [("Close", "X"), ("High", "X"), ("Low", "X"), ("Open", "X"), ("Volume", "X")]
        ),
    )
    flat = pd.DataFrame(_rows(), index=_index(),
                        columns=["Close", "High", "Low", "Open", "Volume"])
    assert pipe.parse_download_df(mi).data == pipe.parse_download_df(flat).data
