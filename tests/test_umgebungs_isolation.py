"""Kein Test darf davon abhängen, WO er läuft.

DER VORFALL (06.08.2026): Die CI auf `main` war bei **15 von 16** Läufen rot,
PR-Läufe dagegen bei 13 von 14 grün. Wochenlang. Es fiel niemandem auf, weil
der grüne Haken am PR hängt und niemand die Push-Läufe ansieht — das Signal
„CI rot" war damit wertlos, weil es dauerrot war.

Die Ursache war kein Produktionsfehler, sondern ein **Umgebungsleck im Test**:
``health_check.is_main_run()`` liest ``GITHUB_REF``. Bei einem Push auf `main`
steht dort ``refs/heads/main`` — also feuerte der Herzschlag mitten im
Unit-Test und ``test_healthy_run_yields_zero_findings`` fiel mit „gesunder Lauf
ist absolut still". Bei einem PR-Lauf steht ``refs/pull/N/merge``, lokal steht
gar nichts. Deshalb war es überall grün, wo jemand hinsah.

Diese Datei nagelt beides fest: dass die Umgebung im Test neutral ist, und dass
die ECHTE Bedingung des roten Laufs die Reihe nicht mehr kippt.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import health_check as hc  # noqa: E402

from conftest import NEUTRALE_UMGEBUNG  # noqa: E402


def test_die_fixture_raeumt_die_gelisteten_variablen_ab():
    """Billig, aber sie hält die Liste ehrlich: was drinsteht, ist auch weg."""
    for name in NEUTRALE_UMGEBUNG:
        assert os.environ.get(name) is None, f"{name} steht noch"


def test_die_liste_deckt_jede_umgebungsvariable_des_produktionscodes():
    """Wächst der Produktionscode um eine Variable, muss sie in die Liste.

    Sonst wiederholt sich der Vorfall mit einer anderen Variable — und wieder
    erst dann, wenn ein Läufer sie zufällig gesetzt hat.
    """
    import re
    gelesen = set()
    for datei in sorted((ROOT / "scripts").glob("*.py")):
        for treffer in re.finditer(r"os\.environ\.get\(\s*[\"']([A-Z_]+)[\"']",
                                   datei.read_text(encoding="utf-8")):
            gelesen.add(treffer.group(1))
    fehlend = gelesen - set(NEUTRALE_UMGEBUNG)
    assert not fehlend, (
        f"Produktionscode liest {sorted(fehlend)}, die Fixture räumt sie nicht "
        f"weg — dieselbe Falle wie GITHUB_REF am 06.08.2026")


def test_is_main_run_ist_im_test_IMMER_falsch():
    """Der konkrete Auslöser: ohne die Fixture wäre das auf einem
    main-Push-Läufer `True` und der Herzschlag feuerte in den Unit-Tests."""
    assert hc.is_main_run() is False


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/pull/77/merge", ""])
def test_die_reihe_bleibt_gruen_egal_welcher_GITHUB_REF_gesetzt_ist(ref):
    """Der ECHTE Regressionstest — und der einzige, der wirklich beißt.

    Ein Test im selben Prozess kann das nicht beweisen: die Fixture hat die
    Variable längst geräumt, und ein eigenes ``setenv`` gewönne ohnehin. Also
    wird pytest in einem KINDPROZESS gestartet, dessen Umgebung genau die
    Bedingung trägt, unter der die CI auf `main` rot lief.

    Bewusst nur die eine betroffene Datei statt der ganzen Reihe: sie enthält
    den gefallenen Test, läuft in ~1 s, und ein Kindprozess über 945 Tests je
    Parameter wäre eine Minute Laufzeit für dieselbe Aussage.
    """
    umgebung = dict(os.environ)
    umgebung["GITHUB_REF"] = ref
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_health_check.py"],
        cwd=str(ROOT), env=umgebung, capture_output=True, text=True,
        timeout=300)
    assert r.returncode == 0, (
        f"GITHUB_REF={ref!r} kippt die Reihe:\n{r.stdout[-3000:]}")
