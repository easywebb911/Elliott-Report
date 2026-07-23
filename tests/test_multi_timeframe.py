"""Multi-Timeframe-Analyse (PR B): Tag/Woche/Monat für WATCHLIST-Titel.

Belegt: Monats-Fetcher-Form (MultiIndex-Lesson), begründete Mindest-Kerzen-
Schwelle, die drei Zählungen je Watchlist-Eintrag (inkl. null-Ehrlichkeit),
das EINMALIGE Holen des Wochen-Counts (higher_degree == timeframes.week), die
Fetch-Bilanz (+2 je Titel, Tag ohne Extra-Fetch), Determinismus — und die
Unberührtheit von Markt-Pipeline / Score / Ranking / Forward-Sammlung.
"""
import json

import pytest

import config
import elliott_pipeline as pipe
import forward_collection as fc

FIXED_TS = "2024-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Hilfs-Fetcher
# ---------------------------------------------------------------------------
def _flat_fetcher(_ticker):
    # Genug Kerzen (>= MIN_BARS), aber flach -> keine Pivots -> kein Long-Count.
    n = config.MIN_BARS + 5
    dates = [f"2020-01-{i:02d}" for i in range(1, 3)] + [f"d{i}" for i in range(n - 2)]
    return pipe.FetchOutcome(data=(dates[:n], [100.0] * n))


def _boom_fetcher(_ticker):
    raise RuntimeError("kein Netz")


def _err_fetcher(_ticker):
    # Wie fetch_yfinance im Fehlerfall: RETURNIERT einen Fehler (wirft nicht).
    return pipe.FetchOutcome(reason=pipe.FETCH_ERROR, detail="kein Netz")


def _counting(fetcher):
    calls = {"n": 0}

    def wrapped(ticker):
        calls["n"] += 1
        return fetcher(ticker)

    return wrapped, calls


# ---------------------------------------------------------------------------
# 1) Monats-Fetcher-Form (MultiIndex-Lesson) + Mindest-Kerzen-Schwelle
# ---------------------------------------------------------------------------
pd = pytest.importorskip("pandas")


def _monthly_df(n):
    """Spiegelt die ECHTE yfinance-Monatsform: gleicher MultiIndex je Ticker,
    nur MONATLICHER DatetimeIndex (freq 'MS')."""
    closes = [50.0 + i for i in range(n)]
    rows = [[c, c + 1, c - 1, c, 1000] for c in closes]
    idx = pd.date_range("2010-01-01", periods=n, freq="MS")
    cols = pd.MultiIndex.from_tuples(
        [("Close", "AAPL"), ("High", "AAPL"), ("Low", "AAPL"),
         ("Open", "AAPL"), ("Volume", "AAPL")])
    return pd.DataFrame(rows, index=idx, columns=cols), closes


def test_monthly_multiindex_form_parsed():
    df, closes = _monthly_df(config.MIN_BARS_MONTHLY)
    assert df.columns.nlevels == 2  # wirklich MultiIndex
    out = pipe.parse_download_df(df, config.MIN_BARS_MONTHLY)
    assert out.reason is None, out.detail
    dates, got = out.data
    assert got == closes
    assert dates[0] == "2010-01-01"  # Monats-Kadenz (erster Monatsanfang)


def test_min_bars_monthly_threshold():
    # 59 Monatskerzen (< 5 Jahre) -> KEIN Monats-Count (fail-soft leer).
    df, _ = _monthly_df(config.MIN_BARS_MONTHLY - 1)
    out = pipe.parse_download_df(df, config.MIN_BARS_MONTHLY)
    assert out.reason == pipe.EMPTY_DATA and out.data is None
    # Genau 60 -> reicht.
    df2, _ = _monthly_df(config.MIN_BARS_MONTHLY)
    assert pipe.parse_download_df(df2, config.MIN_BARS_MONTHLY).data is not None
    # Tages-/Wochen-Schwelle bleibt unverändert (Default = MIN_BARS).
    assert config.MIN_BARS_MONTHLY == 60 and config.MIN_BARS == 60


def test_daily_weekly_threshold_unchanged_by_default():
    # parse_download_df ohne min_bars nutzt weiterhin config.MIN_BARS.
    df, _ = _monthly_df(config.MIN_BARS - 1)  # 59 < 60
    assert pipe.parse_download_df(df).reason == pipe.EMPTY_DATA


# ---------------------------------------------------------------------------
# 2) Die drei Zählungen (pure Helfer)
# ---------------------------------------------------------------------------
def test_count_from_series_on_clean_impulse():
    out = pipe.fetch_synthetic_weekly("AAPL")
    dates, closes = out.data
    c = pipe._count_from_series(dates, closes)
    assert c is not None
    assert set(c) == {"count_label", "invalidation_price", "target_zone",
                      "target_zone_extended"}
    assert "Long-Setup" in c["count_label"]


def test_count_from_series_none_on_flat():
    assert pipe._count_from_series(["a", "b"], [100.0, 100.0]) is None


def test_count_from_fetch_failsoft():
    assert pipe._count_from_fetch("X", None) is None          # kein Fetcher
    assert pipe._count_from_fetch("X", _boom_fetcher) is None  # Exception -> None
    assert pipe._count_from_fetch("X", lambda t: pipe.FetchOutcome(
        reason=pipe.EMPTY_DATA)) is None                       # keine Daten


