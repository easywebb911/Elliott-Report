"""Filter `target_exceeded` (Produktentscheidung 23.07., PRU-Diagnose).

Setups, deren Lauf-Schlusskurs die Zielzone bereits erreicht hat
(close >= target_zone.low), sind nicht mehr handelbar und fliegen VOR dem Ranking
aus den Markt-Top-5 (Rang 6+ rückt nach). Die Watchlist zeigt sie weiter
(exclude_target_reached=False). Zusammenspiel mit dem #28-Guard = Verteidigung in
der Tiefe: der Filter verhindert die Neuanlage, der Guard schützt die Messung.
"""
import elliott_pipeline as pipe
import config
import forward_collection as fc

W = config.ZIGZAG_WINDOW


def _impulse(last_close):
    """Sauberer W2-Long (P0=100, P1=120 -> W1=20, P2=110); der Schwanz steigt bis
    ``last_close``. Zielzone W3 = P2 + [1.0,1.618]*W1 = [130, 142.36]."""
    seg = [(108.0, 100.0, W + 2), (100.0, 120.0, W + 4),
           (120.0, 110.0, W + 3), (110.0, last_close, W + 2)]
    closes = []
    for s, e, n in seg:
        rng = range(n + 1) if not closes else range(1, n + 1)
        for k in rng:
            closes.append(s + (e - s) * (k / n))
    return [f"d{i}" for i in range(len(closes))], closes


ZONE_LOW = 130.0   # target_zone.low für _impulse (P2=110 + 1.0*W1=20)


# ---------------------------------------------------------------------------
# 1) Konstruierte Fälle (Markt-Pipeline, exclude_target_reached=True)
# ---------------------------------------------------------------------------
def test_under_low_stays():
    d, c = _impulse(125.0)                       # < 130 -> handelbar
    entry, reason, _ = pipe.build_candidate("T", d, c)
    assert entry is not None and reason is None
    assert entry["close"] < entry["target_zone"]["low"]


def test_on_low_is_excluded():
    d, c = _impulse(130.0)                        # == low -> raus (>= inklusiv)
    entry, reason, detail = pipe.build_candidate("T", d, c)
    assert entry is None and reason == pipe.TARGET_EXCEEDED
    assert "Zielzone erreicht" in detail


def test_over_high_is_excluded():
    d, c = _impulse(145.0)                        # > high -> raus
    entry, reason, _ = pipe.build_candidate("T", d, c)
    assert entry is None and reason == pipe.TARGET_EXCEEDED


def test_watchlist_over_low_stays_with_setup():
    # Watchlist ruft mit exclude_target_reached=False -> Setup bleibt sichtbar.
    d, c = _impulse(145.0)
    entry, reason, _ = pipe.build_candidate("T", d, c, exclude_target_reached=False)
    assert entry is not None and reason is None
    assert entry["close"] >= entry["target_zone"]["low"]   # über Zone, aber sichtbar


def test_target_exceeded_in_skip_reasons():
    assert pipe.TARGET_EXCEEDED in pipe.SKIP_REASONS


# ---------------------------------------------------------------------------
# 2) Nachrücker-Logik + Diag-Zähler (_scan_market)
# ---------------------------------------------------------------------------
def _mixed_fetcher(mapping):
    """mapping: ticker -> 'ok' (unter Zone) | 'exceeded' (über Zone)."""
    ok_d, ok_c = _impulse(125.0)
    ex_d, ex_c = _impulse(145.0)

    def fetcher(ticker):
        if mapping[ticker] == "exceeded":
            return pipe.FetchOutcome(data=(list(ex_d), list(ex_c)))
        return pipe.FetchOutcome(data=(list(ok_d), list(ok_c)))

    return fetcher


def test_scan_market_excludes_exceeded_and_counts():
    universe = ["A", "B", "C", "X1", "X2"]
    mapping = {"A": "ok", "B": "ok", "C": "ok", "X1": "exceeded", "X2": "exceeded"}
    candidates, reason_counts, _s, _d = pipe._scan_market(universe, _mixed_fetcher(mapping))
    assert len(candidates) == 3                       # nur die handelbaren
    assert reason_counts[pipe.TARGET_EXCEEDED] == 2   # exakt die 2 über Zone
    for r in (pipe.FETCH_ERROR, pipe.EMPTY_DATA, pipe.TOO_FEW_PIVOTS,
              pipe.NO_VALID_COUNT, pipe.SHORT_SETUP_EXCLUDED):
        assert reason_counts[r] == 0
    # kein Kandidat über der Zone im Output
    for c in candidates:
        assert c["close"] < c["target_zone"]["low"]


def test_nachruecker_fills_top5_no_empty_slots():
    # 7 handelbare + 2 über Zone -> Top-5 bleibt voll besetzt (Rang 6+ rückt nach),
    # die 2 Verbrauchten fehlen; keine leeren Slots solange genug Kandidaten.
    universe = [f"OK{i}" for i in range(7)] + ["EX1", "EX2"]
    mapping = {t: ("exceeded" if t.startswith("EX") else "ok") for t in universe}
    # leichte Score-Spreizung, damit sort deterministisch bleibt (gleiche Reihe ->
    # gleicher Score -> Tie-Break per Ticker); Top-N greift auf die 7 OK zu.
    candidates, reason_counts, _s, _d = pipe._scan_market(universe, _mixed_fetcher(mapping))
    top = sorted(candidates, key=lambda e: (-e["score_heuristic"], e["ticker"]))[:config.TOP_N]
    assert len(top) == config.TOP_N == 5              # voll besetzt
    assert reason_counts[pipe.TARGET_EXCEEDED] == 2
    assert all(not t["ticker"].startswith("EX") for t in top)


# ---------------------------------------------------------------------------
# 3) Zusammenspiel mit der Forward-Sammlung (Entry-Regel + Filter)
# ---------------------------------------------------------------------------
def test_collection_never_sees_exceeded_market_setup():
    # Der Filter verhindert, dass verbrauchte Setups überhaupt in die Markt-Top-5
    # (und damit in die Sammlung) kommen. build_report liest load_watchlist() für
    # die Watchlist; wir testen den Markt-Zweig über _scan_market.
    universe = ["A", "EX1"]
    candidates, _rc, _s, _d = pipe._scan_market(universe, _mixed_fetcher(
        {"A": "ok", "EX1": "exceeded"}))
    report = {"markets": {"US": {"candidates": candidates}}}
    coll = {"schema_version": 1, "last_run_date": None, "updated_utc": None, "records": []}
    price = {"A": _impulse(125.0), "EX1": _impulse(145.0)}
    fc.update_forward_collection(coll, report, price, {"US": "risk_on"},
                                 "2026-07-24", "2026-07-24T00:00:00Z")
    tickers = {r["ticker"] for r in coll["records"]}
    assert "EX1" not in tickers                       # verbrauchtes Setup nie gesammelt
    assert "A" in tickers


# ---------------------------------------------------------------------------
# 4) Ranking-Determinismus (Filter ändert das Ergebnis nicht zufällig)
# ---------------------------------------------------------------------------
def test_scan_market_deterministic_with_filter():
    universe = ["A", "B", "EX1", "C", "EX2"]
    mapping = {"A": "ok", "B": "ok", "C": "ok", "EX1": "exceeded", "EX2": "exceeded"}
    import json
    a = pipe._scan_market(universe, _mixed_fetcher(mapping))[0]
    b = pipe._scan_market(universe, _mixed_fetcher(mapping))[0]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
