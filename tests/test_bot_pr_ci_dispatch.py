"""Bot-PRs bekommen ihren Check "test" per workflow_dispatch (11.11.2026).

Befund: Der pull_request-Lauf von CI auf Bot-PRs des Handover-Sync-Bots
wartet auf Freigabe (action_required, 0 Jobs — Läufe #553–#555 auf PR #214,
#526 auf PR #204). Deshalb startet der Bot `ci.yml` nach dem Anlegen bzw.
Aktualisieren seines PRs per workflow_dispatch auf seinem Branch.

Diese Tests halten die Form fest, von der das abhängt:
- `ci.yml`: bestehende Auslöser unverändert, zusätzlich workflow_dispatch mit
  Eingabe `ref`; Job-ID `test` ohne eigenen `name:` (Check-Run heißt exakt
  "test"); Eingabe nie direkt in einem `run:`-Block.
- `handover_sync.yml`: nur `actions: write` zusätzlich; startet `ci.yml`
  ausschließlich auf dem Bot-Branch; kein Merge-Aufruf.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import handover_sync  # noqa: E402

CI = ROOT / ".github/workflows/ci.yml"
SYNC = ROOT / ".github/workflows/handover_sync.yml"


def _yaml(pfad: Path) -> dict:
    return yaml.safe_load(pfad.read_text(encoding="utf-8"))


def _ausloeser(d: dict) -> dict:
    # PyYAML liest den Schlüssel `on` als Wahrheitswert True.
    return d.get("on", d.get(True))


def test_ci_bestehende_ausloeser_unveraendert_plus_dispatch():
    on = _ausloeser(_yaml(CI))
    assert set(on) == {"pull_request", "push", "workflow_dispatch"}
    assert on["pull_request"] is None, "pull_request muss ohne Filter bleiben"
    assert on["push"] == {"branches": ["main"]}
    inputs = on["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"ref"}
    assert inputs["ref"]["required"] is False


def test_ci_job_heisst_test_ohne_eigenen_namen():
    """Der Check-Run trägt den Job-Namen; ohne `name:` ist das die Job-ID."""
    jobs = _yaml(CI)["jobs"]
    assert list(jobs) == ["test"]
    assert "name" not in jobs["test"]


def test_ci_berechtigung_und_warteschlange_unveraendert():
    d = _yaml(CI)
    assert d["permissions"] == {"contents": "read"}
    assert d["concurrency"] == {"group": "ci-${{ github.ref }}",
                                "cancel-in-progress": True}


def test_ci_kopfpruefung_nur_bei_dispatch_und_eingabe_nur_ueber_env():
    schritte = _yaml(CI)["jobs"]["test"]["steps"]
    pruef = [s for s in schritte if "inputs.ref" in str(s.get("if", ""))]
    assert len(pruef) == 1
    s = pruef[0]
    assert "github.event_name == 'workflow_dispatch'" in s["if"]
    assert s["env"]["ERWARTET"] == "${{ inputs.ref }}"
    for schritt in schritte:
        assert "${{ inputs." not in schritt.get("run", ""), (
            "Eingaben gehören in env:, nie direkt in einen run:-Block")


def test_ci_kopfpruefung_steht_vor_den_tests():
    namen = [s.get("name", "") for s in _yaml(CI)["jobs"]["test"]["steps"]]
    assert namen.index("Head-Commit prüfen (nur workflow_dispatch)") \
        < namen.index("Run tests (offline)")


def test_sync_nur_actions_write_zusaetzlich():
    assert _yaml(SYNC)["permissions"] == {
        "contents": "write", "pull-requests": "write", "actions": "write"}


def test_sync_startet_ci_nur_auf_dem_bot_branch():
    schritte = _yaml(SYNC)["jobs"]["sync"]["steps"]
    start = [s for s in schritte if "gh workflow run" in s.get("run", "")]
    assert len(start) == 1
    run = start[0]["run"]
    assert f'BRANCH="{handover_sync.BRANCH_NAME}"' in run
    assert re.search(r'gh workflow run ci\.yml --ref "\$BRANCH"', run)
    assert "--event workflow_dispatch" in run and '--commit "$sha"' in run, (
        "ohne Prüfung auf bestehende Läufe gäbe es doppelte CI-Läufe")
    # Der Start kommt NACH dem Sync-Schritt.
    namen = [s.get("name", "") for s in schritte]
    sync_idx = next(i for i, s in enumerate(schritte)
                    if "scripts/handover_sync.py" in s.get("run", ""))
    assert namen.index(start[0]["name"]) > sync_idx


def test_sync_ruft_nie_einen_merge_auf():
    text = "\n".join(z for z in SYNC.read_text(encoding="utf-8").splitlines()
                     if not z.lstrip().startswith("#"))
    for verboten in ("gh pr merge", "--auto", "enablePullRequestAutoMerge",
                     "/merge"):
        assert verboten not in text, verboten
