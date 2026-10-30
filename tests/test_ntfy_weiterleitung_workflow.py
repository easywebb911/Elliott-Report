"""ntfy-Weiterleitung (Easy-Entscheid 30.10.2026, Auftrag 4 von 6) —
STRUKTUR-Prüfung der Workflow-YAML selbst.

GRENZE (Guardian-Auftrag: aktiv zum Ausbruch bringen): kein Eingabewert
(`title`/`message`/`tags`/`priority`) darf jemals DIREKT als
`${{ inputs.* }}` oder `${{ github.event.* }}` in einem `run:`-Block
stehen — eine solche Interpolation passiert VOR der Shell und wäre
Befehlsausführung, nicht etwas, das ein Python-Filter danach noch
reparieren könnte. Diese Datei prüft die YAML-Struktur dafür, NICHT nur
den String-Text — auch ein mehrzeiliger `run:`-Block mit YAML-Faltung
wird über den geparsten Wert geprüft (s. `_alle_run_bloecke`).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github/workflows/ntfy_weiterleitung.yml"
WORKFLOW_TEXT = WORKFLOW_PATH.read_text(encoding="utf-8")
SKRIPT_TEXT = (ROOT / "scripts/ntfy_payload.py").read_text(encoding="utf-8")


def _yaml() -> dict:
    """PyYAML liest ein nacktes `on:` unter YAML-1.1-Regeln als Boolean
    `True` — s. dasselbe Muster in test_midday_report_refresh_workflow.py."""
    doc = yaml.safe_load(WORKFLOW_TEXT)
    if "on" not in doc and True in doc:
        doc["on"] = doc.pop(True)
    return doc


def _alle_run_bloecke(doc: dict) -> list:
    bloecke = []
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                bloecke.append(step["run"])
    return bloecke


# ---------------------------------------------------------------------------
# Auslöser / Rechte / Concurrency
# ---------------------------------------------------------------------------
def test_nur_workflow_dispatch_als_ausloeser():
    doc = _yaml()
    assert set(doc["on"].keys()) == {"workflow_dispatch"}


def test_vier_erwartete_inputs_mit_defaults():
    doc = _yaml()
    inputs = doc["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs.keys()) == {"title", "message", "tags", "priority"}
    assert inputs["message"]["required"] is True
    for name in ("title", "tags", "priority"):
        assert inputs[name].get("required", False) is False
        assert "default" in inputs[name]


def test_permissions_sind_leer():
    doc = _yaml()
    assert doc["permissions"] == {}


def test_concurrency_begrenzt():
    doc = _yaml()
    assert doc["concurrency"]["group"]
    assert "cancel-in-progress" in doc["concurrency"]


# ---------------------------------------------------------------------------
# Die scharfe Grenze: keine Eingabe-Interpolation in einem run:-Block
# ---------------------------------------------------------------------------
def test_kein_inputs_interpolation_in_run_bloecken():
    doc = _yaml()
    for block in _alle_run_bloecke(doc):
        assert "inputs." not in block, (
            f"run:-Block referenziert 'inputs.' direkt (Injektionsrisiko): {block!r}")


def test_kein_github_event_interpolation_in_run_bloecken():
    doc = _yaml()
    for block in _alle_run_bloecke(doc):
        assert "github.event" not in block, (
            f"run:-Block referenziert 'github.event' direkt: {block!r}")


def test_inputs_kommen_ausschliesslich_ueber_env_ins_skript():
    doc = _yaml()
    job = doc["jobs"]["weiterleiten"]
    sende_step = next(s for s in job["steps"] if "NTFY_IN_TITLE" in str(s.get("env", {})))
    env = sende_step["env"]
    assert env["NTFY_IN_TITLE"] == "${{ inputs.title }}"
    assert env["NTFY_IN_MESSAGE"] == "${{ inputs.message }}"
    assert env["NTFY_IN_TAGS"] == "${{ inputs.tags }}"
    assert env["NTFY_IN_PRIORITY"] == "${{ inputs.priority }}"


def test_secret_nur_auf_dem_einen_sende_schritt():
    doc = _yaml()
    steps_mit_secret = [
        s for s in doc["jobs"]["weiterleiten"]["steps"]
        if "NTFY_TOPIC" in str(s.get("env", {}))
    ]
    assert len(steps_mit_secret) == 1
    assert steps_mit_secret[0]["env"]["NTFY_TOPIC"] == "${{ secrets.NTFY_TOPIC }}"


# ---------------------------------------------------------------------------
# Kein Leck ins öffentliche Protokoll
# ---------------------------------------------------------------------------
def test_kein_set_minus_x():
    """Nur die tatsaechlich AUSGEFUEHRTEN run:-Bloecke zaehlen — Erklaer-
    Kommentare im Workflow-Kopf duerfen die verbotene Zeichenfolge nennen,
    ohne den Test auszuloesen."""
    doc = _yaml()
    for block in _alle_run_bloecke(doc):
        assert "set -x" not in block


def test_kein_echo_der_eingaben():
    """Verboten ist das Ausgeben des WERTS einer Eingabe-/Secret-Variable
    (Shell-Expansion `$NTFY_IN_...`/`${NTFY_IN_...}`/`$NTFY_TOPIC`/
    `${NTFY_TOPIC}`) in einer echo-Zeile — eine STATISCHE Fehlermeldung,
    die nur den NAMEN NTFY_TOPIC nennt (kein `$`/`{` davor), ist erlaubt
    und enthaelt keinen Wert."""
    doc = _yaml()
    for block in _alle_run_bloecke(doc):
        for zeile in block.splitlines():
            z = zeile.strip()
            if z.startswith("echo "):
                for verboten in ("$NTFY_IN_", "${NTFY_IN_", "$NTFY_TOPIC", "${NTFY_TOPIC"):
                    assert verboten not in z, (
                        f"echo-Zeile gibt eine Eingabe-/Secret-VARIABLE aus: {zeile!r}")


def test_kein_github_step_summary_schreiben():
    doc = _yaml()
    for block in _alle_run_bloecke(doc):
        assert "GITHUB_STEP_SUMMARY" not in block


def test_ausgabe_zeile_hat_das_geforderte_format():
    assert 'echo "ntfy gesendet, HTTP' in WORKFLOW_TEXT


def test_fehlendes_secret_fuehrt_zu_klarer_meldung_und_abbruch():
    doc = _yaml()
    job = doc["jobs"]["weiterleiten"]
    sende_step = next(s for s in job["steps"] if "NTFY_TOPIC" in str(s.get("env", {})))
    lauf = sende_step["run"]
    assert 'if [ -z "$NTFY_TOPIC" ]' in lauf
    assert "exit 1" in lauf


def test_kein_neues_secret_ausser_ntfy_topic():
    assert "secrets." in WORKFLOW_TEXT
    import re
    gefunden = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", WORKFLOW_TEXT))
    assert gefunden == {"NTFY_TOPIC"}


# ---------------------------------------------------------------------------
# Mutationsproben (ohne die Workflow-/Skript-Datei zu verändern) — belegen,
# dass die obigen Prüfungen nicht vacuous sind.
# ---------------------------------------------------------------------------
def test_mutationsprobe_inputs_direkt_im_run_block_waere_erkannt():
    kaputter_block = 'echo "${{ inputs.message }}"'
    assert "inputs." in kaputter_block
    doc = _yaml()
    for block in _alle_run_bloecke(doc):
        assert block != kaputter_block


def test_mutationsprobe_set_minus_x_waere_erkannt():
    kaputter_block = "set -x\necho hallo"
    assert "set -x" in kaputter_block
    doc = _yaml()
    for block in _alle_run_bloecke(doc):
        assert block != kaputter_block
        assert "set -x" not in block


# ---------------------------------------------------------------------------
# Konsumenten/Nachbarn unangetastet (Auftrag Punkt 4: greppen)
# ---------------------------------------------------------------------------
def test_notify_py_unberuehrt_eigener_secret_name_identisch():
    notify = (ROOT / "scripts/notify.py").read_text(encoding="utf-8")
    assert 'os.environ.get("NTFY_TOPIC"' in notify
    # dasselbe Secret, kein neues:
    assert "NTFY_TOPIC" in WORKFLOW_TEXT


def test_skript_ist_abhaengigkeitsfrei_kein_requests_import():
    assert "import requests" not in SKRIPT_TEXT
    assert "import config" not in SKRIPT_TEXT
    assert "import repo_path" not in SKRIPT_TEXT


def test_schutz_zonen_deckt_workflows_verzeichnis_bereits_ab():
    """Kein Zonen-Eintrag extra nötig — `.github/workflows/` ist bereits als
    Verzeichnis-Praefix geschuetzt (belegt, nicht angenommen)."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import schutz_zonen as sz
    assert any(".github/workflows/".startswith(p) or
               str(WORKFLOW_PATH.relative_to(ROOT)).startswith(p)
               for p in sz.GESCHUETZTE_VERZEICHNIS_PRAEFIXE)
