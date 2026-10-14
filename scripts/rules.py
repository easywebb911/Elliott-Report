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

ZWEI ZUSÄTZLICHE K.o.-KRITERIEN (14.10.2026, Diagnose-Folgeauftrag, Easy-
Entscheidung — Befund: BAC, Top-5 Platz 1, 5 von 202 Records der Sammlung).
Lücke: die DREI Regeln oben + die bisherige Richtungs-Bestimmung
(``_normalize_up``) prüfen nur, dass ``P1 >= P0`` NACH der Normalisierung
gilt — das ist tautologisch wahr (die Normalisierung erzwingt es) und sagt
nichts darüber aus, ob ``P0`` wirklich der zur Richtung passende Pivot-TYP
ist (Hoch/Tief), oder ob ``P2`` tatsächlich gegenläufig zu ``P1`` liegt. Bei
BAC lag ``P0`` auf einem Hoch (59,60) und ``P1`` auf einem HÖHEREN Tief
(60,76) — geometrisch unmöglich für eine echte ZigZag-Folge, aber von den
drei bestehenden Regeln nicht erfasst.

  Regel 4 (RULE_TREND_ORIGIN_KIND): ``kind(P0)`` muss der zur Richtung
           passende Extrempunkt-Typ sein — 'L' bei Long, 'H' bei Short.
  Regel 5 (RULE_W2_COUNTERTREND): normalisiert muss ``P2 < P1`` STRENG
           gelten — W2 muss die Bewegung von W1 umkehren (retracen), nicht
           fortsetzen.

Beide neue Regeln sind OPTIONAL in der Signatur (``kinds=None``) und an
DIESELBE Bedingung gekoppelt: ohne Pivot-Kind-Information werden BEIDE
übersprungen — auch Regel 5, obwohl sie technisch keine Kind-Information
bräuchte. Grund: zwei bestehende Aufrufer in ``elliott_pipeline.py`` kennen
nur Preise, nie Pivot-Kinds (``_classify_structure``/``_detect_correction`` —
reine Watchlist-/ABC-Korrektur-Anzeige, kein Markt-Setup). Ohne die Kopplung
hätte Regel 5 dort STILLSCHWEIGEND mitgegriffen, obwohl nur die Markt-
Pipeline beauftragt war (Diagnose-Mini-Stopp 14.10.2026, s. PR-Text) —
"nicht berechenbar"/"nicht beauftragt" heißt hier "nicht geprüft", nie
"bestanden" vorgetäuscht.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# Regel-Bezeichner (stabil, auch für JSON/Reporting nutzbar).
RULE_W2_RETRACE = "rule_w2_retrace_le_100"
RULE_W3_NOT_SHORTEST = "rule_w3_not_shortest"
RULE_W4_NO_OVERLAP = "rule_w4_no_overlap_w1"
RULE_TREND_ORIGIN_KIND = "rule_trend_origin_kind"
RULE_W2_COUNTERTREND = "rule_w2_countertrend_to_w1"


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


def _trend_consistency_violations(p_normalized: Sequence[float],
                                  kinds: Optional[Sequence[str]],
                                  direction: int) -> List[str]:
    """Die ZWEI neuen K.o.-Kriterien (s. Moduldoc), EINE Stelle für alle drei
    Aufrufer (Impuls, Teil-Impuls-W4, Ende-W2 — über `check_trend_consistency`).

    ``p_normalized``: bereits richtung-normalisierte Preise (P0..Pn, 'aufwärts').
    ``kinds``: Pivot-Kinds ('H'/'L') in URSPRÜNGLICHER Reihenfolge, gleiche
    Länge/Index wie die Original-Punkte (Kind ändert sich durch die
    Richtungs-Spiegelung NICHT) — oder ``None``, wenn nicht bekannt.

    BEIDE Regeln hängen an DERSELBEN Bedingung (``kinds is not None``), nicht
    nur Regel 4: Aufrufer, die nur Preise ohne Pivot-Kind kennen (die
    Watchlist-Strukturerkennung ``_classify_structure``/die ABC-Korrektur-
    Erkennung ``_detect_correction`` in ``elliott_pipeline.py`` — beide rufen
    ``validate_impulse``/``validate_partial_to_w4`` OHNE ``kinds`` auf), bleiben
    dadurch VOLLSTÄNDIG unverändert, bis bewusst entschieden ist, ob Regel 5
    (die an sich auch ohne Kind prüfbar wäre) dort ebenfalls gelten soll —
    s. PR-Text/Diagnose-Mini-Stopp vom 14.10.2026. Ohne diese Kopplung hätte
    Regel 5 dort STILLSCHWEIGEND mitgegriffen, obwohl nur die Markt-Pipeline
    (classify_setup/enumerate_long_counts, die ``kinds`` übergeben) beauftragt
    war."""
    if kinds is None:
        return []
    violations: List[str] = []
    erwarteter_p0_kind = "L" if direction > 0 else "H"
    if kinds[0] != erwarteter_p0_kind:
        violations.append(RULE_TREND_ORIGIN_KIND)
    if len(p_normalized) >= 3 and not (p_normalized[2] < p_normalized[1]):
        violations.append(RULE_W2_COUNTERTREND)
    return violations


def check_trend_consistency(points: Sequence[float],
                            kinds: Optional[Sequence[str]] = None) -> List[str]:
    """Öffentlicher Zugang zu den zwei neuen K.o.-Kriterien für Aufrufer, die
    keinen der beiden Haupt-Validatoren nutzen (z. B. das 3-Punkte-Ende-W2-
    Setup in ``elliott_pipeline._eval_end_of_w2``) — EINE Stelle statt einer
    dritten Kopie. Braucht mindestens 3 Punkte (P0, P1, P2)."""
    p, direction = _normalize_up(points)
    return _trend_consistency_violations(p, kinds, direction)


def validate_impulse(points: Sequence[float],
                     kinds: Optional[Sequence[str]] = None) -> ValidationResult:
    """Validiert einen kompletten 5-Wellen-Impuls (6 Punkte P0..P5).

    ``kinds`` (additiv, optional): Pivot-Kinds für Regel 4, s. Moduldoc."""
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

    # Regel 4 + 5 (14.10.2026): s. Moduldoc.
    violations.extend(_trend_consistency_violations(p, kinds, direction))

    return ValidationResult(
        is_valid=len(violations) == 0,
        direction=direction,
        violations=violations,
        lengths=[abs(x) for x in lengths],
    )


def validate_partial_to_w4(points: Sequence[float],
                           kinds: Optional[Sequence[str]] = None) -> ValidationResult:
    """Teil-Validierung für ein W1–W4-Setup (5 Punkte P0..P4, W5 noch offen).

    Prüfbar sind hier Regel 1 (W2) und Regel 3 (W4-Überlappung). Regel 2
    (W3 kürzeste) braucht W5 und wird bewusst NICHT als K.o. gewertet.
    ``kinds`` (additiv, optional): Pivot-Kinds für Regel 4, s. Moduldoc.
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

    # Regel 4 + 5 (14.10.2026): s. Moduldoc.
    violations.extend(_trend_consistency_violations(p, kinds, direction))

    return ValidationResult(
        is_valid=len(violations) == 0,
        direction=direction,
        violations=violations,
        lengths=[abs(w1), abs(w2), abs(w3), abs(w4)],
    )
