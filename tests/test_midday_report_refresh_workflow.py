"""Midday Report Refresh (neuer, additiver Workflow, 09.09.2026).

ABSOLUTE, NICHT VERHANDELBARE GRENZE: dieser Workflow darf
data/forward_collection.json/docs/data/forward_collection.json NIEMALS
committen. Der Laufzeit-Beweis liegt in tests/test_report_only_modus.py
(elliott_pipeline.main() wirklich ausgeführt) — diese Datei prüft zusätzlich
die YAML-STRUKTUR des Workflows selbst: die `git add`-Zeile im Commit-Schritt
darf die Sammlungs-Dateien strukturell gar nicht erst nennen können, auch
wenn `REPORT_ONLY` irgendwann versehentlich vergessen würde.

Zweites Netz: bestätigt, dass der bestehende Retry-Watcher (#111,
daily_retry_watcher.yml, an daily.ymls NAMEN „Daily Elliott Report"
gebunden) den neuen Workflow NICHT beobachtet — und dass daily.yml/
daily_retry_watcher.yml selbst unangetastet blieben (GRENZEN).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MIDDAY_PATH = ROOT / ".github/workflows/midday_report_refresh.yml"
MIDDAY = MIDDAY_PATH.read_text(encoding="utf-8")
DAILY = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
WATCHER = (ROOT / ".github/workflows/daily_retry_watcher.yml").read_text(encoding="utf-8")


def _yaml() -> dict:
    """PyYAML liest ein nacktes `on:` unter YAML-1.1-Regeln als Boolean
    `True`, nicht als String `"on"` — derselbe Stolperstein wie bei einer
    frueheren Ad-hoc-Pruefung in dieser Aufgabe. Beide Schluessel abdecken,
    statt sich auf den String zu verlassen."""
    doc = yaml.safe_load(MIDDAY)
    if "on" not in doc and True in doc:
        doc["on"] = doc.pop(True)
    return doc


# ---------------------------------------------------------------------------
# Die absolute Grenze: niemals die Forward-Sammlung committen
# ---------------------------------------------------------------------------
def test_git_add_im_commit_schritt_nennt_niemals_forward_collection():
    doc = _yaml()
    commit_step = next(s for s in doc["jobs"]["build"]["steps"]
                       if s.get("name", "").startswith("Commit report"))
    lauf = commit_step["run"]
    add_zeilen = [z for z in lauf.splitlines() if z.strip().startswith("git add")]
    assert add_zeilen, "kein 'git add' im Commit-Schritt gefunden"
    for zeile in add_zeilen:
        assert "forward_collection" not in zeile, (
            f"'git add' nennt die Forward-Sammlung: {zeile!r}")
    assert any("data/report.json" in z and "docs/data/report.json" in z
              for z in add_zeilen), \
        "die beiden Report-Dateien werden nicht committet — Workflow nutzlos"


def test_commit_schritt_hat_eigene_laufzeit_absicherung_gegen_gestagte_sammlung():
    """Zusätzlich zum reinen 'git add' fehlt-Beweis: ein expliziter Guard IM
    Skript selbst, der abbricht, falls die Sammlung TROTZDEM im Staging
    landet (Verteidigung in der Tiefe, nicht nur ein einziges Netz)."""
    doc = _yaml()
    commit_step = next(s for s in doc["jobs"]["build"]["steps"]
                       if s.get("name", "").startswith("Commit report"))
    lauf = commit_step["run"]
    assert "forward_collection.json" in lauf and "exit 1" in lauf
    assert "git reset" in lauf


def test_eigener_verifikations_schritt_vor_dem_commit():
    doc = _yaml()
    namen = [s.get("name", "") for s in doc["jobs"]["build"]["steps"]]
    idx_verify = next(i for i, n in enumerate(namen) if "UNVERÄNDERT" in n)
    idx_commit = next(i for i, n in enumerate(namen) if n.startswith("Commit report"))
    assert idx_verify < idx_commit, \
        "die Verifikation muss VOR dem Commit-Schritt laufen"
    verify_step = doc["jobs"]["build"]["steps"][idx_verify]
    assert "md5sum" in verify_step["run"]
    assert "exit 1" in verify_step["run"]


def test_pipeline_schritt_setzt_report_only():
    doc = _yaml()
    pipeline_step = next(s for s in doc["jobs"]["build"]["steps"]
                         if s.get("name", "").startswith("Run pipeline"))
    assert pipeline_step.get("env", {}).get("REPORT_ONLY") == "1"
    assert pipeline_step["run"].strip() == "python scripts/elliott_pipeline.py"


def test_kein_anthropic_key_noetig_im_report_only_lauf():
    """Kosten-Entscheidung (Auftrag Punkt 3) auch auf Workflow-Ebene sichtbar
    — das Secret wird gar nicht erst durchgereicht."""
    doc = _yaml()
    pipeline_step = next(s for s in doc["jobs"]["build"]["steps"]
                         if s.get("name", "").startswith("Run pipeline"))
    assert "ANTHROPIC_API_KEY" not in (pipeline_step.get("env") or {})


# ---------------------------------------------------------------------------
# Eigener, separater Cron — daily.yml bleibt unangetastet
# ---------------------------------------------------------------------------
def test_eigener_cron_werktags_und_verschieden_von_daily():
    doc = _yaml()
    cron = doc["on"]["schedule"][0]["cron"]
    minute, stunde, tag, monat, wochentag = cron.split()
    assert (tag, monat, wochentag) == ("*", "*", "1-5"), "nur Werktage Mo-Fr"
    assert cron != "45 22 * * 1-5", "darf nicht mit daily.ymls Cron kollidieren"


def test_eigene_concurrency_gruppe_getrennt_von_daily():
    doc = _yaml()
    assert doc["concurrency"]["group"] != "daily-elliott"


def test_workflow_dispatch_vorhanden_fuer_manuellen_tap():
    doc = _yaml()
    assert "workflow_dispatch" in doc["on"]


# ---------------------------------------------------------------------------
# daily.yml / #111 (daily_retry_watcher.yml) bleiben GRENZEN-konform unangetastet
# ---------------------------------------------------------------------------
def test_daily_yml_unveraendert_cron_und_verhalten():
    assert 'cron: "45 22 * * 1-5"' in DAILY
    assert DAILY.count("- cron:") == 1
    assert "data/forward_collection.json docs/data/forward_collection.json" in DAILY


def test_retry_watcher_unveraendert_und_beobachtet_nur_daily_yml():
    assert 'workflows: ["Daily Elliott Report"]' in WATCHER
    doc = _yaml()
    assert doc["name"] != "Daily Elliott Report", (
        "der neue Workflow-Name darf NICHT mit daily.ymls Namen "
        "kollidieren, sonst würde #111 ihn faelschlich beobachten")
    assert doc["name"] == "Midday Report Refresh"


def test_retry_watcher_datei_nicht_veraendert_worden():
    """Reine Anwesenheits-/Kern-Struktur-Pruefung — GRENZEN verbietet jede
    Aenderung an #111 selbst."""
    assert "workflow_run:" in WATCHER
    assert "types: [completed]" in WATCHER
    assert "MAX_RETRIES_PRO_TAG" in WATCHER or "auto_retry_watcher" in WATCHER
