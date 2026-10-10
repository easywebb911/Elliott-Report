"""Handover-Sync-Bot (Weg B, 09./10.10.2026) — Marker-Prüfung, Block-Einfügung
und Wiederverwendung der Klasse-7-Extraktion. Reine Werttests gegen
synthetische SESSION_HANDOVER.md-Inhalte und Mini-Git-Repos — kein Netz,
kein echter PR-Aufruf (die Git-/GitHub-Plumbing in `fuehre_sync_aus` ist
bewusst `pragma: no cover`, wie `proactive_fixer.wende_fix_an_und_erstelle_pr`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import handover_sync as hs  # noqa: E402


def _git_repo_mit_commits(repo_pfad, commit_subjects):
    subprocess.run(["git", "init", "-q"], cwd=repo_pfad, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"],
                    cwd=repo_pfad, check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                    cwd=repo_pfad, check=True)
    for subject in commit_subjects:
        subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", subject],
                        cwd=repo_pfad, check=True)


_HISTORIE = (
    "Initial commit",
    "Merge pull request #10 from x/feature-a",
    "feat(x): irgendein Fix (#11)",
)


# ---------------------------------------------------------------------------
# 1) Marker-Prüfung (`pruefe_marker`) — normal, fehlt, doppelt, vertauscht
# ---------------------------------------------------------------------------
def test_marker_normal_ist_ok():
    text = "Text davor.\n<!-- AUTO-PR-INDEX-ANFANG -->\n<!-- AUTO-PR-INDEX-ENDE -->\nText danach.\n"
    hs.pruefe_marker(text)  # wirft nicht


def test_marker_fehlt_komplett():
    text = "Kein Marker hier, nur Fließtext.\n"
    try:
        hs.pruefe_marker(text)
        assert False, "MarkerFehler erwartet"
    except hs.MarkerFehler:
        pass


def test_marker_anfang_fehlt_ende_vorhanden():
    text = "Text.\n<!-- AUTO-PR-INDEX-ENDE -->\n"
    try:
        hs.pruefe_marker(text)
        assert False, "MarkerFehler erwartet"
    except hs.MarkerFehler:
        pass


def test_marker_doppelt():
    text = (
        "<!-- AUTO-PR-INDEX-ANFANG -->\n"
        "<!-- AUTO-PR-INDEX-ENDE -->\n"
        "<!-- AUTO-PR-INDEX-ANFANG -->\n"
        "<!-- AUTO-PR-INDEX-ENDE -->\n"
    )
    try:
        hs.pruefe_marker(text)
        assert False, "MarkerFehler erwartet"
    except hs.MarkerFehler:
        pass


def test_marker_an_ungewoehnlicher_stelle_ende_vor_anfang():
    """ENDE steht VOR ANFANG — z. B. durch eine versehentliche
    Umsortierung mitten im Fließtext. Muss erkannt werden, nicht nur die
    reine Anzahl."""
    text = (
        "Fließtext oben.\n<!-- AUTO-PR-INDEX-ENDE -->\n"
        "mehr Fließtext mittendrin\n<!-- AUTO-PR-INDEX-ANFANG -->\nunten.\n"
    )
    try:
        hs.pruefe_marker(text)
        assert False, "MarkerFehler erwartet"
    except hs.MarkerFehler:
        pass


def test_marker_leerer_block_ist_ok():
    """Ein leerer Block (direkt aufeinanderfolgende Marker) ist ein
    gültiger Ausgangszustand — noch keine Zeile ergänzt, kein Fehler."""
    text = "<!-- AUTO-PR-INDEX-ANFANG -->\n<!-- AUTO-PR-INDEX-ENDE -->\n"
    hs.pruefe_marker(text)  # wirft nicht


# ---------------------------------------------------------------------------
# 2) `baue_neuen_text` — Einfügung bleibt außerhalb des Blocks byte-identisch
# ---------------------------------------------------------------------------
def test_baue_neuen_text_fuegt_vor_ende_marker_ein():
    text = (
        "Fließtext VOR dem Block — unberührt.\n"
        "<!-- AUTO-PR-INDEX-ANFANG -->\n"
        "<!-- AUTO-PR-INDEX-ENDE -->\n"
        "Fließtext NACH dem Block — unberührt.\n"
    )
    neu = hs.baue_neuen_text(text, ["- #12 — Merge pull request #12 from x/y"])
    assert "Fließtext VOR dem Block — unberührt.\n" in neu
    assert "Fließtext NACH dem Block — unberührt.\n" in neu
    assert "- #12 — Merge pull request #12 from x/y" in neu
    # Reihenfolge: neue Zeile liegt zwischen ANFANG und ENDE.
    anfang_pos = neu.index(hs.MARKER_ANFANG)
    ende_pos = neu.index(hs.MARKER_ENDE)
    zeile_pos = neu.index("- #12")
    assert anfang_pos < zeile_pos < ende_pos


def test_baue_neuen_text_mit_bereits_vorhandenen_zeilen_haengt_an():
    text = (
        "<!-- AUTO-PR-INDEX-ANFANG -->\n"
        "- #10 — Merge pull request #10 from x/feature-a\n"
        "<!-- AUTO-PR-INDEX-ENDE -->\n"
    )
    neu = hs.baue_neuen_text(text, ["- #11 — feat(x): irgendein Fix (#11)"])
    assert "- #10 — Merge pull request #10 from x/feature-a" in neu
    assert "- #11 — feat(x): irgendein Fix (#11)" in neu
    assert neu.index("#10") < neu.index("#11")


def test_baue_neuen_text_wirft_bei_fehlendem_marker():
    try:
        hs.baue_neuen_text("Kein Marker.\n", ["- #1 — egal"])
        assert False, "MarkerFehler erwartet"
    except hs.MarkerFehler:
        pass


# --- Mutationsproben: Marker-Prüfung aus dem Pfad entfernt -> rot ---------
def test_mutationsprobe_ohne_marker_pruefung_waere_fund_falsch():
    """Simuliert eine kaputte Fassung, die `pruefe_marker` NICHT aufruft
    und blind vor dem ERSTEN Marker-Vorkommen einfügt: landet FALSCH, wenn
    (wie hier) ENDE vor ANFANG steht — der Test schlägt dann fehl, genau
    das Verhalten, das die echte `baue_neuen_text` (MIT Prüfung) verhindert."""
    text = (
        "<!-- AUTO-PR-INDEX-ENDE -->\nMitte\n<!-- AUTO-PR-INDEX-ANFANG -->\n"
    )

    def kaputte_variante_ohne_pruefung(text, neue_zeilen):
        stelle = text.index(hs.MARKER_ENDE)  # kein pruefe_marker() davor
        return text[:stelle] + "\n".join(neue_zeilen) + "\n" + text[stelle:]

    kaputt = kaputte_variante_ohne_pruefung(text, ["- #1 — egal"])
    assert kaputt.index("- #1") < kaputt.index(hs.MARKER_ANFANG)  # falsch einsortiert

    try:
        hs.baue_neuen_text(text, ["- #1 — egal"])
        assert False, "die ECHTE Funktion muss hier MarkerFehler werfen"
    except hs.MarkerFehler:
        pass


def test_mutationsprobe_marker_anzahl_pruefung_entfernt():
    """Simuliert eine Fassung, die nur noch auf Vorhandensein, NICHT mehr
    auf Anzahl prüft: ein doppelter ANFANG-Marker würde unbemerkt
    durchgehen. Die echte `pruefe_marker` muss das abfangen."""
    text = (
        "<!-- AUTO-PR-INDEX-ANFANG -->\n"
        "<!-- AUTO-PR-INDEX-ANFANG -->\n"
        "<!-- AUTO-PR-INDEX-ENDE -->\n"
    )

    def kaputte_pruefung_nur_vorhanden(text):
        if hs.MARKER_ANFANG not in text or hs.MARKER_ENDE not in text:
            raise hs.MarkerFehler("fehlt")
        # KEINE Anzahl-Prüfung -> würde hier fälschlich durchgehen

    kaputte_pruefung_nur_vorhanden(text)  # wirft NICHT — das ist der Defekt

    try:
        hs.pruefe_marker(text)
        assert False, "die ECHTE Prüfung muss den doppelten Marker erkennen"
    except hs.MarkerFehler:
        pass


# ---------------------------------------------------------------------------
# 3) `fehlende_pr_zeilen` — Wiederverwendung der Klasse-7-Extraktion
# ---------------------------------------------------------------------------
def test_fehlende_pr_zeilen_nutzt_main_pr_titel(tmp_path):
    _git_repo_mit_commits(tmp_path, _HISTORIE)
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        "Stand nach PR #10 — im PR-Index erwähnt.\n", encoding="utf-8",
    )
    zeilen = hs.fehlende_pr_zeilen(tmp_path)
    assert zeilen == ["- #11 — feat(x): irgendein Fix (#11)"]


def test_fehlende_pr_zeilen_leer_wenn_alles_erwaehnt(tmp_path):
    _git_repo_mit_commits(tmp_path, _HISTORIE)
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        "Stand nach PR #10 und #11.\n", encoding="utf-8",
    )
    assert hs.fehlende_pr_zeilen(tmp_path) == []


def test_fehlende_pr_zeilen_ohne_handover_datei(tmp_path):
    _git_repo_mit_commits(tmp_path, _HISTORIE)
    assert hs.fehlende_pr_zeilen(tmp_path) == []
