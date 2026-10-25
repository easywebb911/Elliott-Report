"""Technische Schutz-Sperre (Auftrag 3 von 6, Easy-Entscheid 24./25.10.2026,
OPTION 4 — ohne Freigabe-Label). Deckt: kein Treffer (grün), Treffer in jeder
Zonen-Gruppe, Infrastruktur-Präfix, "[Wächter]"-Hinweis, config.py auf
Symbol-Ebene (geschützte vs. andere Konstante), Umbenennen/Verschieben/
Löschen/Typechange (Symlink) einer geschützten Datei, Groß-/Kleinschreibungs-
und Unicode-Pfad-Tricks, Mutationsproben.

Reale Git-Repos in ``tmp_path`` (keine Mocks für `git diff` selbst — die
Rename-/Hunk-/AST-Logik ist zu wichtig, um sie nur gegen erfundene Strings zu
prüfen) + einige rein funktionale Tests mit monkeypatchter Zonen-Liste für
die Mutationsproben (schnell, ohne git).
"""
from __future__ import annotations

import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

import schutz_sperre as ss
import schutz_zonen as zonen


# ---------------------------------------------------------------------------
# Git-Repo-Helfer
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True).stdout


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")


def _write(repo: Path, rel: str, inhalt: str) -> None:
    pfad = repo / rel
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(inhalt, encoding="utf-8")


def _commit(repo: Path, nachricht: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", nachricht)
    return _git(repo, "rev-parse", "HEAD").strip()


_BASIS_CONFIG = '''US_UNIVERSE = ["AAA", "BBB"]

DATA_PERIOD = "2y"
DATA_INTERVAL = "1d"

SCORE_WEIGHTS = {
    "fib_bonus": 20.0,
    "invalidation_bonus": 15.0,
}

TOP_N = 5
'''


@pytest.fixture()
def repo(tmp_path) -> Path:
    _init_repo(tmp_path)
    _write(tmp_path, "config.py", _BASIS_CONFIG)
    _write(tmp_path, "scripts/evaluate.py", "# evaluate v1\n")
    _write(tmp_path, "scripts/rules.py", "# rules v1\n")
    _write(tmp_path, "README.md", "doku v1\n")
    _write(tmp_path, "tests/test_egal.py", "def test_x():\n    assert True\n")
    _commit(tmp_path, "Basis")
    return tmp_path


def _base_head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


# ---------------------------------------------------------------------------
# 1) Kein Zonen-Treffer -> grün
# ---------------------------------------------------------------------------
def test_kein_zonen_treffer_gruen(repo):
    base = _base_head(repo)
    _write(repo, "README.md", "doku v2\n")
    _write(repo, "tests/test_egal.py", "def test_x():\n    assert 1 == 1\n")
    head = _commit(repo, "nur sichere Dateien")
    assert ss.pruefe(base, head, repo_root=repo) == []


# ---------------------------------------------------------------------------
# 2) Treffer in jeder Zonen-Gruppe (Datei-Ebene, aus schutz_zonen.py selbst)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pfad", sorted(zonen.GESCHUETZTE_DATEIEN))
def test_treffer_in_jeder_geschuetzten_datei(repo, pfad):
    base = _base_head(repo)
    _write(repo, pfad, f"# geändert für Test ({pfad})\n")
    head = _commit(repo, f"ändere {pfad}")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == pfad for t in treffer), (pfad, treffer)


def test_treffer_infrastruktur_praefix_workflows(repo):
    base = _base_head(repo)
    _write(repo, ".github/workflows/irgendwas_neu.yml", "name: x\non: push\n")
    head = _commit(repo, "neuer Workflow")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert len(treffer) == 1
    assert treffer[0].datei == ".github/workflows/irgendwas_neu.yml"
    assert treffer[0].zone == "Infrastruktur-Zone"


# ---------------------------------------------------------------------------
# 3) "[Wächter]"-Titel -> zusätzlicher Hinweis, Prüfung bleibt rot
# ---------------------------------------------------------------------------
def test_waechter_titel_hinweis_im_bericht(repo):
    base = _base_head(repo)
    _write(repo, "scripts/evaluate.py", "# geändert\n")
    head = _commit(repo, "Agent-Änderung")
    treffer = ss.pruefe(base, head, repo_root=repo)
    text = ss.bericht(treffer, "[Wächter] irgendein Fund")
    assert ss.WAECHTER_HINWEIS in text
    assert "ROT" in text


