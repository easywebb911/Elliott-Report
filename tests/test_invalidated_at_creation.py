"""Filter `invalidated_at_creation` (Easy-Entscheidung 17.10.2026, PR 2 von 4,
Diagnose-Folgeauftrag).

Ein Setup, dessen Lauf-Schlusskurs bereits bei Anlage auf/unter der eigenen
invalidation_price liegt (close <= invalidation_price), war nie handelbar —
"1R" ist für ein solches Setup nie definiert (identischer Operator wie im
additiven Marker `invertiertes_risiko_bei_anlage`, PR #185). Es fliegt VOR dem
Ranking aus den Markt-Top-5 (Rang 6+ rückt nach). Die Watchlist zeigt es
weiter (exclude_invalidated_at_creation=False).
"""
import math

import elliott_pipeline as pipe
import config
import forward_collection as fc

W = config.ZIGZAG_WINDOW


def _impulse(last_close):
    """Sauberer W2-Long (P0=100, P1=120 -> W1=20, P2=110); invalidation_price
    (W2-Setup) = P0 = 100. Der Schwanz steigt ERST auf 145 (bestätigt P2 exakt
    wie in ``test_target_exceeded._impulse``), dann ein kurzes, UNBESTÄTIGTES
    Nachstück (< ZIGZAG_WINDOW Bars, bildet also keinen eigenen Pivot) bis
    ``last_close`` — so lässt sich ``close`` frei unter P0 setzen, ohne P2s
    Bestätigung zu gefährden (das Nachstück liegt außerhalb von P2s
    Bestätigungsfenster)."""
    seg = [(108.0, 100.0, W + 2), (100.0, 120.0, W + 4),
           (120.0, 110.0, W + 3), (110.0, 145.0, W + 2),
           (145.0, last_close, W - 1)]
    closes = []
    for s, e, n in seg:
        rng = range(n + 1) if not closes else range(1, n + 1)
        for k in rng:
            closes.append(s + (e - s) * (k / n))
    return [f"d{i}" for i in range(len(closes))], closes


INVALIDATION_PRICE = 100.0   # P0 für _impulse (end_of_w2)


# ---------------------------------------------------------------------------
# 1) Konstruierte Fälle (Markt-Pipeline, exclude_invalidated_at_creation=True)
# ---------------------------------------------------------------------------
def test_close_over_invalidation_stays():
    d, c = _impulse(105.0)                        # > 100 -> handelbar
    entry, reason, _ = pipe.build_candidate("T", d, c)
    assert entry is not None and reason is None
    assert entry["close"] > entry["invalidation_price"]


def test_close_on_invalidation_is_excluded():
    d, c = _impulse(100.0)                        # == invalidation -> raus (<= inklusiv)
    entry, reason, detail = pipe.build_candidate("T", d, c)
    assert entry is None and reason == pipe.INVALIDATED_AT_CREATION
    assert "bereits invalidiert" in detail


def test_close_under_invalidation_is_excluded():
    d, c = _impulse(95.0)                         # < invalidation -> raus
    entry, reason, _ = pipe.build_candidate("T", d, c)
    assert entry is None and reason == pipe.INVALIDATED_AT_CREATION


def test_watchlist_invalidated_stays_with_setup():
    # Watchlist ruft mit exclude_invalidated_at_creation=False -> Setup
    # bleibt sichtbar.
    d, c = _impulse(95.0)
    entry, reason, _ = pipe.build_candidate(
        "T", d, c, exclude_invalidated_at_creation=False)
    assert entry is not None and reason is None
    assert entry["close"] <= entry["invalidation_price"]   # invalidiert, aber sichtbar


def test_invalidated_at_creation_in_skip_reasons():
    assert pipe.INVALIDATED_AT_CREATION in pipe.SKIP_REASONS


# ---------------------------------------------------------------------------
# 2) Operator-Mutationsprobe (<=, nicht <) — Gleichstand muss ausschließen
# ---------------------------------------------------------------------------
def test_operator_ist_kleiner_gleich_nicht_nur_kleiner():
    # Exakte Gleichheit close == invalidation_price muss ausschließen — ein
    # Dreh auf `<` würde test_close_on_invalidation_is_excluded rot machen.
    assert pipe._invalidiert_bei_anlage(100.0, 100.0) is True
    assert pipe._invalidiert_bei_anlage(100.0001, 100.0) is False


# ---------------------------------------------------------------------------
# 3) Fail-soft (fehlende/nicht-endliche Werte) — reine Funktionsprobe, da
#    über den realen classify_setup-Pfad invalidation_price/close IMMER
#    endlich sind (Code-Lektüre, s. Kommentar bei _invalidiert_bei_anlage in
#    elliott_pipeline.py — kein beobachteter realer Fall, daher kein
#    Mini-Stopp nötig).
# ---------------------------------------------------------------------------
def test_fail_soft_none_invalidation_price():
    assert pipe._invalidiert_bei_anlage(100.0, None) is None


def test_fail_soft_nan_close():
    assert pipe._invalidiert_bei_anlage(math.nan, 100.0) is None


def test_fail_soft_inf_invalidation_price():
    assert pipe._invalidiert_bei_anlage(100.0, math.inf) is None


# ---------------------------------------------------------------------------
# 4) Nachrücker-Logik + Diag-Zähler (_scan_market)
# ---------------------------------------------------------------------------
def _mixed_fetcher(mapping):
    """mapping: ticker -> 'ok' (über Invalidierung) | 'invalid' (darunter)."""
    ok_d, ok_c = _impulse(105.0)
    inv_d, inv_c = _impulse(95.0)

    def fetcher(ticker):
        if mapping[ticker] == "invalid":
            return pipe.FetchOutcome(data=(list(inv_d), list(inv_c)))
        return pipe.FetchOutcome(data=(list(ok_d), list(ok_c)))

    return fetcher