# ---------------------------------------------------------------------------
# 3) timeframes je Watchlist-Eintrag
# ---------------------------------------------------------------------------
def test_timeframes_on_setup_entry_all_three():
    e = pipe.build_watchlist_entry(
        "AAPL", pipe.fetch_synthetic, pipe.fetch_synthetic_weekly,
        pipe.fetch_synthetic_monthly)
    assert e["wl_status"] == "setup"
    tf = e["timeframes"]
    assert set(tf) == {"day", "week", "month"}
    for lvl in ("day", "week", "month"):
        assert tf[lvl] is not None, lvl
        assert set(tf[lvl]) == {"count_label", "invalidation_price",
                                "target_zone", "target_zone_extended"}
    # Wochen-Count EINMAL geholt -> higher_degree ist identisch (kein Doppel-Fetch).
    assert e["higher_degree"] == tf["week"]


def test_timeframes_month_null_without_monthly_fetcher():
    e = pipe.build_watchlist_entry(
        "AAPL", pipe.fetch_synthetic, pipe.fetch_synthetic_weekly)  # kein Monats-F.
    assert e["timeframes"]["month"] is None
    assert e["timeframes"]["day"] is not None
    assert e["timeframes"]["week"] is not None


def test_timeframes_on_no_setup_entry():
    e = pipe.build_watchlist_entry(
        "FLAT", _flat_fetcher, pipe.fetch_synthetic_weekly,
        pipe.fetch_synthetic_monthly)
    assert e["wl_status"] == "no_setup"
    # Tag ohne saubere Struktur -> null (ehrlich); Woche/Monat aus eigenen Reihen.
    assert e["timeframes"]["day"] is None
    assert e["timeframes"]["week"] is not None
    assert e["timeframes"]["month"] is not None


def test_error_entry_timeframes_all_null_and_no_extra_fetch():
    wkly, wcalls = _counting(pipe.fetch_synthetic_weekly)
    mrly, mcalls = _counting(pipe.fetch_synthetic_monthly)
    e = pipe.build_watchlist_entry("BADX", _err_fetcher, wkly, mrly)
    assert e["wl_status"] == "error"
    assert e["timeframes"] == {"day": None, "week": None, "month": None}
    # Der Tagesabruf scheiterte -> KEINE weiteren Fehl-Fetches (Woche/Monat).
    assert wcalls["n"] == 0 and mcalls["n"] == 0


def test_fetch_budget_two_extra_per_ticker():
    # Tag nutzt die geladene Tagesreihe (0 Extra-Fetches); Woche + Monat = +2.
    wkly, wcalls = _counting(pipe.fetch_synthetic_weekly)
    mrly, mcalls = _counting(pipe.fetch_synthetic_monthly)
    pipe.build_watchlist_entry("AAPL", pipe.fetch_synthetic, wkly, mrly)
    assert wcalls["n"] == 1 and mcalls["n"] == 1  # genau +2 je Titel


# ---------------------------------------------------------------------------
# 4) Unberührtheit: Markt-Pipeline / Score / Ranking / Forward-Sammlung
# ---------------------------------------------------------------------------
def _report(monthly=None):
    return pipe.build_report(pipe.fetch_synthetic, FIXED_TS,
                             pipe.fetch_synthetic_weekly, monthly)


def test_market_candidates_have_no_timeframes():
    r = _report(pipe.fetch_synthetic_monthly)
    for mk in r["markets"].values():
        for c in mk["candidates"]:
            assert "timeframes" not in c  # Monatsgrad NUR Watchlist
            assert "higher_degree" in c   # Wochengrad unverändert vorhanden


def test_markets_identical_with_and_without_monthly_fetcher():
    # Der Monats-Fetcher darf die Märkte (Score/Ranking) NICHT verändern.
    a = _report(None)
    b = _report(pipe.fetch_synthetic_monthly)
    assert json.dumps(a["markets"], sort_keys=True) == json.dumps(b["markets"], sort_keys=True)


def test_forward_collection_never_sees_watchlist_timeframes():
    # Die Sammlung liest ausschließlich markets[].candidates -> nie die Watchlist.
    r = _report(pipe.fetch_synthetic_monthly)
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    fc.update_forward_collection(coll, r, {}, {"US": "risk_on", "DE": "risk_on"},
                                 "2024-01-01", FIXED_TS)
    for rec in coll["records"]:
        assert "timeframes" not in rec
    # Und die Watchlist-Population bleibt außerhalb: kein Watchlist-Ticker im Record
    # (bei leerer echter Watchlist ohnehin 0 — hier strukturell geprüft).


def test_higher_degree_none_without_weekly_stays():
    e = pipe.build_watchlist_entry("AAPL", pipe.fetch_synthetic)  # kein Wochen-F.
    assert e["higher_degree"] is None
    assert e["timeframes"]["week"] is None


# ---------------------------------------------------------------------------
# 5) Determinismus + Monatsgrad zeigt die GROSSEN (mehrjährigen) Züge
# ---------------------------------------------------------------------------
def test_build_report_deterministic_with_monthly():
    a = _report(pipe.fetch_synthetic_monthly)
    b = _report(pipe.fetch_synthetic_monthly)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_monthly_pivots_span_years():
    # Selbstprüfung: die Monats-Reihe erstreckt sich über Jahre (mehrjährige
    # Wellen), nicht über Wochen.
    dates, closes = pipe.fetch_synthetic_monthly("AAPL").data
    y0 = int(dates[0][:4])
    y1 = int(dates[-1][:4])
    assert y1 - y0 >= 2, f"Monatsreihe nur {y0}..{y1}"
    assert pipe._count_from_series(dates, closes) is not None  # zeigt einen Count
