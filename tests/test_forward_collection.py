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