def test_kein_waechter_hinweis_ohne_praefix(repo):
    base = _base_head(repo)
    _write(repo, "scripts/evaluate.py", "# geändert\n")
    head = _commit(repo, "x")
    treffer = ss.pruefe(base, head, repo_root=repo)
    text = ss.bericht(treffer, "ein normaler PR-Titel")
    assert ss.WAECHTER_HINWEIS not in text


def test_kein_label_kein_titel_macht_gruen(repo):
    """Kernregel OPTION 4: es gibt KEINEN Parameter/Pfad in `bericht()`/
    `pruefe()`, der einen Treffer wieder grün machen könnte — die Funktion
    nimmt gar kein Label/Freigabe-Argument entgegen."""
    base = _base_head(repo)
    _write(repo, "scripts/evaluate.py", "# geändert\n")
    head = _commit(repo, "x")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert treffer  # es gibt einen Treffer
    import inspect
    assert "label" not in inspect.signature(ss.pruefe).parameters
    assert "freigabe" not in inspect.signature(ss.pruefe).parameters
    assert "label" not in inspect.signature(ss.bericht).parameters


# ---------------------------------------------------------------------------
# 4) config.py: geschützte Konstante (rot) vs. andere Konstante (grün) —
#    über die AST-Zeilen-Spanne, NICHT über Text-Suche (ein mehrzeiliges
#    Dict ändert sich oft, ohne dass der Konstanten-Name selbst auf der
#    geänderten Zeile steht).
# ---------------------------------------------------------------------------
def test_config_geschuetzte_konstante_dict_wert_ohne_namen_auf_zeile_rot(repo):
    base = _base_head(repo)
    neu = _BASIS_CONFIG.replace('"fib_bonus": 20.0,', '"fib_bonus": 99.0,')
    assert neu != _BASIS_CONFIG
    _write(repo, "config.py", neu)
    head = _commit(repo, "Fib-Bonus geändert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    namen = {t.grund for t in treffer if t.datei == "config.py"}
    assert any("SCORE_WEIGHTS" in g for g in namen), treffer


def test_config_andere_konstante_gruen(repo):
    base = _base_head(repo)
    neu = _BASIS_CONFIG.replace('DATA_PERIOD = "2y"', 'DATA_PERIOD = "5y"')
    _write(repo, "config.py", neu)
    head = _commit(repo, "DATA_PERIOD geändert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert treffer == []


def test_config_top_n_geaendert_rot(repo):
    base = _base_head(repo)
    neu = _BASIS_CONFIG.replace("TOP_N = 5", "TOP_N = 8")
    _write(repo, "config.py", neu)
    head = _commit(repo, "TOP_N geändert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any("TOP_N" in t.grund for t in treffer if t.datei == "config.py")


def test_config_subscript_mutation_rot(repo):
    """Guardian-Fund (Zweitblick vor Ready, Auftrag 3 von 6): eine
    geschützte Konstante über einen Subscript statt eine direkte
    ``NAME = ...``-Neuzuweisung zu ändern, muss GENAUSO rot sein."""
    base = _base_head(repo)
    neu = _BASIS_CONFIG + '\nSCORE_WEIGHTS["fib_bonus"] = 999\n'
    _write(repo, "config.py", neu)
    head = _commit(repo, "SCORE_WEIGHTS per Subscript geändert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any("SCORE_WEIGHTS" in t.grund for t in treffer
              if t.datei == "config.py"), treffer


def test_config_methodenaufruf_mutation_rot(repo):
    """Guardian-Fund: ``SCORE_WEIGHTS.update(...)`` ändert den Inhalt ohne
    eine ``NAME = ...``-Zeile."""
    base = _base_head(repo)
    neu = _BASIS_CONFIG + '\nSCORE_WEIGHTS.update({"fib_bonus": 999})\n'
    _write(repo, "config.py", neu)
    head = _commit(repo, "SCORE_WEIGHTS per update() geändert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any("SCORE_WEIGHTS" in t.grund for t in treffer
              if t.datei == "config.py"), treffer


def test_config_augmented_assign_rot(repo):
    """Guardian-Fund: ``TOP_N += 1`` ist kein ``ast.Assign`` mit
    ``Name``-Target im alten Sinn, sondern ein ``ast.AugAssign`` — muss
    trotzdem rot sein."""
    base = _base_head(repo)
    neu = _BASIS_CONFIG + "\nTOP_N += 3\n"
    _write(repo, "config.py", neu)
    head = _commit(repo, "TOP_N augmentiert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any("TOP_N" in t.grund for t in treffer if t.datei == "config.py")


def test_config_reexport_beim_auslagern_rot(repo):
    """Guardian-Fund: eine geschützte Konstante aus config.py per Import
    zu ersetzen (Auslagerung in eine neue, nicht gelistete Datei) ist der
    PR, der die ``SCORE_WEIGHTS = {...}``-Zeile ENTFERNT — das muss rot
    bleiben (Löschen der Zuweisung zählt bereits als Treffer), UND die
    neue ``from ... import SCORE_WEIGHTS``-Zeile selbst muss erkannt
    werden (Import-Alias-Prüfung in ``_konstanten_zeilen``)."""
    base = _base_head(repo)
    neu = _BASIS_CONFIG.replace(
        'SCORE_WEIGHTS = {\n    "fib_bonus": 20.0,\n'
        '    "invalidation_bonus": 15.0,\n}\n',
        "from scripts.config_extra import SCORE_WEIGHTS\n")
    assert neu != _BASIS_CONFIG
    _write(repo, "config.py", neu)
    head = _commit(repo, "SCORE_WEIGHTS ausgelagert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any("SCORE_WEIGHTS" in t.grund for t in treffer
              if t.datei == "config.py"), treffer


def test_config_geloescht_rot_unabhaengig_von_konstanten(repo):
    base = _base_head(repo)
    (repo / "config.py").unlink()
    head = _commit(repo, "config.py gelöscht")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "config.py" for t in treffer)


def test_config_umbenannt_rot_unabhaengig_von_konstanten(repo):
    base = _base_head(repo)
    _git(repo, "mv", "config.py", "config_neu.py")
    head = _commit(repo, "config.py umbenannt")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "config.py" and "Struktur" in t.zone
              for t in treffer)


def test_config_syntaxfehler_faellt_konservativ_auf_alle_konstanten(repo):
    """Fail-soft in die SICHERE Richtung: ein kaputtes config.py kann nicht
    per AST geprüft werden -> alle geschützten Konstanten gelten als
    getroffen (,,bei Unklarheit: ja``)."""
    base = _base_head(repo)
    _write(repo, "config.py", _BASIS_CONFIG + "\ndef kaputt(:\n")
    head = _commit(repo, "config.py syntaktisch kaputt")
    treffer = ss.pruefe(base, head, repo_root=repo)
    namen = {t.grund for t in treffer if t.datei == "config.py"}
    assert any("SCORE_WEIGHTS" in g for g in namen)
    assert any("TOP_N" in g for g in namen)


# ---------------------------------------------------------------------------
# 5) Umbenennen / Verschieben / Löschen einer geschützten Datei
# ---------------------------------------------------------------------------
def test_umbenennen_geschuetzter_datei_rot_ueber_alten_pfad(repo):
    base = _base_head(repo)
    _git(repo, "mv", "scripts/evaluate.py", "scripts/evaluate_versteckt.py")
    head = _commit(repo, "evaluate.py umbenannt")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "scripts/evaluate.py" for t in treffer), treffer


def test_verschieben_in_anderes_verzeichnis_rot(repo):
    base = _base_head(repo)
    _git(repo, "mv", "scripts/rules.py", "rules.py")
    head = _commit(repo, "rules.py ins Root verschoben")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "scripts/rules.py" for t in treffer), treffer


