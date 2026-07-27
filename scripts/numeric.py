"""Das Finit-Prädikat — EINE Quelle für alle Zahlen-Guards.

WARUM ES DAS GIBT (27.07.2026, Ursachen-Fix zu #51):
``x is not None`` ist **wahr** für ``NaN``. Und **jeder** Vergleich mit ``NaN``
ist **False** — auch ``nan <= 0``, auch ``nan > 0``. Ein Guard der Form

    if x is None or x <= 0:      # NaN rutscht durch
    if x is not None:            # NaN rutscht durch
    if x:                        # NaN ist truthy -> rutscht durch

schützt also nicht, er **schweigt**. Das Ergebnis rechnet still weiter und
wird irgendwo hinten zu ``NaN`` — im Elliott-Report bis in die Zielzone, den
Score oder die Reifung.

Deshalb: **eine** Hilfe, überall dieselbe, statt drei Kopien mit je eigener
Auslegung. ``health_check.py`` (die Sicht­barkeits-Ebene aus #51) benutzt
dasselbe Prädikat — was der Health-Check meldet und was die Pipeline
verwirft, kann so nicht auseinanderlaufen.

SEMANTIK-REGEL für die Aufrufer (je Fundstelle bewusst gewählt, siehe PR):
  • **Messfeld** → nicht-finit wird ``None`` (die Zahl fehlt ehrlich),
  • **Kandidat/Bar** → nicht-finit wird **verworfen** und **gezählt**,
  • **niemals** stilles Weiterrechnen.
"""
from __future__ import annotations

import math
from typing import Iterable


def finite(v) -> bool:
    """Ist ``v`` eine echte, ENDLICHE Zahl?

    ``None``, ``NaN``, ``±Inf``, ``bool`` und alles Nicht-Numerische → False.
    ``bool`` fliegt bewusst raus: ``True`` ist zwar ``int``, aber nie ein
    Messwert — ein durchgerutschtes Flag wäre still genauso falsch wie ein NaN.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


def all_finite(values: Iterable) -> bool:
    """True, wenn ALLE Werte endlich sind (leere Folge → True)."""
    return all(finite(v) for v in values)


def finite_or_none(v):
    """``float(v)`` wenn endlich, sonst ``None`` — die Messfeld-Semantik."""
    return float(v) if finite(v) else None
