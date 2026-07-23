"""Forward-Sammlung: Offline-Simulation über mehrere Mock-Läufe.

Belegt an konstruierten Kursverläufen, dass Records entstehen, reifen und
target_hit/invalidated/ext_hit korrekt gesetzt werden. Prüft außerdem die
Episoden-Mechanik (Dedup bei konsekutiven Top-5-Tagen, neue Episode nach
Verschwinden), Survivorship-Freiheit, Regime und Fail-soft.
"""
import json

import forward_collection as fc


NOW = "2026-07-22T00:00:00Z"


def _entry(ticker, close=100.0, score=70.0, tlow=120.0, thigh=130.0,
           elow=140.0, ehigh=150.0, inval=90.0):
    return {
        "ticker": ticker,
        "close": close,
        "score_heuristic": score,
        "target_zone": {"low": tlow, "high": thigh},
        "target_zone_extended": {"low": elow, "high": ehigh},
        "invalidation_price": inval,
        "direction": "long",
    }


def _report(*entries, market="US"):
    return {"markets": {market: {"candidates": list(entries)}}}


def _series(first_seen, forward_closes, entry_close=100.0):
    """dates/closes so, dass first_seen der Einstiegstag ist und danach
    forward_closes folgen. Index von first_seen zeigt auf entry_close."""
    dates = [first_seen] + [f"d{i}" for i in range(len(forward_closes))]
    closes = [entry_close] + list(forward_closes)
    return dates, closes


# ---------------------------------------------------------------------------
# I/O + Fail-soft
# ---------------------------------------------------------------------------
def test_load_collection_failsoft(tmp_path, monkeypatch):
    # Fehlende Datei -> leere, valide Struktur (kein Absturz).
    monkeypatch.setattr(fc, "REPO_ROOT", tmp_path)
    coll = fc.load_collection()
    assert coll["records"] == [] and coll["schema_version"] == fc.SCHEMA_VERSION
    assert coll["last_run_date"] is None


def test_load_collection_corrupt_failsoft(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / fc.FORWARD_PATH).write_text("{ not json", encoding="utf-8")
    coll = fc.load_collection()
    assert coll["records"] == []  # kaputte Datei -> leere Struktur


