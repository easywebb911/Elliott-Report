"""Persönliche Watchlist: volle Analyse eigener Ticker, außer Konkurrenz zum
Top-5-Ranking und — entscheidend — NIE Teil der Forward-Sammlungs-Population.
"""
import json

import config
import elliott_pipeline as pipe
import forward_collection as fc


FIXED_TS = "2024-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# load_watchlist (fail-soft, Formate)
# ---------------------------------------------------------------------------
def test_load_watchlist_failsoft_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config, "WATCHLIST_PATH", "nope.json")
    assert pipe.load_watchlist() == []


def test_load_watchlist_formats(tmp_path, monkeypatch):
    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config, "WATCHLIST_PATH", "wl.json")
    # bloßes Array
    (tmp_path / "wl.json").write_text('["aapl", "SAP.DE", "aapl", " nvda "]', encoding="utf-8")
    assert pipe.load_watchlist() == ["AAPL", "SAP.DE", "NVDA"]  # upper, dedup, strip
    # {"tickers": [...]}
    (tmp_path / "wl.json").write_text('{"tickers": ["msft"]}', encoding="utf-8")
    assert pipe.load_watchlist() == ["MSFT"]
    # kaputt -> leer
    (tmp_path / "wl.json").write_text("{ broken", encoding="utf-8")
    assert pipe.load_watchlist() == []


def test_load_watchlist_caps(tmp_path, monkeypatch):
    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(config, "WATCHLIST_PATH", "wl.json")
    monkeypatch.setattr(config, "WATCHLIST_MAX", 3)
    (tmp_path / "wl.json").write_text(json.dumps([f"T{i}" for i in range(10)]), encoding="utf-8")
    assert len(pipe.load_watchlist()) == 3


# ---------------------------------------------------------------------------
# Watchlist-Einträge: setup / no_setup / error
# ---------------------------------------------------------------------------
def test_watchlist_setup_entry_full():
    e = pipe.build_watchlist_entry("AAPL", pipe.fetch_synthetic, pipe.fetch_synthetic_weekly)
    assert e["wl_status"] == "setup"
    assert e["watchlist"] is True
    assert e["score_heuristic"] is not None
    assert e["target_zone"] and e["invalidation_price"] is not None
    assert e["higher_degree"] is not None  # Wochen-Count mitgeliefert


def test_watchlist_no_setup_entry_shows_state():
    # Flache Kurse -> keine Pivots/kein Setup, aber Karte MIT Kurs + Hinweis.
    dates = [f"d{i}" for i in range(80)]
    closes = [100.0] * 80
    e = pipe._wl_no_setup_entry("FLATX", dates, closes, pipe.NO_VALID_COUNT, "")
    assert e["wl_status"] == "no_setup"
    assert e["close"] == 100.0
    assert e["note"] == "kein regelkonformes Long-Setup"
    assert e["score_heuristic"] is None and e["target_zone"] is None


def test_watchlist_error_entry_failsoft():
    boom = lambda t: pipe.FetchOutcome(reason=pipe.FETCH_ERROR, detail="net down")
    e = pipe.build_watchlist_entry("BADX", boom)
    assert e["wl_status"] == "error"
    assert e["close"] is None
    assert e["note"] == "Daten nicht abrufbar"


def test_build_watchlist_diag_counts():
    wl = pipe.build_watchlist(pipe.fetch_synthetic, pipe.fetch_synthetic_weekly,
                              tickers=["AAPL", "MSFT"])
    assert wl["diag"]["setup"] == 2
    assert len(wl["entries"]) == 2


# ---------------------------------------------------------------------------
# Ranking-Neutralität + Report-Integration
# ---------------------------------------------------------------------------
def _build_with_watchlist(tickers):
    # build_report liest load_watchlist(); wir testen build_watchlist separat und
    # hängen es an, um Ranking-Neutralität isoliert zu prüfen.
    report = pipe.build_report(pipe.fetch_synthetic, FIXED_TS, pipe.fetch_synthetic_weekly)
    return report


def test_watchlist_field_present_and_shaped():
    report = pipe.build_report(pipe.fetch_synthetic, FIXED_TS)
    assert "watchlist" in report
    assert set(report["watchlist"]) == {"entries", "diag"}
    assert set(report["watchlist"]["diag"]) == {"setup", "no_setup", "error"}


def test_watchlist_does_not_change_market_ranking(monkeypatch):
    # BEWEIS Ranking-Neutralität: mit vs. ohne befüllte Watchlist bleibt die
    # Reihenfolge/Score je Markt identisch.
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    a = pipe.build_report(pipe.fetch_synthetic, FIXED_TS, pipe.fetch_synthetic_weekly)
    monkeypatch.setattr(pipe, "load_watchlist", lambda: ["AAPL", "ZZWATCH", "SAP.DE"])
    b = pipe.build_report(pipe.fetch_synthetic, FIXED_TS, pipe.fetch_synthetic_weekly)
    for mk in ("US", "DE"):
        ra = [(c["ticker"], c["score_heuristic"]) for c in a["markets"][mk]["candidates"]]
        rb = [(c["ticker"], c["score_heuristic"]) for c in b["markets"][mk]["candidates"]]
        assert ra == rb
    assert len(b["watchlist"]["entries"]) == 3  # Watchlist trotzdem befüllt


# ---------------------------------------------------------------------------
# POPULATIONS-SCHUTZ: Watchlist-Ticker fließen NIE in die Forward-Sammlung
# ---------------------------------------------------------------------------
def test_watchlist_ticker_never_enters_forward_collection(monkeypatch):
    # ZZWATCH ist NUR in der Watchlist (in keinem Markt-Universum). Die Sammlung
    # liest ausschließlich markets[].candidates -> ZZWATCH darf nie auftauchen.
    monkeypatch.setattr(pipe, "load_watchlist", lambda: ["ZZWATCH"])
    report = pipe.build_report(pipe.fetch_synthetic, FIXED_TS, pipe.fetch_synthetic_weekly)
    wl_tickers = {e["ticker"] for e in report["watchlist"]["entries"]}
    assert "ZZWATCH" in wl_tickers  # ist in der Watchlist

    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    price = {"ZZWATCH": (["d0"], [10.0])}
    fc.update_forward_collection(coll, report, price, {"US": "risk_on", "DE": "risk_on"},
                                 "2024-01-01", FIXED_TS)
    coll_tickers = {r["ticker"] for r in coll["records"]}
    assert "ZZWATCH" not in coll_tickers  # <-- Populations-Schutz belegt
    # Alle gesammelten Ticker stammen aus den Markt-Top-5, nicht aus der Watchlist.
    top5 = set()
    for mk in ("US", "DE"):
        top5 |= {c["ticker"] for c in report["markets"][mk]["candidates"]}
    assert coll_tickers <= top5
