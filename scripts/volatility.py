"""ATR(14) — Average True Range, EIN Volatilitätsmaß für die Band-Breite um
die Fibonacci-Beobachtungszone/-Extension (23.08.2026, Bau-Auftrag "Band statt
Linie").

FORMEL (Standard, wie im Auftrag vorgegeben — keine eigene Variante):

    True Range[i] = max(High[i]-Low[i], |High[i]-Close[i-1]|,
                         |Low[i]-Close[i-1]|)
    ATR(14)       = einfacher gleitender Durchschnitt der letzten 14
                    True-Range-Werte

Bewusst die einfache 14er-Durchschnittsbildung (kein Wilder-Smoothing).

EINE Stelle, wiederverwendbar (Auftrag Punkt 1): Tages-ATR wird EINMAL beim
Parsen des Downloads berechnet (``elliott_pipeline.parse_download_df``) und
von dort als Skalar durchgereicht — nicht mehrfach neu gerechnet.

Messfeld-Semantik (siehe ``numeric.py``): fehlen High/Low für auch nur einen
der letzten 15 Bars, wird ATR ``None`` statt eines aus Lücken gemittelten
Werts (die Pipeline lud bis 23.08.2026 nur Close/Volume — High/Low kommen aus
demselben Download, ohne neuen Netz-Call, siehe PR-Text).
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from numeric import finite

ATR_PERIOD = 14


def true_range(high: float, low: float, prev_close: float) -> float:
    """Wahre Spanne EINES Bars gegenüber dem Vor-Schlusskurs."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr14(
    highs: Optional[Sequence[Optional[float]]],
    lows: Optional[Sequence[Optional[float]]],
    closes: Sequence[float],
) -> Optional[float]:
    """ATR(14) aus den letzten ``ATR_PERIOD`` True-Range-Werten (braucht dafür
    ``ATR_PERIOD + 1`` Bars, da der erste TR-Wert den Vor-Schlusskurs
    braucht). ``None`` bei fehlenden High/Low oder zu kurzer Reihe — Messfeld
    fehlt ehrlich, kein Rateergebnis."""
    if highs is None or lows is None:
        return None
    n = len(closes)
    if len(highs) != n or len(lows) != n or n < ATR_PERIOD + 1:
        return None
    tr_values: List[float] = []
    for i in range(n - ATR_PERIOD, n):
        h, l, prev_c = highs[i], lows[i], closes[i - 1]
        if not (finite(h) and finite(l) and finite(prev_c)):
            return None
        tr_values.append(true_range(h, l, prev_c))
    return round(sum(tr_values) / ATR_PERIOD, 4)
