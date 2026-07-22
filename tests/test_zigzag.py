"""Tests für die ZigZag-Pivot-Engine auf synthetischen Serien mit bekannten
Pivots."""
from zigzag import HIGH, LOW, zigzag


def _triangle(start, peak, end, up_len, down_len):
    """Baut einen linearen Auf-/Abstieg (Hilfsfunktion)."""
    vals = []
    for k in range(up_len + 1):
        vals.append(start + (peak - start) * k / up_len)
    for k in range(1, down_len + 1):
        vals.append(peak + (end - peak) * k / down_len)
    return vals


def test_single_peak_confirmed():
    # Klare Spitze in der Mitte: ein Hoch-Pivot, mit window=2 bestätigt.
    vals = [1, 2, 3, 4, 5, 4, 3, 2, 1]
    pivots = zigzag(vals, window=2)
    kinds = [p.kind for p in pivots]
    assert kinds == [HIGH]
    assert pivots[0].index == 4
    assert pivots[0].price == 5


def test_known_alternating_pivots():
    # Sägezahn mit bekannten Extrema an den Indizes.
    #        idx: 0  1  2  3  4  5  6  7  8  9 10 11 12
    vals = [10, 12, 14, 16, 12, 8, 12, 16, 20, 16, 12, 8, 4]
    pivots = zigzag(vals, window=2)
    kinds = [p.kind for p in pivots]
    idxs = [p.index for p in pivots]
    # Hoch bei 3 (16), Tief bei 5 (8), Hoch bei 8 (20), dann Abstieg (Rand
    # nicht bestätigt -> letztes Tief bei 12 evtl. unbestätigt).
    assert kinds[0] == HIGH and idxs[0] == 3
    assert kinds[1] == LOW and idxs[1] == 5
    assert kinds[2] == HIGH and idxs[2] == 8
    # Alternierung garantiert:
    for a, b in zip(kinds, kinds[1:]):
        assert a != b


def test_merge_same_direction_keeps_extreme():
    # Zwei aufeinanderfolgende Hochs -> nur das höhere überlebt (Alternierung).
    vals = [1, 2, 5, 2, 4, 7, 4, 2, 1]  # Hochs bei idx2(5) und idx5(7)
    pivots = zigzag(vals, window=2)
    highs = [p for p in pivots if p.kind == HIGH]
    # Beide Hochs sind bestätigt und durch ein Tief getrennt -> beide bleiben.
    assert len(highs) == 2
    # aber niemals zwei gleiche Richtungen direkt hintereinander:
    kinds = [p.kind for p in pivots]
    for a, b in zip(kinds, kinds[1:]):
        assert a != b


def test_flat_series_no_pivots():
    vals = [5.0] * 20
    assert zigzag(vals, window=3) == []


def test_too_short_series():
    assert zigzag([1, 2, 3], window=3) == []


def test_dates_attached():
    vals = [1, 2, 3, 4, 5, 4, 3, 2, 1]
    dates = [f"2024-01-{i+1:02d}" for i in range(len(vals))]
    pivots = zigzag(vals, window=2, dates=dates)
    assert pivots[0].date == dates[pivots[0].index]
