"""Elliott-Wellen Regel-Validator.

Prüft die DREI harten Elliott-Regeln als K.o.-Kriterien für einen 5-teiligen
Impuls (Punkte P0..P5, Wellen W1..W5):

    P0 --W1--> P1 --W2--> P2 --W3--> P3 --W4--> P4 --W5--> P5

  Regel 1: W2 retraciert W1 nie um mehr als 100 %.
           (Aufwärts: P2 fällt nicht unter P0.)
  Regel 2: W3 ist nie die KÜRZESTE der Wellen 1 / 3 / 5.
  Regel 3: W4 überlappt den Preisbereich von W1 nicht.
           (Aufwärts: P4 liegt über P1.)

Der Validator ist richtungsneutral: Er bestimmt die Impuls-Richtung aus
P0 -> P1 und normalisiert intern auf "aufwärts", damit die Regeln nur einmal
formuliert werden müssen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

# Regel-Bezeichner (stabil, auch für JSON/Reporting nutzbar).
RULE_W2_RETRACE = "rule_w2_retrace_le_100"
RULE_W3_NOT_SHORTEST = "rule_w3_not_shortest"
RULE_W4_NO_OVERLAP = "rule_w4_no_overlap_w1"


@dataclass
class ValidationResult:
    is_valid: bool
    direction: int  # +1 aufwärts, -1 abwärts
    violations: List[str] = field(default_factory=list)
    # Kennzahlen (immer in "aufwärts"-Normalisierung, alle >= 0 erwartet):
    lengths: List[float] = field(default_factory=list)  # [W1..W5]


def _normalize_up(points: Sequence[float]) -> tuple[List[float], int]:
    """Multipliziert die Punkte so, dass ein Aufwärts-Impuls entsteht."""
    direction = 1 if points[1] >= points[0] else -1
    norm = [direction * p for p in points]
    return norm, direction


def validate_impulse(points: Sequence[float]) -> ValidationResult:
    """Validiert einen kompletten 5-Wellen-Impuls (6 Punkte P0..P5)."""
    if len(points) != 6:
        raise ValueError("validate_impulse erwartet genau 6 Punkte (P0..P5)")

    p, direction = _normalize_up(points)
    p0, p1, p2, p3, p4, p5 = p

    # Wellenlängen (Preis-Beträge) in normalisierter Aufwärts-Sicht.
    w1 = p1 - p0
    w2 = p1 - p2
    w3 = p3 - p2
    w4 = p3 - p4
    w5 = p5 - p4
    lengths = [w1, w2, w3, w4, w5]

    violations: List[str] = []

    # Regel 1: W2 retraciert W1 nie > 100 % -> P2 >= P0.
    if p2 < p0:
        violations.append(RULE_W2_RETRACE)

    # Regel 2: W3 nie die kürzeste von W1/W3/W5.
    # Verletzt, wenn W3 strikt kürzer als W1 UND strikt kürzer als W5.
    if w3 < w1 and w3 < w5:
        violations.append(RULE_W3_NOT_SHORTEST)

    # Regel 3: W4 überlappt W1 nicht -> P4 > P1.
    if p4 <= p1:
        violations.append(RULE_W4_NO_OVERLAP)

    return ValidationResult(
        is_valid=len(violations) == 0,
        direction=direction,
        violations=violations,
        lengths=[abs(x) for x in lengths],
    )


def validate_partial_to_w4(points: Sequence[float]) -> ValidationResult:
    """Teil-Validierung für ein W1–W4-Setup (5 Punkte P0..P4, W5 noch offen).

    Prüfbar sind hier Regel 1 (W2) und Regel 3 (W4-Überlappung). Regel 2
    (W3 kürzeste) braucht W5 und wird bewusst NICHT als K.o. gewertet.
    """
    if len(points) != 5:
        raise ValueError("validate_partial_to_w4 erwartet genau 5 Punkte (P0..P4)")

    p, direction = _normalize_up(points)
    p0, p1, p2, p3, p4 = p

    w1 = p1 - p0
    w2 = p1 - p2
    w3 = p3 - p2
    w4 = p3 - p4

    violations: List[str] = []
    if p2 < p0:
        violations.append(RULE_W2_RETRACE)
    if p4 <= p1:
        violations.append(RULE_W4_NO_OVERLAP)

    return ValidationResult(
        is_valid=len(violations) == 0,
        direction=direction,
        violations=violations,
        lengths=[abs(w1), abs(w2), abs(w3), abs(w4)],
    )
