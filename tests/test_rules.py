"""Tests für den Elliott-Regel-Validator: je ein Positiv- und ein
Verletzungsfall pro harter Regel."""
from rules import (
    RULE_W2_RETRACE,
    RULE_W3_NOT_SHORTEST,
    RULE_W4_NO_OVERLAP,
    validate_impulse,
    validate_partial_to_w4,
)


# Referenz-Impuls (aufwärts), erfüllt alle drei Regeln:
#   P0=0 P1=10 P2=5 P3=20 P4=12 P5=25
VALID_UP = [0, 10, 5, 20, 12, 25]


def test_valid_impulse_up():
    res = validate_impulse(VALID_UP)
    assert res.is_valid
    assert res.direction == 1
    assert res.violations == []


def test_valid_impulse_down_mirror():
    # Gespiegelter Abwärts-Impuls muss ebenso valide sein (Richtungsneutralität).
    down = [-x for x in VALID_UP]
    res = validate_impulse(down)
    assert res.is_valid
    assert res.direction == -1
    assert res.violations == []


# --- Regel 1: W2 retraciert W1 nie > 100 % --------------------------------
def test_rule1_pass():
    res = validate_impulse([0, 10, 1, 20, 12, 25])  # P2=1 knapp über P0=0
    assert RULE_W2_RETRACE not in res.violations


def test_rule1_violation():
    res = validate_impulse([0, 10, -1, 20, 12, 25])  # P2 unter P0 -> >100 %
    assert not res.is_valid
    assert RULE_W2_RETRACE in res.violations


# --- Regel 2: W3 nie die kürzeste von W1/W3/W5 ----------------------------
def test_rule2_pass():
    res = validate_impulse(VALID_UP)  # w3=15 ist die längste
    assert RULE_W3_NOT_SHORTEST not in res.violations


def test_rule2_violation():
    # w1=5, w3=4 (kürzer), w5=5 (länger) -> W3 strikt kürzeste. Andere Regeln
    # bleiben erfüllt (P2>=P0, P4>P1).
    res = validate_impulse([0, 5, 3, 7, 6, 11])
    assert not res.is_valid
    assert RULE_W3_NOT_SHORTEST in res.violations


# --- Regel 3: W4 überlappt W1-Preisbereich nicht --------------------------
def test_rule3_pass():
    res = validate_impulse(VALID_UP)  # P4=12 > P1=10
    assert RULE_W4_NO_OVERLAP not in res.violations


def test_rule3_violation():
    res = validate_impulse([0, 10, 5, 20, 9, 25])  # P4=9 <= P1=10 -> Überlappung
    assert not res.is_valid
    assert RULE_W4_NO_OVERLAP in res.violations


# --- Teil-Validierung W1..W4 ----------------------------------------------
def test_partial_valid():
    res = validate_partial_to_w4([0, 10, 5, 20, 12])
    assert res.is_valid
    assert res.violations == []


def test_partial_overlap_violation():
    res = validate_partial_to_w4([0, 10, 5, 20, 9])
    assert not res.is_valid
    assert RULE_W4_NO_OVERLAP in res.violations


def test_wrong_point_count_raises():
    import pytest

    with pytest.raises(ValueError):
        validate_impulse([0, 1, 2, 3, 4])  # nur 5 Punkte