def test_write_and_reload_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(fc, "REPO_ROOT", tmp_path)
    coll = {"schema_version": 1, "last_run_date": "2026-07-22",
            "updated_utc": NOW, "records": [{"ticker": "AAPL"}]}
    written = fc.write_collection(coll)
    assert len(written) == 2  # data/ + docs/data/
    for p in written:
        assert p.exists()
    back = fc.load_collection()
    assert back["records"][0]["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# Reifung (mature_record) — konstruierte Kursverläufe
# ---------------------------------------------------------------------------
def test_target_hit_on_rising_path():
    rec = fc._new_record(_entry("AAPL", tlow=120.0, elow=140.0, inval=90.0),
                         "US", "s", "risk_on", "2026-07-22", NOW)
    # steigt sauber bis 125 über 10 Tage, Ziel 120 erreicht, nie Invalidierung.
    dates, closes = _series("s", [102, 105, 108, 112, 116, 121, 123, 124, 125, 125])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["matured"] is True
    assert rec["target_hit"] == 1
    assert rec["invalidated"] == 0
    assert rec["ext_hit"] == 0          # 140 nie erreicht
    assert rec["bars_elapsed"] == 10
    assert rec["max_gain_10d"] == 25.0  # (125-100)/100*100


def test_invalidated_on_falling_path():
    rec = fc._new_record(_entry("AAPL", tlow=120.0, inval=90.0),
                         "US", "s", "risk_on", "2026-07-22", NOW)
    dates, closes = _series("s", [98, 95, 92, 89, 85, 84, 83, 82, 81, 80])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["matured"] is True
    assert rec["invalidated"] == 1
    assert rec["target_hit"] == 0
    assert rec["max_drawdown_10d"] == -20.0  # (80-100)/100*100


def test_ext_hit_before_invalidation():
    rec = fc._new_record(_entry("AAPL", tlow=120.0, elow=140.0, inval=90.0),
                         "US", "s", "risk_on", "2026-07-22", NOW)
    dates, closes = _series("s", [110, 122, 135, 142, 138, 130, 128, 126, 125, 124])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["target_hit"] == 1
    assert rec["ext_hit"] == 1
    assert rec["invalidated"] == 0


def test_invalidation_first_beats_later_target():
    # Invalidierung an Tag 0, Ziel erst später -> invalidated, target_hit=0.
    rec = fc._new_record(_entry("AAPL", tlow=120.0, inval=90.0),
                         "US", "s", "risk_on", "2026-07-22", NOW)
    dates, closes = _series("s", [89, 95, 105, 121, 125, 126, 127, 128, 129, 130])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["invalidated"] == 1
    assert rec["target_hit"] == 0


def test_same_day_tie_resolves_conservatively_as_invalidated():
    # Gleichstand: Ziel UND Invalidierung am selben Tag gerissen (bei Close-only
    # nicht auflösbar). Konservativ -> invalidated=1, target_hit=0 (kein Treffer
    # aufblähen). Praktisch durch classify_setup unerreichbar (Ziel > Invalidierung),
    # hier nur mit degeneriertem Setup erzwungen.
    rec = fc._new_record(_entry("AAPL", tlow=120.0, inval=120.0),  # entartet: gleich
                         "US", "s", "risk_on", "2026-07-22", NOW)
    dates, closes = _series("s", [120, 120, 120, 120, 120, 120, 120, 120, 120, 120])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["invalidated"] == 1
    assert rec["target_hit"] == 0
    assert rec["ext_hit"] == 0


def test_early_resolution_before_full_horizon():
    # Ziel an Tag 1 erreicht -> resolved, obwohl noch nicht 10 Tage reif.
    rec = fc._new_record(_entry("AAPL", tlow=120.0, inval=90.0),
                         "US", "s", "risk_on", "2026-07-22", NOW)
    dates, closes = _series("s", [110, 125])  # nur 2 Folgetage
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["matured"] is False       # < 10 Tage
    assert rec["target_hit"] == 1        # aber schon aufgelöst
    assert rec["bars_elapsed"] == 2


def test_unresolved_stays_null_when_pending():
    # Weder Ziel noch Invalidierung, < 10 Tage -> Kennzahlen bleiben null.
    rec = fc._new_record(_entry("AAPL", tlow=120.0, inval=90.0),
                         "US", "s", "risk_on", "2026-07-22", NOW)
    dates, closes = _series("s", [101, 102, 103])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["matured"] is False
    assert rec["target_hit"] is None
    assert rec["invalidated"] is None
    assert rec["max_gain_10d"] == 3.0    # laufende Kennzahlen trotzdem gefüllt


def test_r_multiple_computation():
    rec = fc._new_record(_entry("AAPL", tlow=120.0, inval=90.0),
                         "US", "s", "risk_on", "2026-07-22", NOW)
    # Risiko = 100-90 = 10; max = 130 -> r = (130-100)/10 = 3.0
    dates, closes = _series("s", [110, 120, 130, 128, 125, 124, 123, 122, 121, 120])
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["r_multiple"] == 3.0


def test_mature_missing_first_seen_is_noop():
    rec = fc._new_record(_entry("AAPL"), "US", "not-in-data",
                         "risk_on", "2026-07-22", NOW)
    before = dict(rec)
    fc.mature_record(rec, ["a", "b"], [10.0, 11.0], NOW)
    assert rec["target_hit"] == before["target_hit"]  # unverändert (null)
    assert rec["matured"] is False


# ---------------------------------------------------------------------------
# Episoden-Mechanik über mehrere Läufe
# ---------------------------------------------------------------------------
def test_consecutive_top5_days_one_episode():
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    regimes = {"US": "risk_on"}
    price = {"AAPL": _series("day1", [101, 102])}

    # Lauf 1
    fc.update_forward_collection(coll, _report(_entry("AAPL")), price, regimes,
                                 "2026-07-01", NOW)
    assert len(coll["records"]) == 1
    ep1 = coll["records"][0]["episode_id"]

    # Lauf 2 — AAPL wieder Top-5, direkt am Folgetag (prev_run_date == last_seen)
    fc.update_forward_collection(coll, _report(_entry("AAPL")), price, regimes,
                                 "2026-07-02", NOW)
    assert len(coll["records"]) == 1  # KEIN Doppel-Record
    assert coll["records"][0]["episode_id"] == ep1
    assert coll["records"][0]["last_seen_top5_date"] == "2026-07-02"


def test_reappearance_after_gap_new_episode():
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    regimes = {"US": "risk_on"}
    price = {"AAPL": _series("day1", [101, 102])}

    # Lauf 1: AAPL Top-5
    fc.update_forward_collection(coll, _report(_entry("AAPL")), price, regimes,
                                 "2026-07-01", NOW)
    # Lauf 2: AAPL NICHT Top-5 (report leer) -> Record bleibt offen, reift
    fc.update_forward_collection(coll, _report(), price, regimes,
                                 "2026-07-02", NOW)
    assert len(coll["records"]) == 1
    # Lauf 3: AAPL taucht WIEDER auf -> neue Episode (last_seen != prev_run_date)
    fc.update_forward_collection(coll, _report(_entry("AAPL")), price, regimes,
                                 "2026-07-03", NOW)
    assert len(coll["records"]) == 2  # neue Episode angelegt


def test_open_record_matures_after_falling_out_of_top5():
    # Survivorship: Ticker fällt aus Top-5, Record reift trotzdem bis matured.
    # first_seen wird beim Anlegen = letzter Kurs-Tag gesetzt; Reifung entsteht,
    # wenn die Kurs-Historie über spätere Läufe wächst.
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    regimes = {"US": "risk_on"}

    # Lauf 1: Historie endet am Einstiegstag "T0" -> noch keine Folgetage.
    price1 = {"AAPL": (["a", "b", "T0"], [98.0, 99.0, 100.0])}
    fc.update_forward_collection(coll, _report(_entry("AAPL", tlow=200.0, inval=50.0)),
                                 price1, regimes, "2026-07-01", NOW)
    assert coll["records"][0]["first_seen_date"] == "T0"
    assert coll["records"][0]["matured"] is False

    # Lauf 2: Ticker NICHT mehr Top-5, aber Historie wuchs um 11 Folgetage.
    fwd = [102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122]
    price2 = {"AAPL": (["a", "b", "T0"] + [f"d{i}" for i in range(len(fwd))],
                       [98.0, 99.0, 100.0] + [float(x) for x in fwd])}
    fc.update_forward_collection(coll, _report(), price2, regimes, "2026-07-02", NOW)
    assert coll["records"][0]["matured"] is True  # reift trotz Top-5-Abgang
    assert coll["records"][0]["bars_elapsed"] == 10


def test_counts_helper():
    coll = {"records": [{"matured": True}, {"matured": False}, {"matured": True}]}
    assert fc.counts(coll) == (3, 2)


# ---------------------------------------------------------------------------
# Regime
# ---------------------------------------------------------------------------
def test_compute_regime_risk_on_off_unknown():
    assert fc.compute_regime([1.0] * 199) == "unknown"       # zu wenig Daten
    closes = [10.0] * 200 + [20.0]                            # letzter > SMA200
    assert fc.compute_regime(closes) == "risk_on"
    closes = [20.0] * 200 + [5.0]                             # letzter < SMA200
    assert fc.compute_regime(closes) == "risk_off"


def test_market_regimes_offline_deterministic():
    r = fc.market_regimes(offline=True)
    assert r == {"US": "risk_on", "DE": "risk_on"}


# ---------------------------------------------------------------------------
# report.json-Neutralität: die Sammlung berührt den Report nie
# ---------------------------------------------------------------------------
def test_collection_does_not_mutate_report():
    report = _report(_entry("AAPL"), _entry("MSFT"))
    snapshot = json.dumps(report, sort_keys=True)
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    price = {"AAPL": _series("d", [101]), "MSFT": _series("d", [101])}
    fc.update_forward_collection(coll, report, price, {"US": "risk_on"},
                                 "2026-07-01", NOW)
    assert json.dumps(report, sort_keys=True) == snapshot  # Report unverändert


# ---------------------------------------------------------------------------
# Backtesting-Felder: eingefrorene Pivots (point-in-time) + price_path
# ---------------------------------------------------------------------------
def _entry_with_pivots(ticker, **kw):
    e = _entry(ticker, **kw)
    e["count_label"] = "Impuls 1–5 · Long-Setup am Ende W2 (W3 erwartet)"
    e["chart_points"] = [
        {"index": 0, "date": "2026-06-01", "price": 100.0, "kind": "L"},
        {"index": 1, "date": "2026-06-10", "price": 130.0, "kind": "H"},
        {"index": 2, "date": "2026-06-20", "price": 112.0, "kind": "L"},
    ]
    e["count_wave_labels"] = [{"index": 0, "wave": 0}, {"index": 1, "wave": 1},
                              {"index": 2, "wave": 2}]
    return e


def test_new_record_freezes_pivots_and_label():
    rec = fc._new_record(_entry_with_pivots("AAPL"), "US", "2026-06-20",
                         "risk_on", "2026-06-20", NOW)
    assert rec["count_label"].startswith("Impuls")
    assert [p["price"] for p in rec["chart_points"]] == [100.0, 130.0, 112.0]
    assert rec["count_wave_labels"] == [{"index": 0, "wave": 0},
                                        {"index": 1, "wave": 1},
                                        {"index": 2, "wave": 2}]
    assert rec["price_path"] == []  # noch nicht gereift


def test_frozen_pivots_are_point_in_time_across_runs():
    # Belegt Point-in-time: die eingefrorene Zählung ändert sich bei späteren
    # Läufen NICHT, selbst wenn der Kandidat am Folgetag eine andere Struktur hat.
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    regimes = {"US": "risk_on"}
    price = {"AAPL": _series("day1", [113, 114])}

    # Lauf 1: Episode mit Original-Pivots anlegen.
    fc.update_forward_collection(coll, _report(_entry_with_pivots("AAPL")),
                                 price, regimes, "2026-07-01", NOW)
    frozen = json.dumps(coll["records"][0]["chart_points"], sort_keys=True)

    # Lauf 2: derselbe Ticker weiter Top-5, aber mit KOMPLETT anderer Struktur.
    changed = _entry_with_pivots("AAPL")
    changed["chart_points"] = [{"index": 0, "date": "x", "price": 999.0, "kind": "H"}]
    changed["count_wave_labels"] = [{"index": 0, "wave": 0}]
    fc.update_forward_collection(coll, _report(changed), price, regimes,
                                 "2026-07-02", NOW)

    assert len(coll["records"]) == 1  # gleiche Episode
    assert json.dumps(coll["records"][0]["chart_points"], sort_keys=True) == frozen


def test_price_path_fills_on_maturation():
    rec = fc._new_record(_entry_with_pivots("AAPL", inval=108.0), "US", "T0",
                         "risk_on", "2026-07-01", NOW)
    dates = ["a", "T0", "n1", "n2", "n3"]
    closes = [110.0, 112.0, 114.0, 118.0, 125.0]
    fc.mature_record(rec, dates, closes, NOW)
    assert rec["price_path"] == [
        {"date": "n1", "close": 114.0},
        {"date": "n2", "close": 118.0},
        {"date": "n3", "close": 125.0},
    ]
    assert rec["bars_elapsed"] == 3


def test_price_path_capped_at_horizon():
    rec = fc._new_record(_entry_with_pivots("AAPL"), "US", "T0",
                         "risk_on", "2026-07-01", NOW)
    fwd = list(range(200, 200 + 15))  # 15 Folgetage > HORIZON
    dates, closes = _series("T0", fwd, entry_close=112.0)
    fc.mature_record(rec, dates, closes, NOW)
    assert len(rec["price_path"]) == fc.HORIZON_DAYS  # max 10


def test_old_record_without_pivots_does_not_crash():
    # Alt-Record (vor dem Feature) ohne chart_points/count_wave_labels/price_path:
    # Reifung darf nicht crashen; die Felder werden fail-soft nachgezogen.
    old = {
        "ticker": "OLD", "first_seen_date": "T0", "entry_close": 100.0,
        "invalidation_price": 90.0, "target_zone": {"low": 120.0, "high": 130.0},
        "target_zone_extended": {"low": 140.0, "high": 150.0}, "matured": False,
        "target_hit": None, "ext_hit": None, "invalidated": None,
    }
    dates, closes = _series("T0", [102, 105, 108])
    fc.mature_record(old, dates, closes, NOW)  # kein KeyError / Crash
    assert old["price_path"] == [{"date": "d0", "close": 102.0},
                                 {"date": "d1", "close": 105.0},
                                 {"date": "d2", "close": 108.0}]


def test_purge_removes_backtesting_fields(tmp_path):
    # Revert-Weg räumt die neuen Felder mit weg (sie liegen in derselben Datei).
    import importlib
    purge = importlib.import_module("purge_forward_collection")
    (tmp_path / "data").mkdir()
    (tmp_path / "docs" / "data").mkdir(parents=True)
    payload = {"records": [{"ticker": "AAPL", "chart_points": [{"price": 1}],
                            "price_path": [{"close": 2}]}]}
    for rel in ("data/forward_collection.json", "docs/data/forward_collection.json"):
        (tmp_path / rel).write_text(json.dumps(payload), encoding="utf-8")
    rc = purge.main(["--path", str(tmp_path), "--reset", "--live"])
    assert rc == 0
    back = json.loads((tmp_path / "data/forward_collection.json").read_text())
    assert back["records"] == []  # inkl. chart_points/price_path entfernt


# ---------------------------------------------------------------------------
# N×-Zähler (appearance_count) — Episoden, nicht Tage; inkl. der aktuellen
# ---------------------------------------------------------------------------
def _ep(ticker, first_seen, matured=False, last_seen="2026-07-25"):
    return {"ticker": ticker, "episode_id": f"{ticker}@{first_seen}",
            "first_seen_date": first_seen, "matured": matured,
            "last_seen_top5_date": last_seen}


def test_appearance_count_counts_episodes_incl_current():
    coll = {"last_run_date": "2026-07-25", "records": [
        _ep("AAPL", "2026-07-22", matured=True, last_seen="2026-07-23"),
        _ep("AAPL", "2026-07-24", matured=True, last_seen="2026-07-24"),
        _ep("MSFT", "2026-07-25", matured=False, last_seen="2026-07-25"),
        _ep("NVDA", "2026-07-20", matured=True, last_seen="2026-07-21"),
    ]}
    # 2 abgeschlossene Episoden + aktuelle (neu) = 3
    assert fc.appearance_count(coll, "AAPL") == 3
    # 1 offene Episode, die HEUTE fortgesetzt wird -> nicht doppelt zählen = 1
    assert fc.appearance_count(coll, "MSFT") == 1
    # 1 abgeschlossene + aktuelle (neu) = 2
    assert fc.appearance_count(coll, "NVDA") == 2
    # nie gesehen -> aktuelle ist die 1.
    assert fc.appearance_count(coll, "TSLA") == 1
    assert fc.appearance_count({"records": []}, "X") == 1


def test_appearance_count_reappearance_is_new_episode():
    # Wiederauftauchen nach Verschwinden (last_seen != prev_run_date) zählt neu.
    coll = {"last_run_date": "2026-07-25", "records": [
        _ep("AAPL", "2026-07-20", matured=True, last_seen="2026-07-22"),  # weg seit 22.
    ]}
    assert fc.appearance_count(coll, "AAPL") == 2  # alte + neue Episode


def test_annotate_only_market_candidates_not_watchlist():
    coll = {"last_run_date": "2026-07-25", "records": [
        _ep("AAPL", "2026-07-22", matured=True, last_seen="2026-07-23"),
    ]}
    report = {
        "markets": {"US": {"candidates": [{"ticker": "AAPL"}, {"ticker": "NVDA"}]}},
        "watchlist": {"entries": [{"ticker": "AAPL"}, {"ticker": "WLONLY"}]},
    }
    fc.annotate_appearance_counts(coll, report)
    assert report["markets"]["US"]["candidates"][0]["appearance_count"] == 2  # AAPL
    assert report["markets"]["US"]["candidates"][1]["appearance_count"] == 1  # NVDA
    # Watchlist bekommt KEINEN Zähler (nicht Teil der Population).
    for e in report["watchlist"]["entries"]:
        assert "appearance_count" not in e


def test_annotate_is_ranking_neutral():
    # Nur additiv: Ticker/Score-Reihenfolge bleibt, nur ein Feld kommt dazu.
    coll = {"last_run_date": None, "records": []}
    cands = [{"ticker": "AAPL", "score_heuristic": 80.0},
             {"ticker": "MSFT", "score_heuristic": 70.0}]
    report = {"markets": {"US": {"candidates": cands}}}
    before = [(c["ticker"], c["score_heuristic"]) for c in cands]
    fc.annotate_appearance_counts(coll, report)
    after = [(c["ticker"], c["score_heuristic"]) for c in report["markets"]["US"]["candidates"]]
    assert before == after
    assert all("appearance_count" in c for c in report["markets"]["US"]["candidates"])


# ---------------------------------------------------------------------------
# Score-Alert-Flanke (>Schwelle) — an die vorhandene Episoden-Logik gekoppelt.
# Jede Flanke über echte update_forward_collection-Läufe durchgespielt (KEIN
# Parallel-State), plus Bündelung, Stumm-Beweis und report.json-Neutralität.
# ---------------------------------------------------------------------------
THRESH = 90


def _run(coll, report, run_date, price=None):
    """Ein echter Sammel-Lauf + Flanke danach — wie im Pipeline-main().
    Gibt die gefeuerten Edges zurück."""
    price = price or {t: _series("d", [101, 102])
                      for m in report["markets"].values()
                      for t in [c["ticker"] for c in m["candidates"]]}
    fc.update_forward_collection(coll, report, price, {"US": "risk_on", "DE": "risk_on"},
                                 run_date, NOW)
    return fc.score_alert_edges(coll, report, THRESH, run_date)


def _fresh_coll():
    return {"schema_version": 1, "last_run_date": None, "updated_utc": None,
            "records": []}


def test_score_alert_fires_when_newly_over_threshold():
    coll = _fresh_coll()
    edges = _run(coll, _report(_entry("AAPL", score=93.0)), "2026-07-01")
    assert [e["ticker"] for e in edges] == ["AAPL"]
    assert edges[0]["score"] == 93.0 and edges[0]["market"] == "US"
    # Flanke am Record vermerkt (an der Episode, nicht als Parallel-State).
    assert coll["records"][0]["score_alert_fired"] == "2026-07-01"


def test_score_alert_silent_at_or_below_threshold():
    coll = _fresh_coll()
    # exakt 90 ist NICHT > 90 (strikt) und 85 klar darunter -> beide stumm.
    assert _run(coll, _report(_entry("AAPL", score=90.0)), "2026-07-01") == []
    assert _run(_fresh_coll(), _report(_entry("MSFT", score=85.0)), "2026-07-01") == []


def test_score_alert_silent_when_staying_over_threshold():
    coll = _fresh_coll()
    price = {"AAPL": _series("d", [101, 102])}
    assert _run(coll, _report(_entry("AAPL", score=93.0)), "2026-07-01", price)  # feuert
    # Folgetag, gleiche Episode, weiter >90 -> STUMM (Zustand, keine neue Flanke).
    edges2 = _run(coll, _report(_entry("AAPL", score=94.0)), "2026-07-02", price)
    assert edges2 == []
    assert len(coll["records"]) == 1  # dieselbe Episode
    assert coll["records"][0]["score_alert_fired"] == "2026-07-01"  # Erst-Flanke bleibt


def test_score_alert_silent_on_dip_and_recross_same_episode():
    coll = _fresh_coll()
    price = {"AAPL": _series("d", [101, 102, 103])}
    assert _run(coll, _report(_entry("AAPL", score=93.0)), "2026-07-01", price)  # feuert
    assert _run(coll, _report(_entry("AAPL", score=85.0)), "2026-07-02", price) == []  # unter
    # Wieder >90 in DERSELBEN Episode -> weiterhin stumm (nur 1x je Episode).
    assert _run(coll, _report(_entry("AAPL", score=95.0)), "2026-07-03", price) == []
    assert len(coll["records"]) == 1


def test_score_alert_fires_again_in_new_episode():
    coll = _fresh_coll()
    price = {"AAPL": _series("d", [101, 102])}
    assert _run(coll, _report(_entry("AAPL", score=93.0)), "2026-07-01", price)  # Episode 1
    # Ticker fällt aus Top-5 (leerer Report) -> Lücke.
    assert _run(coll, _report(), "2026-07-02", price) == []
    # Kommt >90 zurück -> NEUE Episode -> darf erneut feuern.
    edges = _run(coll, _report(_entry("AAPL", score=91.0)), "2026-07-03", price)
    assert [e["ticker"] for e in edges] == ["AAPL"]
    assert len(coll["records"]) == 2  # zwei Episoden
    assert coll["records"][1]["score_alert_fired"] == "2026-07-03"


def test_score_alert_bundles_multiple_tickers_one_batch():
    coll = _fresh_coll()
    report = {"markets": {
        "US": {"candidates": [_entry("XYZ", score=93.0), _entry("ABC", score=91.0)]},
        "DE": {"candidates": [_entry("SAP.DE", score=92.0)]},
    }}
    edges = _run(coll, report, "2026-07-01")
    # Ein Batch (eine Liste) für alle neu-überschrittenen Ticker beider Märkte.
    assert {e["ticker"] for e in edges} == {"XYZ", "ABC", "SAP.DE"}
    assert {e["market"] for e in edges} == {"US", "DE"}


def test_score_alert_silent_run_produces_no_edges():
    # Stumm-Beweis: ein Lauf ohne >90-Flanke feuert NULL.
    coll = _fresh_coll()
    report = {"markets": {"US": {"candidates": [
        _entry("A", score=89.84), _entry("B", score=80.0)]}}}  # Höchststand-nah, aber <90
    assert _run(coll, report, "2026-07-01") == []


def test_score_alert_excludes_watchlist():
    coll = _fresh_coll()
    report = {
        "markets": {"US": {"candidates": [_entry("AAPL", score=93.0)]}},
        "watchlist": {"entries": [{"ticker": "WLHOT", "score_heuristic": 99.0}]},
    }
    edges = _run(coll, report, "2026-07-01")
    # Watchlist (eigene Auswahl) löst NIE aus, auch bei 99.
    assert [e["ticker"] for e in edges] == ["AAPL"]


def test_score_alert_is_idempotent_within_run():
    # Zweiter Aufruf im selben Lauf feuert nicht erneut (Flag schon gesetzt).
    coll = _fresh_coll()
    report = _report(_entry("AAPL", score=93.0))
    fc.update_forward_collection(coll, report, {"AAPL": _series("d", [101])},
                                 {"US": "risk_on"}, "2026-07-01", NOW)
    assert len(fc.score_alert_edges(coll, report, THRESH, "2026-07-01")) == 1
    assert fc.score_alert_edges(coll, report, THRESH, "2026-07-01") == []


def test_score_alert_does_not_mutate_report_scores():
    coll = _fresh_coll()
    report = _report(_entry("AAPL", score=93.0), _entry("MSFT", score=70.0))
    fc.update_forward_collection(coll, report, {"AAPL": _series("d", [101]),
                                                "MSFT": _series("d", [101])},
                                 {"US": "risk_on"}, "2026-07-01", NOW)
    snap = json.dumps(report, sort_keys=True)
    fc.score_alert_edges(coll, report, THRESH, "2026-07-01")
    assert json.dumps(report, sort_keys=True) == snap  # Report unangetastet