def test_loeschen_geschuetzter_datei_rot(repo):
    base = _base_head(repo)
    (repo / "scripts" / "evaluate.py").unlink()
    head = _commit(repo, "evaluate.py gelöscht")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "scripts/evaluate.py" for t in treffer), treffer


# ---------------------------------------------------------------------------
# 6) Symlink / Typechange auf eine geschützte Datei
# ---------------------------------------------------------------------------
@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="Symlinks nicht Teil der Windows-CI-Matrix")
def test_typechange_zu_symlink_an_geschuetztem_pfad_rot(repo):
    """Eine geschützte Datei wird durch einen Symlink ERSETZT (gleicher
    Pfad, Modus 100644 -> 120000, Git meldet Status 'T'). Der Pfad bleibt
    unverändert geschützt — der Treffer kommt über den normalen Pfad-
    Abgleich, ohne Sonderfall für Symlinks nötig."""
    base = _base_head(repo)
    ziel = repo / "scripts" / "evaluate.py"
    ziel.unlink()
    os.symlink("rules.py", ziel)
    head = _commit(repo, "evaluate.py zu Symlink gemacht")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "scripts/evaluate.py" for t in treffer), treffer


@pytest.mark.skipif(sys.platform.startswith("win"),
                    reason="Symlinks nicht Teil der Windows-CI-Matrix")
