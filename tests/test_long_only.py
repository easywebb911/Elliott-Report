"""Tests für den Long-only-Filter.

Short-Setups (Abwärts-Erwartung) müssen VOR dem Ranking verworfen werden und
als eigener Skip-Grund `short_setup_excluded` gezählt werden. Long-Setups
bleiben unverändert.

Testdaten: der synthetische Fetcher erzeugt einen Aufwärts-Impuls (Long-Setup
Ende W2). Durch vertikale Spiegelung (K - Kurs) wird daraus ein
Abwärts-Impuls -> Short-Setup. So decken wir beide Richtungen ab.
"""
import elliott_pipeline as pipe

_K = 300.0  # Spiegelachse; hält alle gespiegelten Kurse positiv


def _long_series(ticker="AAPL"):
    dates, closes = pipe.fetch_synthetic(ticker).data
    return dates, list(closes)


def _short_series(ticker="AAPL"):
    dates, longs = _long_series(ticker)
    return dates, [_K - c for c in longs]


def _mixed_fetcher(mapping):
    """mapping: ticker -> 'long' | 'short' -> FetchOutcome mit passender Reihe."""
    dates, longs = _long_series("SEED")
    shorts = [_K - c for c in longs]

    def fetcher(ticker):
        closes = longs if mapping[ticker] == "long" else shorts
        return pipe.FetchOutcome(data=(dates, list(closes)))

    return fetcher


def test_build_candidate_long_passes():
    dates, closes = _long_series("AAPL")
    entry, reason, detail = pipe.build_candidate("AAPL", dates, closes)
    assert entry is not None
    assert reason is None
    assert entry["direction"] == "long"
    assert "Short" not in entry["count_label"]


def test_build_candidate_short_excluded():
    dates, closes = _short_series("AAPL")
    entry, reason, detail = pipe.build_candidate("AAPL", dates, closes)
    assert entry is None
    assert reason == pipe.SHORT_SETUP_EXCLUDED
    assert "short" in detail.lower()


def test_scan_market_mixed_only_longs_and_counter():
    universe = ["L1", "L2", "L3", "S1", "S2"]
    mapping = {"L1": "long", "L2": "long", "L3": "long", "S1": "short", "S2": "short"}
    candidates, reason_counts, _samples, _dead = pipe._scan_market(universe, _mixed_fetcher(mapping))

    # Nur Long-Kandidaten im Output.
    assert len(candidates) == 3
    for c in candidates:
        assert c["direction"] == "long"
        assert "Short" not in c["count_label"]

    # Skip-Zähler weist exakt die 2 aussortierten Shorts aus ...
    assert reason_counts[pipe.SHORT_SETUP_EXCLUDED] == 2
    # ... und keine anderen Gründe wurden fälschlich ausgelöst.
    for r in (pipe.FETCH_ERROR, pipe.EMPTY_DATA, pipe.TOO_FEW_PIVOTS, pipe.NO_VALID_COUNT):
        assert reason_counts[r] == 0


def test_short_setup_excluded_in_skip_reasons():
    assert pipe.SHORT_SETUP_EXCLUDED in pipe.SKIP_REASONS


def _dead_fetcher(mapping):
    """mapping: ticker -> 'ok' | 'empty' | 'boom' — für die Hygiene-Sammlung."""
    dates, longs = _long_series("SEED")

    def fetcher(ticker):
        mode = mapping[ticker]
        if mode == "empty":
            return pipe.FetchOutcome(reason=pipe.EMPTY_DATA, detail="leer")
        if mode == "boom":
            raise RuntimeError("net down")
        return pipe.FetchOutcome(data=(dates, list(longs)))

    return fetcher


def test_scan_market_collects_dead_tickers_by_name():
    # Listen-Hygiene: empty_data + fetch_error werden NAMENTLICH gesammelt,
    # too_few_pivots/no_valid_count NICHT (die sind keine toten Symbole).
    universe = ["OK1", "DEADX", "OK2", "BOOMX"]
    mapping = {"OK1": "ok", "DEADX": "empty", "OK2": "ok", "BOOMX": "boom"}
    candidates, reason_counts, _samples, dead = pipe._scan_market(
        universe, _dead_fetcher(mapping))
    dead_map = dict(dead)
    assert dead_map == {"DEADX": pipe.EMPTY_DATA, "BOOMX": pipe.FETCH_ERROR}
    assert reason_counts[pipe.EMPTY_DATA] == 1
    assert reason_counts[pipe.FETCH_ERROR] == 1
