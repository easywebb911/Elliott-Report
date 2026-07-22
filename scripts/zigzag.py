"""ZigZag Pivot-Engine.

Findet *bestätigte* Hoch-/Tief-Pivots über ein symmetrisches Fenster und
liefert eine garantiert alternierende Pivot-Sequenz (H, L, H, L, ...).

Design-Entscheidungen (bewusst simpel & deterministisch):
- Arbeitet auf einer einzelnen Preisreihe (üblicherweise Schlusskurse). Das
  ist reproduzierbar und robust; High/Low-Trennung kann später additiv
  ergänzt werden.
- "Bestätigt" heißt: ein Bar ist nur dann Pivot-Kandidat, wenn links UND
  rechts je WINDOW Bars existieren und er dort das Extremum ist. Die letzten
  WINDOW Bars sind daher nie bestätigt (kein Look-ahead-Bias).
- Aufeinanderfolgende gleichgerichtete Extrema werden zusammengeführt
  (nur das extremere überlebt) -> Alternierung ist garantiert.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

HIGH = "H"
LOW = "L"


class Pivot:
    """Ein bestätigter Pivot-Punkt."""

    __slots__ = ("index", "price", "kind", "date")

    def __init__(self, index: int, price: float, kind: str, date: Optional[str] = None):
        self.index = index
        self.price = float(price)
        self.kind = kind  # HIGH oder LOW
        self.date = date

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "date": self.date,
            "price": round(self.price, 4),
            "kind": self.kind,
        }

    def __repr__(self) -> str:  # pragma: no cover - Debug-Hilfe
        return f"Pivot(i={self.index}, {self.kind}, {self.price:.2f})"


def _confirmed_extrema(values: Sequence[float], window: int) -> List[Pivot]:
    """Rohe Pivot-Kandidaten: Bars, die im symmetrischen Fenster Extremum sind.

    Ein Bar kann sowohl Hoch als auch Tief markieren, wenn das Fenster flach
    ist; solche mehrdeutigen Bars werden übersprungen (die Merge-Stufe kann
    sie ohnehin nicht sinnvoll einordnen).
    """
    n = len(values)
    pivots: List[Pivot] = []
    for i in range(n):
        if i - window < 0 or i + window > n - 1:
            continue  # Fenster ragt über den Rand -> nicht bestätigbar
        seg = values[i - window : i + window + 1]
        v = values[i]
        is_high = v >= max(seg)
        is_low = v <= min(seg)
        if is_high and is_low:
            continue  # flaches Fenster -> mehrdeutig, überspringen
        if is_high:
            pivots.append(Pivot(i, v, HIGH))
        elif is_low:
            pivots.append(Pivot(i, v, LOW))
    return pivots


def _merge_alternating(pivots: List[Pivot]) -> List[Pivot]:
    """Führt gleichgerichtete Nachbarn zusammen und garantiert Alternierung."""
    merged: List[Pivot] = []
    for p in pivots:
        if not merged:
            merged.append(p)
            continue
        last = merged[-1]
        if p.kind == last.kind:
            # Gleiche Richtung -> nur das extremere behalten.
            keep_new = (p.price > last.price) if p.kind == HIGH else (p.price < last.price)
            if keep_new:
                merged[-1] = p
        else:
            merged.append(p)
    return merged


def zigzag(
    values: Sequence[float],
    window: int,
    dates: Optional[Sequence[str]] = None,
) -> List[Pivot]:
    """Bestätigte, alternierende Pivot-Sequenz.

    Args:
        values: Preisreihe (z. B. Schlusskurse).
        window: symmetrisches Bestätigungs-Fenster (>= 1).
        dates: optionale Datumsstrings gleicher Länge (für das Frontend).

    Returns:
        Liste von Pivot-Objekten, chronologisch, garantiert alternierend.
    """
    if window < 1:
        raise ValueError("window muss >= 1 sein")
    if len(values) < 2 * window + 1:
        return []

    pivots = _confirmed_extrema(values, window)
    pivots = _merge_alternating(pivots)

    if dates is not None:
        for p in pivots:
            if 0 <= p.index < len(dates):
                p.date = dates[p.index]
    return pivots


def pivot_prices(pivots: Sequence[Pivot]) -> List[float]:
    """Nur die Preise (Hilfsfunktion für den Regel-Validator)."""
    return [p.price for p in pivots]