def test_neuer_symlink_alias_auf_geschuetzte_datei_kein_inhalts_bypass(repo):
    """Ein NEUER Symlink an einem UNGESCHÜTZTEN Pfad, der auf eine
    geschützte Datei zeigt, ändert deren Inhalt NICHT (byte-identisch) —
    das ist bewusst außerhalb des Prüf-Umfangs (kein Zonen-Treffer für den
    Alias-Pfad selbst), weil keine geschützte LOGIK verändert wird. Dieser
    Test dokumentiert die Grenze, nicht eine Lücke."""
    base = _base_head(repo)
    os.symlink("evaluate.py", repo / "scripts" / "alias_harmlos.py")
    head = _commit(repo, "harmloser Alias")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert treffer == []


# ---------------------------------------------------------------------------
# 7) Groß-/Kleinschreibung und Unicode-Normalform — Pfad-Tricks
# ---------------------------------------------------------------------------
def test_grossschreibung_variante_eines_geschuetzten_pfads_rot(repo):
    base = _base_head(repo)
    _git(repo, "mv", "scripts/evaluate.py", "scripts/Evaluate.py")
    head = _commit(repo, "Groß-/Kleinschreibung getrickst")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any("scripts/Evaluate.py" in t.datei for t in treffer), treffer
    assert any("Groß-/Kleinschreibung" in t.zone for t in treffer)


def test_unicode_nfd_variante_wird_wie_nfc_behandelt():
    """`é` als vorkomponiertes Zeichen (NFC) und als `e` + Akzent-
    Kombinationszeichen (NFD) sehen gleich aus, sind aber unterschiedliche
    Byte-Folgen. `_normalisiert` gleicht das an (beide Schreibweisen eines
    ECHTEN Treffers zählen gleich) — reiner Funktionstest, kein Git nötig."""
    nfc = unicodedata.normalize("NFC", "scripts/evaluate.py")
    nfd = unicodedata.normalize("NFD", "scripts/evaluate.py")
    assert ss._normalisiert(nfc) == ss._normalisiert(nfd)


# ---------------------------------------------------------------------------
# 8) Änderung an der Sperre selbst / Zonen-Liste -> rot (bereits über den
#    parametrisierten Test 2 mitgeprüft, hier zusätzlich explizit benannt)
# ---------------------------------------------------------------------------
def test_aenderung_an_sperre_selbst_rot(repo):
    base = _base_head(repo)
    _write(repo, "scripts/schutz_sperre.py", "# Sperre manipuliert\n")
    head = _commit(repo, "Sperre geändert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "scripts/schutz_sperre.py" for t in treffer)


def test_aenderung_an_zonen_liste_rot(repo):
    base = _base_head(repo)
    _write(repo, "scripts/schutz_zonen.py", "# Zonen-Liste manipuliert\n")
    head = _commit(repo, "Zonen-Liste geändert")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "scripts/schutz_zonen.py" for t in treffer)


# ---------------------------------------------------------------------------
# Mutationsproben (müssen rot werden, wenn die beschriebene Mutation real
# vorgenommen würde) — direkte Funktionstests ohne Git, schnell.
# ---------------------------------------------------------------------------
def test_mutation_zone_aus_liste_entfernt(monkeypatch):
    assert ss._datei_zone("scripts/evaluate.py") is not None
    gekuerzt = zonen.GESCHUETZTE_DATEIEN - {"scripts/evaluate.py"}
    monkeypatch.setattr(zonen, "GESCHUETZTE_DATEIEN", gekuerzt)
    assert ss._datei_zone("scripts/evaluate.py") is None


def test_mutation_umbenennen_erkennung_entfernt(monkeypatch, repo):
    """Mit Rename-Tracking (Normalfall) wird der ALTE Pfad einer
    umbenannten geschützten Datei erkannt. Simuliert man das Abschalten der
    Rename-Erkennung (`diff_dateien` liefert nur den NEUEN Pfad, kein
    `alter_pfad` mehr — als würde `--find-renames` entfernt), verschwindet
    der Treffer. Das belegt, WARUM `--find-renames`/die `alter_pfad`-
    Auswertung in `pruefe()` nicht entfernt werden darf."""
    echter_diff = ss.diff_dateien

    def ohne_rename_tracking(base, head, repo_root=ss.REPO_ROOT):
        eintraege = echter_diff(base, head, repo_root)
        return [ss.DiffEintrag(e.status, e.pfad, None) for e in eintraege]

    base = _base_head(repo)
    _git(repo, "mv", "scripts/evaluate.py", "scripts/evaluate_versteckt.py")
    head = _commit(repo, "evaluate.py umbenannt")

    treffer_normal = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "scripts/evaluate.py" for t in treffer_normal)

    monkeypatch.setattr(ss, "diff_dateien", ohne_rename_tracking)
    treffer_mutiert = ss.pruefe(base, head, repo_root=repo)
    assert not any(t.datei == "scripts/evaluate.py" for t in treffer_mutiert)


