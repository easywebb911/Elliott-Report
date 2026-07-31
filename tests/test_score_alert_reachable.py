"""Der Score-Alarm muss ERREICHBAR sein — für JEDEN Setup-Typ.

Warum es diese Datei gibt (31.07.2026): die Schwelle stand als feste `90` in
`config.py`, während das erreichbare Maximum des besten Setup-Typs exakt
`55 + 20 + 15 = 90.00` beträgt — und der Vergleich lautete `> 90`. Der Alarm
konnte also **nie** auslösen. Über 53 committete Report-Stände (500 Scores)
lag der Höchststand bei 89.84; der Kommentar in `config.py` las das als
„selten" statt als „unmöglich". Ein Test, der das gemerkt hätte, gab es nicht.

Hier steht er. Er rechnet NICHT dieselbe Formel nach wie der Code — die
Sollwerte sind von Hand ausgeschrieben:

    end_of_w4 : (55 + 20 + 15) * 0.98 = 88.20   von Maximum 90.00
    end_of_w2 : (45 + 20 + 15) * 0.98 = 78.40   von Maximum 80.00
    end_of_c  : (40 + 20 + 15) * 0.98 = 73.50   von Maximum 75.00
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import elliott_pipeline as pipe  # noqa: E402
import forward_collection as fc  # noqa: E402

# Von Hand nachgerechnet, NICHT aus config abgeleitet.
SOLL = {
    "end_of_w4": (90.00, 88.20),
    "end_of_w2": (80.00, 78.40),
    "end_of_c": (75.00, 73.50),
}


def test_jeder_setup_typ_hat_eine_ERREICHBARE_schwelle():
    """Der Kernsatz: Schwelle STRIKT unter dem Maximum — je Typ.

    Fängt jede künftige Konstanten-Änderung, die den Alarm wieder tötet: ob
    jemand einen Deckel senkt, den Anteil auf 1.0 stellt oder einen Setup-Typ
    ergänzt, dessen Maximum unter der Schwelle liegt.
    """
    assert set(SOLL) == set(config.SETUP_BASE_POINTS), \
        "Setup-Typen haben sich geändert — Sollwerte hier nachziehen"
    for typ in config.SETUP_BASE_POINTS:
        maximum = config.score_max(typ)
        schwelle = config.score_alert_threshold(typ)
        assert schwelle < maximum, (
            f"{typ}: Schwelle {schwelle} >= Maximum {maximum} — der Alarm ist "
            f"für diesen Typ konstruktiv tot (genau der Defekt vom 31.07.2026)")


def test_die_schwellen_haben_die_von_hand_gerechneten_werte():
    for typ, (maximum, schwelle) in SOLL.items():
        assert round(config.score_max(typ), 2) == maximum, typ
        assert round(config.score_alert_threshold(typ), 2) == schwelle, typ


def test_der_rueckfall_ist_die_STRENGSTE_schwelle():
    """Unbekannter Typ -> konservativ, aber nicht stumm."""
    assert round(config.score_alert_threshold_max(), 2) == 88.20
    assert config.score_alert_threshold_max() == max(
        config.score_alert_threshold(t) for t in config.SETUP_BASE_POINTS)
    # Auch der Rückfall muss erreichbar bleiben.
    assert config.score_alert_threshold_max() < max(
        config.score_max(t) for t in config.SETUP_BASE_POINTS)


def test_der_anteil_ist_die_einzige_neue_zahl():
    """Keine zweite Schwelle, die still veralten kann."""
    assert config.SCORE_ALERT_FRACTION == 0.98
    assert not hasattr(config, "SCORE_ALERT_THRESHOLD"), \
        "die feste Schwelle ist zurück — sie war der Defekt"
    quelle = (ROOT / "config.py").read_text(encoding="utf-8")
    assert "SCORE_ALERT_THRESHOLD" not in quelle.replace(
        "die alte feste Schwelle 90", "")


# ---------------------------------------------------------------------------
# Der Typ kommt aus dem `count_label` — LAUFZEIT geprüft, nicht per Textsuche
# ---------------------------------------------------------------------------
def test_echte_setups_werden_ihrem_typ_zugeordnet():
    """`classify_setup` erzeugt die Labels, `setup_typ_aus_label` liest sie.

    Beide laufen hier WIRKLICH. Ein Umformulieren der Beschriftung (und damit
    ein stiller Verlust der Typ-Erkennung) macht diesen Test rot — er ist der
    Ersatz dafür, dass der Report den Typ nicht als eigenes Feld führt.
    """
    faelle = [
        # p0 tief, p1 hoch, p2 Retrace, p3 hoch, p4 Retrace (W4 ohne Überlappung)
        ("end_of_w4", pipe._eval_end_of_w4([100.0, 120.0, 110.0, 150.0, 135.0], 140.0)),
        ("end_of_w2", pipe._eval_end_of_w2([100.0, 120.0, 110.0], 112.0)),
    ]
    for erwartet, setup in faelle:
        assert setup is not None, f"{erwartet}: Testdaten ergeben kein Setup"
        assert setup["setup"] == erwartet
        assert fc.setup_typ_aus_label(setup["count_label"]) == erwartet, \
            f"Beschriftung {setup['count_label']!r} wird nicht mehr erkannt"
        # ... und die Schwelle passt zu den Basispunkten DIESES Setups.
        erwartete_schwelle = config.SCORE_ALERT_FRACTION * (
            setup["base_points"] + config.FIB_PROXIMITY_MAX_BONUS
            + config.INVALIDATION_DISTANCE_MAX_BONUS)
        assert config.score_alert_threshold(erwartet) == pytest.approx(
            erwartete_schwelle)


def test_unlesbares_label_ergibt_None():
    for wert in (None, 123, "", "Impuls 1–5 · Long-Setup", "Ende W9"):
        assert fc.setup_typ_aus_label(wert) is None


def test_das_typ_maximum_ist_praktisch_erreichbar():
    """Ein echtes Setup erreicht sein Maximum — die Decke ist keine Fiktion.

    Das W2-Beispiel trifft das Fibonacci-Ziel exakt und liegt weit genug von
    der Invalidierung: 45 + 20 + 15 = 80.00, also GENAU das Typ-Maximum. Damit
    ist belegt, dass die Schwelle 78.40 nicht nur formal, sondern tatsächlich
    unterschreitbar ist.
    """
    setup = pipe._eval_end_of_w2([100.0, 120.0, 110.0], 112.0)
    assert pipe.score_setup(setup) == pytest.approx(config.score_max("end_of_w2"))
    assert pipe.score_setup(setup) >= config.score_alert_threshold("end_of_w2")


def test_end_of_c_ist_derzeit_keine_erreichbare_lage():
    """Ehrlich benannt: `end_of_c` steht in den Konstanten, wird aber von
    `classify_setup` NIE erzeugt (first-fit über W4 und W2). Die Schwelle für
    diesen Typ ist damit heute rein theoretisch — der Erreichbarkeits-Test
    deckt ihn trotzdem ab, damit eine spätere Einführung nicht in dieselbe
    Falle läuft."""
    quelle = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    assert "end_of_c" not in quelle, \
        "end_of_c wird jetzt erzeugt — diesen Hinweis anpassen und den Fall belegen"
    assert "end_of_c" in config.SETUP_BASE_POINTS
