"""Tests für den Elliott-Regel-Validator: je ein Positiv- und ein
Verletzungsfall pro harter Regel."""
from rules import (
    RULE_TREND_ORIGIN_KIND,
    RULE_W2_COUNTERTREND,
    RULE_W2_RETRACE,
    RULE_W3_NOT_SHORTEST,
    RULE_W4_NO_OVERLAP,
    check_trend_consistency,
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


# ===========================================================================
# Regel 4 + 5 (14.10.2026, Diagnose-Folgeauftrag) — Befund: BAC, Top-5
# Platz 1. P0 lag auf einem Hoch (59,60), P1 auf einem HÖHEREN Tief (60,76):
# geometrisch unmöglich für eine echte ZigZag-Folge, von den Regeln 1-3
# nicht erfasst (die normalisierte Richtung macht P1 >= P0 tautologisch wahr).
# ===========================================================================

# BAC-Muster, auf einfache Zahlen übertragen: P0 auf einem "Hoch" (59,60),
# P1 auf einem HÖHEREN "Tief" (60,76), P2 auf einem Hoch, das W1 NICHT
# retraciert, sondern fortsetzt (64,48 > P1) — exakt der Befund.
BAC_MUSTER = [59.60, 60.76, 64.48, 60.86, 62.72]
BAC_KINDS = ["H", "L", "H", "L", "H"]

# Saubere Long-Zählung: P0 Tief, P1 Hoch, P2 Tief (retraciert), P3 Hoch, P4 Tief.
SAUBER_LONG = [0, 10, 5, 20, 12]
SAUBER_LONG_KINDS = ["L", "H", "L", "H", "L"]

# Sauberer Short-Impuls (6 Punkte, für validate_impulse): Spiegelbild, P0 Hoch,
# P1 Tief, P2 Hoch (retraciert), P3 Tief, P4 Hoch, P5 Tief.
SAUBER_SHORT_IMPULS = [0, -10, -5, -20, -12, -25]
SAUBER_SHORT_IMPULS_KINDS = ["H", "L", "H", "L", "H", "L"]


def test_bac_muster_wird_ohne_kind_info_weiterhin_akzeptiert():
    """Ohne `kinds` (altes Verhalten, z. B. Watchlist-Strukturerkennung):
    Regel 4+5 werden ÜBERSPRUNGEN — byte-identisch zum Vorher-Zustand."""
    res = validate_partial_to_w4(BAC_MUSTER)
    assert res.is_valid
    assert res.violations == []


def test_bac_muster_wird_mit_kind_info_verworfen():
    res = validate_partial_to_w4(BAC_MUSTER, BAC_KINDS)
    assert not res.is_valid
    assert RULE_TREND_ORIGIN_KIND in res.violations
    assert RULE_W2_COUNTERTREND in res.violations


def test_saubere_long_zaehlung_bleibt_mit_kind_info_gueltig():
    res = validate_partial_to_w4(SAUBER_LONG, SAUBER_LONG_KINDS)
    assert res.is_valid
    assert res.violations == []


def test_sauberer_short_impuls_bleibt_mit_kind_info_gueltig():
    res = validate_impulse(SAUBER_SHORT_IMPULS, SAUBER_SHORT_IMPULS_KINDS)
    assert res.is_valid
    assert res.violations == []
    assert res.direction == -1


def test_regel4_verletzung_wave0_falscher_typ_bei_short():
    # Short-Setup (P0 muss ein Hoch sein), aber P0 ist als Tief markiert.
    falsch_kinds = ["L", "H", "L", "H", "H", "L"]  # P0 fälschlich "L" statt "H"
    res = validate_impulse(SAUBER_SHORT_IMPULS, falsch_kinds)
    assert not res.is_valid
    assert RULE_TREND_ORIGIN_KIND in res.violations


def test_regel5_w2_setzt_bewegung_fort_statt_zu_retracen():
    # P2 >= P1 (normalisiert) statt P2 < P1 -> W2 retraciert nicht.
    muster = [0, 10, 15, 25, 18]   # P2=15 > P1=10: Fortsetzung statt Rückschlag
    res = validate_partial_to_w4(muster, ["L", "H", "L", "H", "L"])
    assert not res.is_valid
    assert RULE_W2_COUNTERTREND in res.violations
    # Regel 1 (P2 >= P0) bleibt separat erfüllt — die neue Regel ist eine
    # ZUSÄTZLICHE, keine Ersatz-Bedingung.
    assert RULE_W2_RETRACE not in res.violations


def test_regel5_randfall_p2_exakt_gleich_p1_ist_verletzung():
    # P2 == P1 (kein echter Rückschlag) -> P2 < P1 ist STRIKT, Gleichstand zählt
    # als Verletzung (kein Toleranz-Fall).
    muster = [0, 10, 10, 20, 12]
    res = validate_partial_to_w4(muster, ["L", "H", "L", "H", "L"])
    assert not res.is_valid
    assert RULE_W2_COUNTERTREND in res.violations


# --- Öffentliche Funktion für den 3-Punkte-Pfad (Ende W2) -----------------
def test_check_trend_consistency_3_punkte_sauber():
    assert check_trend_consistency([0, 10, 5], ["L", "H", "L"]) == []


def test_check_trend_consistency_3_punkte_bac_artig():
    # P0 Hoch, P1 höheres Tief, P2 setzt fort statt zu retracen.
    v = check_trend_consistency([59.60, 60.76, 64.48], ["H", "L", "H"])
    assert RULE_TREND_ORIGIN_KIND in v
    assert RULE_W2_COUNTERTREND in v


def test_check_trend_consistency_ohne_kinds_ueberspringt_regel4():
    # Ohne kinds: nur Regel 5 wäre theoretisch prüfbar — aber beide Regeln
    # hängen BEWUSST an derselben Bedingung (s. rules.py-Moduldoc), damit
    # Aufrufer ohne Kind-Wissen (Watchlist/ABC-Korrektur) unverändert bleiben.
    assert check_trend_consistency([59.60, 60.76, 64.48]) == []


# ===========================================================================
# MUTATIONSPROBEN (Auftrag TESTS) — eine lokale "kaputte" Variante neben der
# echten, beide auf demselben Fall ausgeführt: echt und kaputt MÜSSEN sich
# unterscheiden, sonst wäre die Probe wertlos.
# ===========================================================================
def test_mutationsprobe_kind_pruefung_entfernt():
    """Kaputt: Regel 4 (Kind-Prüfung) fehlt komplett — das BAC-Muster würde
    nur noch an Regel 5 scheitern. Hier so konstruiert, dass NUR Regel 4
    greifen würde (W2 retraciert hier korrekt), damit die Probe eindeutig ist."""
    muster = [59.60, 60.76, 55.0, 62.0, 58.0]   # P2=55 < P1=60.76: retraciert OK
    kinds = ["H", "L", "H", "L", "H"]           # P0 trotzdem falscher Typ

    def kaputt_ohne_regel4(points, kinds):
        p, direction = points, (1 if points[1] >= points[0] else -1)
        norm = [direction * x for x in p]
        v = []
        if not (norm[2] < norm[1]):
            v.append(RULE_W2_COUNTERTREND)
        return v  # FEHLT: die Kind-Prüfung (Regel 4)

    echt = check_trend_consistency(muster, kinds)
    kaputt = kaputt_ohne_regel4(muster, kinds)
    assert RULE_TREND_ORIGIN_KIND in echt
    assert RULE_TREND_ORIGIN_KIND not in kaputt
    assert echt != kaputt


def test_mutationsprobe_p2_kleiner_p1_auf_kleiner_gleich_gedreht():
    """Kaputt: Vergleich `P2 < P1` auf `P2 <= P1` gedreht — der Randfall
    P2 == P1 (kein echter Rückschlag) würde dann FÄLSCHLICH noch als
    Verletzung durchgehen... in Wahrheit ist die Mutation hier andersrum
    gefährlich: `<=` statt `<` als GÜLTIGKEITS-Bedingung (statt als
    Verletzungs-Bedingung) ließe P2==P1 fälschlich DURCH. Genau das prüft
    dieser Test: eine Variante, die `norm[2] <= norm[1]` als "noch gültig"
    wertet (statt `< ` strikt zu verlangen), akzeptiert den Gleichstand-Fall
    fälschlich."""
    muster = [0, 10, 10, 20, 12]  # P2 == P1

    def kaputt_mit_kleiner_gleich(points):
        p, direction = points, (1 if points[1] >= points[0] else -1)
        norm = [direction * x for x in p]
        v = []
        if not (norm[2] <= norm[1]):   # FALSCH: <= statt < als Gültig-Bedingung
            v.append(RULE_W2_COUNTERTREND)
        return v

    echt = check_trend_consistency(muster, ["L", "H", "L", "H", "L"])
    kaputt = kaputt_mit_kleiner_gleich(muster)
    assert RULE_W2_COUNTERTREND in echt
    assert RULE_W2_COUNTERTREND not in kaputt
    assert echt != kaputt
