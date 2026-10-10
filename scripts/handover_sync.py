#!/usr/bin/env python3
"""Handover-Sync-Bot — Weg B (Easy-Entscheid 09./10.10.2026).

Findet main-PRs, die laut `proactive_watcher.erkenne_handover_luecke`
(Klasse 7) in SESSION_HANDOVER.md fehlen, und trägt sie MECHANISCH in den
markierten Block (`MARKER_ANFANG`/`MARKER_ENDE`) ein — EIN gesammelter,
NICHT-Draft-PR je Lauf, nur wenn Lücken vorliegen. Wiederverwendet die
bestehende Extraktion (`proactive_watcher._main_pr_titel`) statt sie neu zu
erfinden.

WEG B, NICHT „Auto-Merge für Bot-PRs" (die ältere, inzwischen korrigierte
Formulierung im Handover-Eintrag vom 09.10.2026 — s. Korrektur
10.10.2026): dieses Skript merged NICHTS. Es legt den PR an bzw.
aktualisiert ihn; Easy gibt den CI-Lauf per Tap frei und mergt selbst.
Kein PAT, keine GitHub-App — ausschließlich das Standard-`GITHUB_TOKEN`.

MECHANISCH, keine KI-Bewertung (anders als `proactive_fixer.py`): fehlt der
Marker, kommt er mehrfach oder an ungewöhnlicher Stelle vor (ANFANG nicht
vor ENDE), bricht der Lauf OHNE PR ab — mit einer klaren Zeile im
Job-Summary, statt den Block zu erraten oder rot ohne erkennbaren Grund zu
laufen. Fließtext außerhalb des Blocks bleibt dabei immer byte-identisch,
auch im Erfolgsfall (siehe `baue_neuen_text`).

Idempotenz: fester Branch-Name (`BRANCH_NAME`), bei jedem Lauf frisch von
`origin/main` aufgesetzt und force-gepusht. Ein bereits offener PR auf
diesem Branch wird von GitHub automatisch mitaktualisiert — `gh pr create`
scheitert dann erwartbar mit „a pull request ... already exists", das
dieses Skript fail-soft als „aktualisiert" statt als Fehler behandelt."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import proactive_watcher as pw

MARKER_ANFANG = "<!-- AUTO-PR-INDEX-ANFANG -->"
MARKER_ENDE = "<!-- AUTO-PR-INDEX-ENDE -->"
BOT_TITEL_PRAEFIX = pw._BOT_HANDOVER_SYNC_PRAEFIX  # "chore(handover-sync):"
BRANCH_NAME = "handover-sync/auto-pr-index"


def _log(msg: str) -> None:
    print(f"[handover-sync] {msg}", flush=True)


class MarkerFehler(Exception):
    """Block-Marker fehlt, ist doppelt, oder ANFANG liegt nicht vor ENDE."""


def pruefe_marker(text: str) -> None:
    """Genau EIN ANFANG- und EIN ENDE-Marker, ANFANG strikt vor ENDE —
    sonst MarkerFehler. Keine Heuristik, kein Raten."""
    anfang_n = text.count(MARKER_ANFANG)
    ende_n = text.count(MARKER_ENDE)
    if anfang_n != 1 or ende_n != 1:
        raise MarkerFehler(
            f"Marker-Anzahl falsch: {MARKER_ANFANG!r}={anfang_n}x, "
            f"{MARKER_ENDE!r}={ende_n}x (jeweils genau 1x erwartet)."
        )
    if text.index(MARKER_ANFANG) >= text.index(MARKER_ENDE):
        raise MarkerFehler("ANFANG-Marker liegt nicht vor dem ENDE-Marker.")


def fehlende_pr_zeilen(repo_root: Path) -> List[str]:
    """Fertige Index-Zeilen ('- #N — <Commit-Subject>') für alle main-PRs,
    die in SESSION_HANDOVER.md fehlen — identische Quelle wie
    `erkenne_handover_luecke` (Klasse 7), keine eigene Extraktion."""
    handover_pfad = repo_root / "SESSION_HANDOVER.md"
    if not handover_pfad.is_file():
        return []
    main_prs = pw._main_pr_titel(repo_root)
    if not main_prs:
        return []
    handover_text = handover_pfad.read_text(encoding="utf-8")
    erwaehnte = {int(n) for n in pw._HANDOVER_PR_ERWAEHNUNG.findall(handover_text)}
    fehlende = sorted(set(main_prs) - erwaehnte)
    return [f"- #{n} — {main_prs[n]}" for n in fehlende]


def baue_neuen_text(text: str, neue_zeilen: List[str]) -> str:
    """Fügt `neue_zeilen` unmittelbar VOR dem ENDE-Marker ein. Alles
    außerhalb des Blocks — Fließtext, alte PR-Tabelle — bleibt
    byte-identisch. Wirft MarkerFehler statt zu raten."""
    pruefe_marker(text)
    einfuege_stelle = text.index(MARKER_ENDE)
    vor_marker = text[:einfuege_stelle]
    nach_marker = text[einfuege_stelle:]
    if not vor_marker.endswith("\n"):
        vor_marker += "\n"
    zusatz = "\n".join(neue_zeilen) + "\n"
    return vor_marker + zusatz + nach_marker


# ---------------------------------------------------------------------------
# Git-/GitHub-Plumbing — NUR von main() genutzt, NIE von der getesteten
# Logik oben. Fail-soft: jeder Fehler wird geloggt, bricht den Lauf nie mit
# einem unklaren Traceback ab (Job-Summary bekommt in jedem Pfad eine Zeile).
# ---------------------------------------------------------------------------
def _run(cmd: List[str], cwd: Path, env: Optional[dict] = None) -> subprocess.CompletedProcess:  # pragma: no cover
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True, env=env)


def fuehre_sync_aus(repo_root: Path, github_token: str) -> Optional[str]:  # pragma: no cover — Netz+Git, Logik oben separat getestet
    """EIN Lauf -> fester Branch -> EIN Commit -> EIN PR (nicht Draft),
    angelegt oder aktualisiert. Gibt die PR-URL zurück, oder None (keine
    Lücken / Marker-Fehler / sonstiger Fehlschlag — jeweils mit Zeile im
    Job-Summary, nie stillschweigend)."""
    try:
        neue_zeilen = fehlende_pr_zeilen(repo_root)
    except MarkerFehler as exc:
        pw.schreibe_job_summary(f"**Abbruch — Marker-Problem:** {exc}\n\nKEIN PR angelegt.")
        _log(f"Abbruch — Marker-Problem: {exc}")
        return None

    if not neue_zeilen:
        pw.schreibe_job_summary("Keine Lücken — SESSION_HANDOVER.md ist vollständig. Kein PR.")
        _log("Keine Lücken — kein PR.")
        return None

    handover_pfad = repo_root / "SESSION_HANDOVER.md"
    alter_text = handover_pfad.read_text(encoding="utf-8")
    try:
        neuer_text = baue_neuen_text(alter_text, neue_zeilen)
    except MarkerFehler as exc:
        pw.schreibe_job_summary(f"**Abbruch — Marker-Problem:** {exc}\n\nKEIN PR angelegt.")
        _log(f"Abbruch — Marker-Problem: {exc}")
        return None

    env = {**os.environ, "GH_TOKEN": github_token}
    try:
        _run(["git", "-c", "user.name=github-actions[bot]",
              "-c", "user.email=41898282+github-actions[bot]"
              "@users.noreply.github.com",
              "checkout", "-B", BRANCH_NAME, "origin/main"], repo_root)
        handover_pfad.write_text(neuer_text, encoding="utf-8")
        _run(["git", "add", "SESSION_HANDOVER.md"], repo_root)
        commit_msg = (
            f"{BOT_TITEL_PRAEFIX} {len(neue_zeilen)} Zeile(n) im "
            f"AUTO-PR-INDEX-Block ergänzt\n\n"
            f"Automatisch erzeugt (Handover-Sync-Bot, Weg B — Easy-Entscheid "
            f"09./10.10.2026). Ausschließlich der markierte Block wurde "
            f"verändert; Fließtext und alte PR-Tabelle bleiben byte-identisch."
        )
        _run(["git", "-c", "user.name=github-actions[bot]",
              "-c", "user.email=41898282+github-actions[bot]"
              "@users.noreply.github.com",
              "commit", "-m", commit_msg], repo_root)
        _run(["git", "push", "-u", "origin", BRANCH_NAME, "--force-with-lease"],
             repo_root, env=env)

        pr_titel = f"{BOT_TITEL_PRAEFIX} {len(neue_zeilen)} Zeile(n) ergänzt"
        pr_body = (
            "Automatisch erzeugter Sync-PR (Handover-Sync-Bot, Weg B — "
            "Easy-Entscheid 09./10.10.2026). **KEIN Auto-Merge:** Easy gibt "
            "den CI-Lauf per Tap frei und mergt selbst.\n\n"
            f"**Ergänzte Zeile(n) ({len(neue_zeilen)}):**\n\n"
            + "\n".join(neue_zeilen) +
            "\n\nÄndert AUSSCHLIESSLICH den markierten AUTO-PR-INDEX-Block in "
            "`SESSION_HANDOVER.md` — Fließtext und alte PR-Tabelle "
            "(`## 2. PR-INDEX #1–#153`) bleiben byte-identisch.\n\n"
            "**Fragile Annahme (offen beim ersten echten Lauf):** ob CI nach "
            "Easys Freigabe tatsächlich grün läuft, und ob die Merge-Box "
            "eine zusätzliche, per API nicht einsehbare klassische "
            "Branch-Protection-Regel meldet (Ruleset `Main`, "
            "`required_status_checks` auf `test`, ist konfiguriert aber "
            "`enforcement: disabled` — s. Diagnose 10.10.2026).\n\n"
            "**Revert:** `git revert` auf diesen PR.\n\n"
            "---\n_Generated by [Claude Code](https://claude.ai/code)_"
        )
        erstellt = subprocess.run(
            ["gh", "pr", "create", "--title", pr_titel, "--body", pr_body,
             "--base", "main", "--head", BRANCH_NAME],
            cwd=repo_root, capture_output=True, text=True, env=env,
        )
        if erstellt.returncode == 0:
            pr_url = erstellt.stdout.strip().splitlines()[-1]
            pw.schreibe_job_summary(
                f"**Neuer Sync-PR angelegt:** {pr_url}\n\n"
                f"{len(neue_zeilen)} Zeile(n) ergänzt."
            )
            _log(f"Neuer PR: {pr_url}")
            return pr_url
        if "already exists" in erstellt.stderr:
            ansicht = subprocess.run(
                ["gh", "pr", "view", BRANCH_NAME, "--json", "url", "-q", ".url"],
                cwd=repo_root, capture_output=True, text=True, env=env, check=True,
            )
            pr_url = ansicht.stdout.strip()
            pw.schreibe_job_summary(
                f"**Bestehenden Sync-PR aktualisiert:** {pr_url}\n\n"
                f"{len(neue_zeilen)} Zeile(n) ergänzt (Branch neu von main "
                f"aufgesetzt, force-gepusht)."
            )
            _log(f"Bestehenden PR aktualisiert: {pr_url}")
            return pr_url
        raise RuntimeError(f"gh pr create fehlgeschlagen: {erstellt.stderr}")
    except Exception as exc:  # noqa: BLE001 — fail-soft, nie eskalieren
        pw.schreibe_job_summary(
            f"**Fehler bei PR-Erstellung/-Aktualisierung:** "
            f"{type(exc).__name__}: {exc}"
        )
        _log(f"Fehlschlag (fail-soft): {type(exc).__name__}: {exc}")
        return None


def main() -> int:  # pragma: no cover — Orchestrierung
    repo_root = Path(__file__).resolve().parent.parent
    github_token = os.environ.get("GITHUB_TOKEN", "")
    fuehre_sync_aus(repo_root, github_token)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
