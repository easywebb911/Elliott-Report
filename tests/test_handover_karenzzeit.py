"""Karenzzeit für die Handover-Lücken-Erkennung (Easy-Entscheid 19.10.2026,
Folgeauftrag). Ohne Karenz meldet sich fast jeder frisch gemergte PR selbst
als Lücke (er kann seine eigene Nummer erst NACH dem Anlegen im Handover
nennen, nachgetragen im selben PR) und löst einen Bot-PR aus, den Easy
wegklicken muss (Muster #187, #190).

Eine PR-Nummer gilt nur als Lücke, wenn ihr Merge-Commit ÄLTER als
`pw.KARENZ_TAGE` ist (strikter Vergleich — der Grenzfall GENAU KARENZ_TAGE
alt ist noch geschützt). `erkenne_handover_luecke` (Wächter) UND
`handover_sync.fehlende_pr_zeilen` (Bot) teilen dafür EINE Funktion
(`pw._main_pr_luecken`), damit beide exakt dieselbe Lücken-Menge sehen.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import proactive_watcher as pw  # noqa: E402
import handover_sync as hs  # noqa: E402


def _git_repo_mit_commits(repo_pfad, commit_subjects):
    """Baut ein Mini-Git-Repo mit leeren Commits — nur die Subject-Zeile
    (und das reale Commit-Datum) zählen für den Detektor. Die Commits
    entstehen zur echten „jetzt"-Zeit; die Grenzfälle unten verschieben
    stattdessen die injizierte `jetzt`-Zeit relativ zum tatsächlichen
    Commit-Zeitstempel (per `pw._main_pr_commits` ausgelesen) — robuster
    als ein Offset gegen die Wanduhr, da Subprocess-Laufzeiten keine Rolle
    spielen."""
    subprocess.run(["git", "init", "-q"], cwd=repo_pfad, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"],
                    cwd=repo_pfad, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_pfad, check=True)
    for subject in commit_subjects:
        subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", subject],
                        cwd=repo_pfad, check=True)


def _commit_zeit(repo_pfad, pr_nummer: int) -> datetime:
    commits = pw._main_pr_commits(repo_pfad)
    return commits[pr_nummer][1]


# ---------------------------------------------------------------------------
# 1) Grenzfälle bei injizierter Zeit (Auftrag: 2 Tage / genau 3 Tage / 4 Tage)
# ---------------------------------------------------------------------------
def test_merge_vor_zwei_tagen_wird_nicht_gemeldet(tmp_path):
    _git_repo_mit_commits(tmp_path, ("Initial commit", "Merge pull request #50 from x/y"))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Noch nichts erwähnt.\n", encoding="utf-8")
    t0 = _commit_zeit(tmp_path, 50)
    jetzt = t0 + timedelta(days=2)
    assert pw.erkenne_handover_luecke(tmp_path, jetzt=jetzt) == []
    assert pw._main_pr_luecken(tmp_path, jetzt=jetzt) == []


def test_merge_genau_drei_tage_alt_ist_grenzfall_noch_geschuetzt(tmp_path):
    """Grenzfall (Auftrag: „Verhalten festlegen und testen"): GENAU
    KARENZ_TAGE alt ist noch NICHT „älter als" — strikter Vergleich, der
    Commit bleibt geschützt."""
    _git_repo_mit_commits(tmp_path, ("Initial commit", "Merge pull request #51 from x/y"))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Noch nichts erwähnt.\n", encoding="utf-8")
    t0 = _commit_zeit(tmp_path, 51)
    jetzt = t0 + timedelta(days=pw.KARENZ_TAGE)
    assert pw.erkenne_handover_luecke(tmp_path, jetzt=jetzt) == []
    assert pw._main_pr_luecken(tmp_path, jetzt=jetzt) == []


def test_merge_knapp_ueber_drei_tagen_wird_gemeldet(tmp_path):
    _git_repo_mit_commits(tmp_path, ("Initial commit", "Merge pull request #52 from x/y"))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Noch nichts erwähnt.\n", encoding="utf-8")
    t0 = _commit_zeit(tmp_path, 52)
    jetzt = t0 + timedelta(days=pw.KARENZ_TAGE, seconds=1)
    funde = pw.erkenne_handover_luecke(tmp_path, jetzt=jetzt)
    assert len(funde) == 1
    assert "#52" in funde[0].beschreibung
    assert pw._main_pr_luecken(tmp_path, jetzt=jetzt) == [52]


def test_merge_vor_vier_tagen_wird_gemeldet(tmp_path):
    _git_repo_mit_commits(tmp_path, ("Initial commit", "Merge pull request #53 from x/y"))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Noch nichts erwähnt.\n", encoding="utf-8")
    t0 = _commit_zeit(tmp_path, 53)
    jetzt = t0 + timedelta(days=4)
    funde = pw.erkenne_handover_luecke(tmp_path, jetzt=jetzt)
    assert len(funde) == 1
    assert "#53" in funde[0].beschreibung


def test_pr_im_handover_erwaehnt_wird_nie_gemeldet_auch_nicht_nach_jahren(tmp_path):
    """Die Karenzzeit ist eine zusätzliche Schutzfrist, KEIN Ersatz für die
    Erwähnungs-Prüfung — ein im Handover genannter PR bleibt für immer
    abgedeckt, egal wie alt sein Merge-Commit ist."""
    _git_repo_mit_commits(tmp_path, ("Initial commit", "Merge pull request #54 from x/y"))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Stand nach PR #54.\n", encoding="utf-8")
    t0 = _commit_zeit(tmp_path, 54)
    jetzt_weit_in_der_zukunft = t0 + timedelta(days=3650)
    assert pw.erkenne_handover_luecke(tmp_path, jetzt=jetzt_weit_in_der_zukunft) == []


def test_bot_pr_titel_bleibt_ausgeschlossen_unabhaengig_vom_alter(tmp_path):
    """Der Bot-PR-Ausschluss (`_BOT_HANDOVER_SYNC_PRAEFIX`) wirkt bereits in
    `_main_pr_commits`, VOR der Karenz-Prüfung — unabhängig vom injizierten
    Alter nie ein Fund."""
    _git_repo_mit_commits(tmp_path, (
        "Initial commit",
        "chore(handover-sync): 1 Zeile(n) im AUTO-PR-INDEX-Block ergänzt (#55)",
    ))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Nichts erwähnt.\n", encoding="utf-8")
    jetzt = datetime.now(timezone.utc) + timedelta(days=3650)
    assert pw.erkenne_handover_luecke(tmp_path, jetzt=jetzt) == []
    assert 55 not in pw._main_pr_commits(tmp_path)


# ---------------------------------------------------------------------------
# 2) Wächter und Bot teilen dieselbe Funktion (EXZELLENZ Punkt 6)
# ---------------------------------------------------------------------------
def test_waechter_und_bot_sehen_dieselbe_luecken_menge(tmp_path):
    _git_repo_mit_commits(tmp_path, (
        "Initial commit",
        "Merge pull request #60 from x/a",
        "Merge pull request #61 from x/b",
    ))
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        "<!-- AUTO-PR-INDEX-ANFANG -->\n- #60 — erwähnt\n<!-- AUTO-PR-INDEX-ENDE -->\n",
        encoding="utf-8",
    )
    t0 = _commit_zeit(tmp_path, 61)
    jetzt = t0 + timedelta(days=pw.KARENZ_TAGE, seconds=1)

    waechter_funde = pw.erkenne_handover_luecke(tmp_path, jetzt=jetzt)
    bot_zeilen = hs.fehlende_pr_zeilen(tmp_path, jetzt=jetzt)

    assert len(waechter_funde) == 1
    assert "#61" in waechter_funde[0].beschreibung
    assert "#60" not in waechter_funde[0].beschreibung
    assert bot_zeilen == ["- #61 — Merge pull request #61 from x/b"]


# ---------------------------------------------------------------------------
# 3) Mutationsproben — Karenz entfernt / Operator gedreht muss rot werden
# ---------------------------------------------------------------------------
def test_mutationsprobe_ohne_karenz_waere_frischer_pr_sofort_gemeldet(tmp_path):
    """Simuliert die Fassung VOR diesem Auftrag (keine Karenz-Prüfung): ein
    frischer PR (Commit vor 1 Minute) würde sofort gemeldet. Die ECHTE
    Funktion mit Karenz meldet ihn NICHT — der Unterschied belegt, dass die
    Karenzzeit tatsächlich etwas verhindert, nicht nur Code ist, der nie
    greift."""
    _git_repo_mit_commits(tmp_path, ("Initial commit", "Merge pull request #70 from x/y"))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Nichts erwähnt.\n", encoding="utf-8")

    commits = pw._main_pr_commits(tmp_path)
    erwaehnte = set()  # Handover-Text erwähnt nichts
    ohne_karenz_fehlende = sorted(n for n in commits if n not in erwaehnte)
    assert ohne_karenz_fehlende == [70]  # die alte, karenzlose Logik würde melden

    # Die ECHTE Funktion (mit Karenz, `jetzt` ~= echte Erstellzeit) meldet
    # denselben frischen PR NICHT.
    assert pw._main_pr_luecken(tmp_path) == []


def test_mutationsprobe_operator_gedreht_waere_grenzfall_falsch(tmp_path):
    """Dreht den Vergleich im Produktionscode NICHT — sondern beweist am
    Grenzfall (genau KARENZ_TAGE alt), dass `<=` (geschützt) und nicht `<`
    (bereits eine Lücke) gilt. Eine Fassung mit `<` statt `<=` würde hier
    fälschlich einen Fund liefern; die ECHTE Funktion liefert keinen."""
    _git_repo_mit_commits(tmp_path, ("Initial commit", "Merge pull request #71 from x/y"))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Nichts erwähnt.\n", encoding="utf-8")
    t0 = _commit_zeit(tmp_path, 71)
    jetzt = t0 + timedelta(days=pw.KARENZ_TAGE)

    # Nachbau der gedrehten (kaputten) Bedingung: `<` statt `<=`.
    alter = jetzt - t0
    kaputt_waere_geschuetzt = alter < timedelta(days=pw.KARENZ_TAGE)
    assert kaputt_waere_geschuetzt is False  # die Mutante würde hier melden

    # Die ECHTE Funktion: am Grenzfall weiterhin geschützt (`<=`).
    assert pw._main_pr_luecken(tmp_path, jetzt=jetzt) == []