def test_mutation_config_symbolpruefung_auf_dateiebene_vergroebert(repo):
    """Würde `config.py` (wie bei `proactive_watcher`) auf DATEI-Ebene
    gesperrt statt auf Symbol-Ebene, wäre `test_config_andere_konstante_
    gruen` (oben) rot statt grün — diese eine Assertion ist die
    Mutationsprobe selbst, hier zur Dokumentation gespiegelt."""
    base = _base_head(repo)
    neu = _BASIS_CONFIG.replace('DATA_PERIOD = "2y"', 'DATA_PERIOD = "5y"')
    _write(repo, "config.py", neu)
    head = _commit(repo, "nur DATA_PERIOD")
    treffer = ss.pruefe(base, head, repo_root=repo)
    assert treffer == [], (
        "config.py darf NICHT auf Datei-Ebene gesperrt sein — nur auf "
        "Symbol-Ebene (GESCHUETZTE_CONFIG_KONSTANTEN)")


def test_mutation_konfig_konstante_aus_schutzliste_entfernt(monkeypatch, repo):
    base = _base_head(repo)
    neu = _BASIS_CONFIG.replace('"fib_bonus": 20.0,', '"fib_bonus": 99.0,')
    _write(repo, "config.py", neu)
    head = _commit(repo, "Fib-Bonus geändert")

    treffer_normal = ss.pruefe(base, head, repo_root=repo)
    assert any(t.datei == "config.py" for t in treffer_normal)

    monkeypatch.setattr(
        zonen, "GESCHUETZTE_CONFIG_KONSTANTEN",
        zonen.GESCHUETZTE_CONFIG_KONSTANTEN - {"SCORE_WEIGHTS"})
    treffer_mutiert = ss.pruefe(base, head, repo_root=repo)
    assert treffer_mutiert == []


# ---------------------------------------------------------------------------
# Deterministisch: zweimaliger Aufruf mit denselben SHAs liefert dieselbe,
# sortierte Ausgabe.
# ---------------------------------------------------------------------------
def test_pruefe_deterministisch_bei_wiederholtem_aufruf(repo):
    base = _base_head(repo)
    _write(repo, "scripts/evaluate.py", "# a\n")
    _write(repo, "scripts/rules.py", "# b\n")
    head = _commit(repo, "zwei Treffer")
    a = ss.pruefe(base, head, repo_root=repo)
    b = ss.pruefe(base, head, repo_root=repo)
    assert a == b


def test_bericht_sortiert_treffer_deterministisch(repo):
    base = _base_head(repo)
    _write(repo, "scripts/rules.py", "# b\n")
    _write(repo, "scripts/evaluate.py", "# a\n")
    head = _commit(repo, "zwei Treffer, Schreibreihenfolge egal")
    treffer = ss.pruefe(base, head, repo_root=repo)
    text1 = ss.bericht(treffer, "x")
    text2 = ss.bericht(list(reversed(treffer)), "x")
    assert text1 == text2


# ---------------------------------------------------------------------------
# main(): Exit-Code und Job-Zusammenfassungs-Datei
# ---------------------------------------------------------------------------
def test_main_exit_code_1_bei_treffer_0_ohne(repo, tmp_path, monkeypatch):
    base = _base_head(repo)
    _write(repo, "scripts/evaluate.py", "# a\n")
    head = _commit(repo, "ein Treffer")
    summary = tmp_path / "summary.md"

    # main() nutzt das Modul-weite REPO_ROOT für pruefe(); für den Test
    # patchen wir es auf das temporäre Repo.
    monkeypatch.setattr(ss, "REPO_ROOT", repo)
    rc = ss.main(["--base", base, "--head", head, "--titel", "x",
                 "--summary-datei", str(summary)])
    assert rc == 1
    assert summary.exists()
    assert "ROT" in summary.read_text(encoding="utf-8")


def test_main_exit_code_0_ohne_treffer(repo, tmp_path, monkeypatch):
    base = _base_head(repo)
    _write(repo, "README.md", "doku v2\n")
    head = _commit(repo, "nur Doku")
    monkeypatch.setattr(ss, "REPO_ROOT", repo)
    rc = ss.main(["--base", base, "--head", head, "--titel", "x"])
    assert rc == 0
