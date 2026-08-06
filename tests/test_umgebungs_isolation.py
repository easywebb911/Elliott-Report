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


def _env_zugriffe(quelle: str):
    """Alle Umgebungs-Zugriffe einer Datei — als AST, nicht als Textsuche.

    **Warum nicht per Regex:** ein Guardian-Nit (06.08.2026) traf genau ins
    Ziel — eine Suche nach ``os.environ.get("X")`` übersieht
    ``os.environ["X"]`` und ``os.getenv("X")``. Dieselbe Fallenklasse, nur
    anders geschrieben, wäre unentdeckt geblieben, und der Test hätte mehr
    Schutz versprochen, als er liefert.

    Gibt zwei Mengen zurück: die **literalen** Namen und die Zahl der
    Zugriffe, deren Name erst zur Laufzeit feststeht. Letztere kann keine
    statische Prüfung auflösen — sie werden deshalb nicht verschwiegen,
    sondern gezählt und gemeldet.
    """
    import ast
    literale, dynamisch = set(), []

    def _name(knoten):
        return (knoten.value
                if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str)
                else None)

    for k in ast.walk(ast.parse(quelle)):
        ziel = None
        if isinstance(k, ast.Call):
            f = k.func
            # os.environ.get("X") / os.getenv("X")
            if isinstance(f, ast.Attribute) and f.attr in ("get", "getenv") and k.args:
                if f.attr == "getenv" or (isinstance(f.value, ast.Attribute)
                                          and f.value.attr == "environ"):
                    ziel = k.args[0]
        elif isinstance(k, ast.Subscript):
            # os.environ["X"]
            if isinstance(k.value, ast.Attribute) and k.value.attr == "environ":
                ziel = k.slice
        if ziel is None:
            continue
        name = _name(ziel)
        if name is None:
            dynamisch.append(ast.dump(ziel)[:60])
        else:
            literale.add(name)
    return literale, dynamisch


def test_die_liste_deckt_jede_umgebungsvariable_des_produktionscodes():
    """Wächst der Produktionscode um eine Variable, muss sie in die Liste.

    Sonst wiederholt sich der Vorfall mit einer anderen Variable — und wieder
    erst dann, wenn ein Läufer sie zufällig gesetzt hat.
    """
    gelesen, dynamisch = set(), []
    for datei in sorted((ROOT / "scripts").glob("*.py")):
        lit, dyn = _env_zugriffe(datei.read_text(encoding="utf-8"))
        gelesen |= lit
        dynamisch += [f"{datei.name}: {d}" for d in dyn]
    fehlend = gelesen - set(NEUTRALE_UMGEBUNG)
    assert not fehlend, (
        f"Produktionscode liest {sorted(fehlend)}, die Fixture räumt sie nicht "
        f"weg — dieselbe Falle wie GITHUB_REF am 06.08.2026")
    # EHRLICHE GRENZE, statt sie zu verschweigen: steht der Variablenname erst
    # zur Laufzeit fest, kann keine statische Prüfung ihn kennen. Heute gibt es
    # keinen solchen Zugriff; entsteht einer, soll dieser Test laut werden und
    # nicht stillschweigend weiter Vollständigkeit behaupten.
    assert not dynamisch, (
        f"Umgebungs-Zugriff mit nicht-literalem Namen: {dynamisch} — dieser "
        f"Test kann ihn nicht prüfen, die Variable muss von Hand in "
        f"NEUTRALE_UMGEBUNG")


def test_der_scanner_findet_ALLE_drei_schreibweisen():
    """Gegenprobe zum Scanner selbst — sonst ist er eine Attrappe.

    Genau das war der Guardian-Nit: die erste Fassung suchte nur nach
    `os.environ.get(...)`. Ein Scanner, der die halbe Sprache übersieht,
    meldet Vollständigkeit, wo keine ist.
    """
    quelle = (
        "import os\n"
        "a = os.environ.get('EINS')\n"
        "b = os.environ['ZWEI']\n"
        "c = os.getenv('DREI')\n"
        "d = os.environ.get(schluessel)\n"
    )
    literale, dynamisch = _env_zugriffe(quelle)
    assert literale == {"EINS", "ZWEI", "DREI"}
    assert len(dynamisch) == 1, "der Laufzeit-Name muss als solcher auffallen"


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