def test_scan_market_excludes_invalidated_and_counts():
    universe = ["A", "B", "C", "X1", "X2"]
    mapping = {"A": "ok", "B": "ok", "C": "ok", "X1": "invalid", "X2": "invalid"}
    candidates, reason_counts, _s, _d, _b, _lb = pipe._scan_market(
        universe, _mixed_fetcher(mapping))
    assert len(candidates) == 3                               # nur die handelbaren
    assert reason_counts[pipe.INVALIDATED_AT_CREATION] == 2    # exakt die 2 invalidierten
    for r in (pipe.FETCH_ERROR, pipe.EMPTY_DATA, pipe.TOO_FEW_PIVOTS,
              pipe.NO_VALID_COUNT, pipe.SHORT_SETUP_EXCLUDED,
              pipe.TARGET_EXCEEDED, pipe.TARGET_EXT_EXCEEDED):
        assert reason_counts[r] == 0
    for c in candidates:
        assert c["close"] > c["invalidation_price"]


def test_nachruecker_fills_top5_no_empty_slots():
    # 7 handelbare + 2 invalidierte -> Top-5 bleibt voll besetzt (Rang 6+
    # rückt nach), die 2 Verbrauchten fehlen; keine leeren Slots.
    universe = [f"OK{i}" for i in range(7)] + ["INV1", "INV2"]
    mapping = {t: ("invalid" if t.startswith("INV") else "ok") for t in universe}
    candidates, reason_counts, _s, _d, _b, _lb = pipe._scan_market(
        universe, _mixed_fetcher(mapping))
    top = sorted(candidates, key=lambda e: (-e["score_heuristic"], e["ticker"]))[:config.TOP_N]
    assert len(top) == config.TOP_N == 5
    assert reason_counts[pipe.INVALIDATED_AT_CREATION] == 2
    assert all(not t["ticker"].startswith("INV") for t in top)


# ---------------------------------------------------------------------------
# 5) Zusammenspiel mit der Forward-Sammlung (Filter verhindert Neu-Anlage)
# ---------------------------------------------------------------------------
def test_collection_never_sees_invalidated_market_setup():
    universe = ["A", "INV1"]
    candidates, _rc, _s, _d, _b, _lb = pipe._scan_market(universe, _mixed_fetcher(
        {"A": "ok", "INV1": "invalid"}))
    report = {"markets": {"US": {"candidates": candidates}}}
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    price = {"A": _impulse(105.0), "INV1": _impulse(95.0)}
    fc.update_forward_collection(coll, report, price, {"US": "risk_on"},
                                 "2026-10-17", "2026-10-17T00:00:00Z")
    tickers = {r["ticker"] for r in coll["records"]}
    assert "INV1" not in tickers                      # invalidiertes Setup nie gesammelt
    assert "A" in tickers


# ---------------------------------------------------------------------------
# 6) Ranking-Determinismus + Score/Ranking der gültigen Kandidaten unverändert
# ---------------------------------------------------------------------------
def test_scan_market_deterministic_with_filter():
    universe = ["A", "B", "INV1", "C", "INV2"]
    mapping = {"A": "ok", "B": "ok", "C": "ok", "INV1": "invalid", "INV2": "invalid"}
    import json
    a = pipe._scan_market(universe, _mixed_fetcher(mapping))[0]
    b = pipe._scan_market(universe, _mixed_fetcher(mapping))[0]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_score_of_valid_candidate_unaffected_by_filter():
    # Score eines handelbaren Kandidaten ist identisch, ob der Filter aktiv
    # ist oder nicht — der Filter wirkt NUR auf invalidierte Setups.
    d, c = _impulse(105.0)
    e1, _r1, _d1 = pipe.build_candidate("T", d, c, exclude_invalidated_at_creation=True)
    e2, _r2, _d2 = pipe.build_candidate("T", d, c, exclude_invalidated_at_creation=False)
    assert e1["score_heuristic"] == e2["score_heuristic"]


# ---------------------------------------------------------------------------
# 7 · Gegentest über gespeicherte Daten: die bereits (PR #185/#189) markierten
#     `invertiertes_risiko_bei_anlage`-Records SIND exakt die Fälle, die
#     dieser Filter — hätte er zur Anlagezeit schon gegolten — nie als Record
#     hätte entstehen lassen. Beleg aus dem echten Bestand, nicht erraten.
# ---------------------------------------------------------------------------
def test_gegentest_bestehende_invertiertes_risiko_marker_erfuellen_das_kriterium():
    coll = fc.load_collection()
    records = coll.get("records", [])
    markiert = [r for r in records if r.get("invertiertes_risiko_bei_anlage") is True]
    assert len(markiert) >= 13   # Stand 17.10.2026: 11 (PR #185) + 2 (PR #189)
    betroffene_ticker = set()
    for rec in markiert:
        urteil = pipe._invalidiert_bei_anlage(
            rec.get("entry_close"), rec.get("invalidation_price"))
        assert urteil is True   # identisches Kriterium, andere Quelle
        betroffene_ticker.add(rec["ticker"])
    # Namentlich dieselben Titel wie in der Registry-Historie (PR #185/#189).
    assert {"BAC", "FME.DE", "JUN3.DE"} <= betroffene_ticker
