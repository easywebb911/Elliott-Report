#!/usr/bin/env python3
"""Technische Schutz-Sperre (Auftrag 3 von 6, Easy-Entscheid 24./25.10.2026).

PFLICHT VOR JEDEM SELBST MERGENDEN AGENTEN (noch nicht gebaut — diese Sperre
ist die Voraussetzung dafür). Berührt ein PR eine geschützte Zone
(`scripts/schutz_zonen.py`), ist diese Prüfung ROT — IMMER, ohne Ausnahme.

OPTION 4 (Easy-Entscheid 25.10.2026, zum Mini-Stopp aus Schritt 0 dieses
Auftrags): KEIN Freigabe-Label. Grund: Easy (iPhone) und Code/ein Agent
laufen für GitHub unter DEMSELBEN Konto (`easywebb911`) — belegt an einem
echten Beispiel (PR #199: `ready_for_review`/`merged` durch Easy UND die
PR-Erstellung durch Code zeigen denselben `actor.login`, beide
`performed_via_github_app: null`). Ein Label, das "nur Easy" setzen soll,
wäre technisch nicht von einem Agenten-Label zu unterscheiden — das wäre
falsche Sicherheit. Also: KEIN Weg zur Grünfärbung, auch nicht über Titel
oder Freigabe. Ein Titel mit "[Wächter]" bekommt im Job-Summary zusätzlich
den Hinweis "Agent: NICHT mergen, nur Easy" — reine Zusatz-Information,
macht die Prüfung NICHT grüner.

WAS DAS HEISST (Handover Abschnitt 8, s. dort): die Sperre schützt vor dem
FEHLER eines Agenten (versehentliche Änderung einer geschützten Zone),
NICHT vor einem ABSICHTLICHEN Regelbruch über dasselbe Konto — das ist eine
bewusst akzeptierte, dokumentierte Grenze (s. Moduldoc `schutz_zonen.py`
und Schritt-0b-Befund), kein Versehen.

HARTE GRENZEN: nur lesend (kein Schreibzugriff aufs Repo, kein Merge, kein
PR-Kommentar — nur `GITHUB_STEP_SUMMARY`/stdout). Braucht nur
`contents: read`; der PR-Titel kommt als CLI-Argument aus dem
Event-Payload (`github.event.pull_request.title`), NICHT aus einem API-Call
— deshalb ist `pull-requests: read` nicht nötig.

AUFRUF (durch `.github/workflows/schutz_sperre.yml`):
    python scripts/schutz_sperre.py --base <base-sha> --head <head-sha> \\
        --titel "<PR-Titel>" [--summary-datei <Pfad>]
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path
import schutz_zonen as zonen

REPO_ROOT = repo_path.REPO_ROOT

WAECHTER_TITEL_PRAEFIX = "[Wächter]"
WAECHTER_HINWEIS = "Agent: NICHT mergen, nur Easy"


class Treffer(NamedTuple):
    datei: str
    zone: str
    grund: str


def _normalisiert(pfad: str) -> str:
    """NFC-normalisiert + Vorwärts-Slashes — Abwehr einfacher Unicode-
    Normalisierungs-Tricks (verschiedene Normalform, gleiche Zeichen)."""
    p = pfad.replace("\\", "/").lstrip("/")
    return unicodedata.normalize("NFC", p)


def _datei_zone(pfad: str) -> Optional[Tuple[str, str]]:
    """(Zone, Grund) wenn ``pfad`` (ohne config.py, s. ``main``) eine
    geschützte Zone berührt, sonst ``None``. Prüft exakt UND — als Pfad-
    Trick-Abwehr — zusätzlich case-insensitive (Groß-/Kleinschreibung darf
    keinen Treffer verstecken, selbst wenn das echte Linux-Dateisystem
    case-sensitiv ist)."""
    p = _normalisiert(pfad)
    if p in zonen.GESCHUETZTE_DATEIEN:
        return "Datei-Zone", f"exakter Treffer: {p}"
    for praefix in zonen.GESCHUETZTE_VERZEICHNIS_PRAEFIXE:
        if p.startswith(praefix):
            return "Infrastruktur-Zone", f"liegt unter {praefix}"
    p_fold = p.casefold()
    for g in zonen.GESCHUETZTE_DATEIEN:
        if p != g and p_fold == g.casefold():
            return ("Datei-Zone (Groß-/Kleinschreibung)",
                    f"„{p}“ unterscheidet sich von „{g}“ nur in "
                    f"Groß-/Kleinschreibung")
    for praefix in zonen.GESCHUETZTE_VERZEICHNIS_PRAEFIXE:
        if p.startswith(praefix):
            continue
        if p_fold.startswith(praefix.casefold()):
            return ("Infrastruktur-Zone (Groß-/Kleinschreibung)",
                    f"liegt unter einer Groß-/Kleinschreibungs-Variante von "
                    f"{praefix}")
    return None


class DiffEintrag(NamedTuple):
    status: str
    pfad: str
    alter_pfad: Optional[str]  # gesetzt bei Rename/Copy


def diff_dateien(base_sha: str, head_sha: str,
                 repo_root: Path = REPO_ROOT) -> List[DiffEintrag]:
    """Geänderte Dateien gegen die Merge-Basis (``git diff base...head`` —
    Drei-Punkt, also gegen den tatsächlichen Merge-Basis-Commit, nicht nur
    gegen den aktuellen Stand von ``base``). Rename-/Copy-Erkennung an, damit
    ein Umbenennen/Verschieben einer geschützten Datei nicht als simples
    Löschen+Neuanlegen an einem unverdächtigen Pfad durchrutscht."""
    out = subprocess.run(
        ["git", "diff", "--no-color", "--find-renames", "--find-copies",
         "--name-status", f"{base_sha}...{head_sha}"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout
    eintraege: List[DiffEintrag] = []
    for zeile in out.splitlines():
        if not zeile.strip():
            continue
        teile = zeile.split("\t")
        status = teile[0]
        if status[0] in ("R", "C") and len(teile) >= 3:
            eintraege.append(DiffEintrag(status, teile[2], teile[1]))
        else:
            eintraege.append(DiffEintrag(status, teile[1], None))
    return eintraege


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _geaenderte_zeilen(base_sha: str, head_sha: str, pfad: str,
                       repo_root: Path = REPO_ROOT
                       ) -> Tuple[Set[int], Set[int]]:
    """(alte_zeilen, neue_zeilen) — je die Zeilennummern, die der Diff für
    ``pfad`` als geändert ausweist (``-U0``: minimaler Kontext, exakte
    Hunk-Grenzen, keine unveränderten Nachbarzeilen mitgezählt)."""
    out = subprocess.run(
        ["git", "diff", "--no-color", "-U0", f"{base_sha}...{head_sha}",
         "--", pfad],
        cwd=repo_root, capture_output=True, text=True, check=True,
    ).stdout
    alt: Set[int] = set()
    neu: Set[int] = set()
    for zeile in out.splitlines():
        m = _HUNK_RE.match(zeile)
        if not m:
            continue
        alt_start, alt_len = int(m.group(1)), int(m.group(2) or 1)
        neu_start, neu_len = int(m.group(3)), int(m.group(4) or 1)
        if alt_len:
            alt.update(range(alt_start, alt_start + alt_len))
        if neu_len:
            neu.update(range(neu_start, neu_start + neu_len))
    return alt, neu


def _konstanten_zeilen(quelltext: str,
                       namen: frozenset) -> Dict[str, List[Tuple[int, int]]]:
    """Zeilen-Spannen (start, end, inklusiv) JEDER Top-Level-Anweisung, die
    einen Namen aus ``namen`` IRGENDWIE referenziert — per AST, nicht per
    Text-Muster (ein mehrzeiliges Dict-Literal wiederholt den Konstanten-
    Namen nicht in jeder geänderten Zeile; ein Textmuster würde solche
    Treffer verfehlen).

    BEWUSST NICHT auf ``NAME = ...``-Zuweisungen beschränkt (Guardian-Fund,
    Auftrag 3 von 6, Zweitblick vor Ready): ``SCORE_WEIGHTS["a"] = 999``,
    ``SCORE_WEIGHTS.update(...)``, ``TOP_N += 1`` oder auch nur ein Lesen
    (``x = SCORE_WEIGHTS["a"]``) laufen alle über einen ``ast.Name``-Knoten
    irgendwo im Teilbaum der Top-Level-Anweisung — ``ast.walk`` findet das,
    eine reine Ziel-Prüfung (``Assign.targets``) nicht. Ein bloßes Lesen als
    Treffer zu werten ist großzügiger als nötig, aber bewusst so: „bei
    Unklarheit: ja" (wie an anderer Stelle im Projekt), und Lesen vs.
    Schreiben zuverlässig zu trennen wäre an dieser Stelle selbst wieder
    umgehbar. ``import``/``from … import``-Anweisungen werden zusätzlich
    separat geprüft (``ast.alias.name``/``asname`` stehen nicht als
    ``ast.Name``, sondern als Strings im Baum)."""
    baum = ast.parse(quelltext)
    spannen: Dict[str, List[Tuple[int, int]]] = {}
    for knoten in ast.iter_child_nodes(baum):
        gefunden: Set[str] = {
            n.id for n in ast.walk(knoten)
            if isinstance(n, ast.Name) and n.id in namen
        }
        if isinstance(knoten, (ast.Import, ast.ImportFrom)):
            for alias in knoten.names:
                bezeichner = alias.asname or alias.name
                if bezeichner in namen:
                    gefunden.add(bezeichner)
        if not gefunden:
            continue
        ende = getattr(knoten, "end_lineno", knoten.lineno)
        for name in gefunden:
            spannen.setdefault(name, []).append((knoten.lineno, ende))
    return spannen


def config_konstanten_treffer(base_sha: str, head_sha: str,
                              alter_pfad: Optional[str],
                              neuer_pfad: Optional[str],
                              repo_root: Path = REPO_ROOT) -> List[str]:
    """Welche ``GESCHUETZTE_CONFIG_KONSTANTEN`` im Diff von config.py
    tatsächlich berührt wurden — Zeilen-Diff ``∩`` AST-Zeilen-Spanne, auf
    ALTEM und NEUEM Stand (eine gelöschte Konstante ist nur auf dem alten
    Stand sichtbar, eine neu hinzugefügte nur auf dem neuen).

    Fail-soft in die SICHERE Richtung: kann eine Seite nicht geparst werden
    (Syntaxfehler, Datei fehlt), gilt das als Treffer auf ALLE geschützten
    Konstanten (,,bei Unklarheit: ja`` — Default der bestehenden
    Wächter-Logik, hier bewusst übernommen)."""
    alte_zeilen, neue_zeilen = _geaenderte_zeilen(
        base_sha, head_sha, neuer_pfad or alter_pfad or zonen.CONFIG_DATEI,
        repo_root)
    treffer: Set[str] = set()

    def _pruefe(rev: str, pfad: Optional[str], geaenderte: Set[int]) -> None:
        if pfad is None:
            return
        try:
            text = subprocess.run(
                ["git", "show", f"{rev}:{pfad}"], cwd=repo_root,
                capture_output=True, text=True, check=True,
            ).stdout
            spannen = _konstanten_zeilen(text, zonen.GESCHUETZTE_CONFIG_KONSTANTEN)
        except (subprocess.CalledProcessError, SyntaxError):
            treffer.update(zonen.GESCHUETZTE_CONFIG_KONSTANTEN)
            return
        for name, bereiche in spannen.items():
            if any(start <= z <= ende for (start, ende) in bereiche
                  for z in geaenderte):
                treffer.add(name)

    _pruefe(base_sha, alter_pfad, alte_zeilen)
    _pruefe(head_sha, neuer_pfad, neue_zeilen)
    return sorted(treffer)


def pruefe(base_sha: str, head_sha: str,
          repo_root: Path = REPO_ROOT) -> List[Treffer]:
    """Alle Zonen-Treffer für diesen PR-Diff. Reine Funktion (bis auf die
    `git`-Subprozess-Aufrufe) — deterministisch für denselben Diff."""
    treffer: List[Treffer] = []
    eintraege = diff_dateien(base_sha, head_sha, repo_root)
    config_eintrag: Optional[DiffEintrag] = None

    for e in eintraege:
        pfade_mit_markierung = [(e.pfad, "")]
        if e.alter_pfad is not None:
            pfade_mit_markierung.append((e.alter_pfad, " (alter Pfad)"))
        beruehrt_config = False
        for pfad, markierung in pfade_mit_markierung:
            if _normalisiert(pfad) == zonen.CONFIG_DATEI:
                beruehrt_config = True
                continue
            zone = _datei_zone(pfad)
            if zone:
                name, grund = zone
                treffer.append(Treffer(
                    datei=pfad, zone=name,
                    grund=f"{grund} (Diff-Status {e.status}{markierung})"))
        if beruehrt_config:
            config_eintrag = e

    if config_eintrag is not None:
        status = config_eintrag.status
        if status[0] in ("R", "C"):
            # Umbenennen/Kopieren von config.py selbst: unabhängig vom
            # Konstanten-Inhalt immer ein Treffer (die Datei-Identität
            # ändert sich, eine Konstanten-Spannen-Prüfung wäre hier nicht
            # aussagekräftig).
            treffer.append(Treffer(
                datei=zonen.CONFIG_DATEI, zone="config.py (Struktur)",
                grund=f"Diff-Status {status} — Umbenennen/Kopieren von "
                      f"config.py selbst ist immer ein Treffer"))
        elif status == "D":
            treffer.append(Treffer(
                datei=zonen.CONFIG_DATEI, zone="config.py (Struktur)",
                grund="config.py wurde gelöscht — immer ein Treffer"))
        else:
            alter_pfad = None if status == "A" else zonen.CONFIG_DATEI
            namen = config_konstanten_treffer(
                base_sha, head_sha, alter_pfad=alter_pfad,
                neuer_pfad=zonen.CONFIG_DATEI, repo_root=repo_root)
            for name in namen:
                treffer.append(Treffer(
                    datei=zonen.CONFIG_DATEI, zone="config.py (Symbol-Ebene)",
                    grund=f"geschützte Konstante {name} im Diff berührt"))

    return treffer


def bericht(treffer: Sequence[Treffer], titel: str) -> str:
    zeilen = ["# Schutz-Sperre", ""]
    ist_waechter = titel.strip().startswith(WAECHTER_TITEL_PRAEFIX)
    if not treffer:
        zeilen.append("Keine geschützte Zone berührt. ✅")
        return "\n".join(zeilen)
    zeilen.append(f"**{len(treffer)} Zonen-Treffer — Prüfung ROT.** Kein "
                 f"Label, kein Titel, keine Freigabe macht diese Prüfung "
                 f"grün (s. Moduldoc `scripts/schutz_sperre.py`).")
    if ist_waechter:
        zeilen.append(f"\n**{WAECHTER_HINWEIS}** (Titel beginnt mit "
                      f"„{WAECHTER_TITEL_PRAEFIX}“).")
    zeilen.append("\n| Datei | Zone | Grund |")
    zeilen.append("|---|---|---|")
    for t in sorted(treffer, key=lambda x: (x.datei, x.zone)):
        zeilen.append(f"| `{t.datei}` | {t.zone} | {t.grund} |")
    return "\n".join(zeilen)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="Merge-Basis-SHA des PR.")
    ap.add_argument("--head", required=True, help="Head-SHA des PR.")
    ap.add_argument("--titel", default="", help="PR-Titel aus dem Event-"
                    "Payload (kein API-Call nötig).")
    ap.add_argument("--summary-datei", default=None,
                    help="Zusätzlich die Job-Zusammenfassung hier anhängen "
                         "(z. B. $GITHUB_STEP_SUMMARY).")
    args = ap.parse_args(argv)

    treffer = pruefe(args.base, args.head, repo_root=REPO_ROOT)
    text = bericht(treffer, args.titel)
    print(text)
    if args.summary_datei:
        with open(args.summary_datei, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    return 1 if treffer else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
