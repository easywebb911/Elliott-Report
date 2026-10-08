#!/usr/bin/env python3
"""Cluster-Sensitivität der AUC — Umsetzung der Registry-Regel „Cluster-
Sensitivität der AUC ab der nächsten offiziellen Auswertung" (08.10.2026,
#166, docs/validation_registry.md, Abschnitt „Regeln (nicht verhandelbar)").

HARTE GRENZEN (wie evaluate.py, Zeile für Zeile übernommen)
  - läuft **nie** im Tageslauf (kein Aufruf in `.github/workflows/`, kein
    Import aus `elliott_pipeline`/`notify`/`health_check` — per Test
    abgesichert),
  - sendet **keinen** Push,
  - schreibt **nie** in `forward_collection.json`, **nie** in `report.json`
    und **nie** in `docs/validation_registry.md` oder `scripts/evaluate.py`
    (per Test abgesichert) — Ausgabe NUR auf die Konsole, optional zusätzlich
    in eine vom Aufrufer per `--out` benannte Datei,
  - läuft **nur auf Anfrage**, nie automatisch.

WAS DIESES SKRIPT TUT (und was nicht)
  Berichtet genau VIER AUC-Bootstrap-Untergrenzen, einzeln benannt:
  „primär (a)", „Tag-Block (a)", „Ticker-Block (a)", „primär (b)". Die
  beiden Cluster-Varianten (Tag-Block/Ticker-Block) werden laut Regel NUR
  auf Population (a) gerechnet, NIE auf (b) — hier bewusst eingehalten,
  nicht nur behauptet (s. `_VIER_NAMEN` unten und `bericht()`).

  Die Trefferquote (Zufalls-Benchmark) wird hier **nicht** berechnet — sie
  ist nicht Teil dieser Regel. Das Skript weist das im Bericht explizit aus,
  statt es wegzulassen (sonst sähe es wie ein Versehen aus).

  Population (a)/(b): WIEDERVERWENDET, nicht nachgebaut. (a) = `evaluate.
  build_population(coll)` auf der unveränderten Sammlung. (b) = dieselbe
  Funktion auf der Sammlung NACH `filter_sensitivity_sammlung.filtere()`
  (entfernt Records mit mindestens einem der drei Qualitäts-Marker) — exakt
  der Mechanismus, den auch `evaluate.py --sammlung
  data/forward_collection_sensitivity.json` nutzen würde, hier nur ohne die
  Zwischendatei (beide Funktionen sind reine, lesende Funktionen, s. Modul-
  Kommentare dort).

  n < EVAL_MIN_N (Population (a)): das Skript **verweigert**, exakt wie
  `evaluate.py::run()` ohne `--vorschau` (dasselbe `EVAL_MIN_N` aus
  `forward_collection.py`, hier importiert, nicht kopiert).

FESTE PARAMETER (Konstanten unten, datiert 08.10.2026, aus der Registry-
Regel #166 übernommen — KEINE eigene neue Entscheidung dieses Skripts):
  10.000 Ziehungen, CI-Niveau 0,975, fünf feste Seeds
  (20260728, 1, 42, 7, 999).

PERZENTIL-KONVENTION: exakt wie `evaluate.py::auc_test`/`_quantil`
(Zeilen 312–316 und 344–366, Stand 08.10.2026) — hier nicht reimplementiert,
sondern importiert (`evaluate._quantil`, `evaluate.auc`), damit kein
Drift zwischen beiden Rechnungen entstehen kann.

KEIN Kalender/Handelstage-Bezug: der Tag-Block-Key ist das ROHE
`first_seen_date`-Feld des Records (ein Kalendertag-String), der Ticker-
Block-Key das rohe `ticker`-Feld — keine `market_calendar`-Funktion im
Spiel, identisch zur Diagnose vom 03.10.2026 (#164), deren Zahlen dieses
Skript reproduzieren soll (s. Registry-Nachtrag/PR-Text für den Abgleich).

VERWENDUNG (nur manuell):
  python scripts/evaluate_cluster_sensitivity.py
      [--sammlung data/forward_collection.json] [--out DATEI]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path

REPO_ROOT = repo_path.REPO_ROOT

import evaluate as ev  # noqa: E402 — NUR LESEND genutzt, s. Moduldoc oben
import filter_sensitivity_sammlung as fss  # noqa: E402 — dito, nur `filtere()`
import forward_collection as fc  # noqa: E402

# ---------------------------------------------------------------------------
# Feste Parameter (08.10.2026, Registry-Regel #166 — keine eigene Wahl).
# ---------------------------------------------------------------------------
BOOTSTRAP_DRAWS = 10_000
CI_NIVEAU = 0.975
SEEDS = (20260728, 1, 42, 7, 999)
EVAL_MIN_N = fc.EVAL_MIN_N

# Verbotene Ausgabe-Ziele (harte Grenze: nie in Sammlung/Report/Registry/
# evaluate.py schreiben, auch nicht versehentlich über --out).
_VERBOTENE_ZIELE = (
    "data/forward_collection.json",
    "data/forward_collection_sensitivity.json",
    "data/report.json",
    "docs/validation_registry.md",
    "scripts/evaluate.py",
)

# Die vier benannten Berichts-Zeilen, FESTE Reihenfolge (Registry-Regel).
_VIER_NAMEN = ("primär (a)", "Tag-Block (a)", "Ticker-Block (a)", "primär (b)")


def _bloecke(cases: Sequence[Dict], feld: str) -> Dict[str, List[Dict]]:
    """Reine Gruppierungsfunktion: Block-Key = roher Feldwert (first_seen_date
    oder ticker), KEINE Kalenderfunktion. Jeder Fall gehört zu genau einem
    Block."""
    out: Dict[str, List[Dict]] = defaultdict(list)
    for c in cases:
        out[c[feld]].append(c)
    return dict(out)


def _resample_scores_labels(bloecke: Dict[str, List[Dict]],
                            gezogene_keys: Sequence[str]
                            ) -> Tuple[List[float], List[int]]:
    """Baut (scores, labels) aus EINER Ziehung von Block-Keys. Jeder gezogene
    Block geht VOLLSTÄNDIG (alle seine Fälle) in die Stichprobe ein — nie nur
    ein Teil davon."""
    scores: List[float] = []
    labels: List[int] = []
    for key in gezogene_keys:
        for c in bloecke[key]:
            scores.append(c["score"])
            labels.append(c["hit"])
    return scores, labels


def bootstrap_ci(cases: Sequence[Dict], block_feld: Optional[str], seed: int,
                 *, bootstrap: int = BOOTSTRAP_DRAWS,
                 ci_level: float = CI_NIVEAU) -> Dict:
    """Block-Bootstrap der AUC. ``block_feld=None`` → fallweise (primär,
    identisch zu `evaluate.auc_test`s Ziehungslogik). Sonst: Block-Bootstrap
    über den rohen Feldwert.

    Perzentil-Konvention EXAKT wie `evaluate.py::auc_test`/`_quantil`
    (Zeilen 312–316, 344–366) — importiert, nicht reimplementiert."""
    scores_alle = [c["score"] for c in cases]
    labels_alle = [c["hit"] for c in cases]
    punkt = ev.auc(scores_alle, labels_alle)
    rng = random.Random(seed)
    werte: List[float] = []

    if block_feld is None:
        n = len(cases)
        cluster_anzahl = n  # bei primär: Fallzahl als "Cluster-Anzahl"
        for _ in range(bootstrap):
            idx = [rng.randrange(n) for _ in range(n)]
            a = ev.auc([scores_alle[i] for i in idx],
                       [labels_alle[i] for i in idx])
            if a is not None:
                werte.append(a)
    else:
        bloecke = _bloecke(cases, block_feld)
        keys = sorted(bloecke)
        k = len(keys)
        cluster_anzahl = k
        for _ in range(bootstrap):
            gezogen = [keys[rng.randrange(k)] for _ in range(k)]
            s2, l2 = _resample_scores_labels(bloecke, gezogen)
            a = ev.auc(s2, l2)
            if a is not None:
                werte.append(a)

    werte.sort()
    alpha = 1.0 - ci_level
    lo = ev._quantil(werte, alpha / 2) if werte else float("nan")
    hi = ev._quantil(werte, 1 - alpha / 2) if werte else float("nan")
    return {
        "auc": punkt, "ci_untergrenze": lo, "ci_obergrenze": hi,
        "ci_niveau": ci_level, "cluster_anzahl": cluster_anzahl,
        "bootstrap_ziehungen": bootstrap, "faelle": len(cases),
    }


def berechne(cases_a: Sequence[Dict], cases_b: Sequence[Dict],
            seeds: Sequence[int] = SEEDS) -> Dict[int, Dict[str, Dict]]:
    """{seed: {name: ergebnis}} für die vier benannten Rechnungen, über alle
    Seeds. Tag-Block/Ticker-Block NUR auf cases_a — cases_b bekommt
    ausschließlich die fallweise (primäre) Rechnung, nie eine Cluster-
    Variante (Registry-Regel, s. Moduldoc)."""
    out: Dict[int, Dict[str, Dict]] = {}
    for seed in seeds:
        out[seed] = {
            "primär (a)": bootstrap_ci(cases_a, None, seed),
            "Tag-Block (a)": bootstrap_ci(cases_a, "first_seen_date", seed),
            "Ticker-Block (a)": bootstrap_ci(cases_a, "ticker", seed),
            "primär (b)": bootstrap_ci(cases_b, None, seed),
        }
    return out


def bericht(ergebnisse: Dict[int, Dict[str, Dict]]) -> str:
    """Reiner Text, deterministisch aus `ergebnisse` — kein I/O hier."""
    zeilen: List[str] = []
    zeilen.append("Cluster-Sensitivität der AUC — Registry-Regel #166")
    zeilen.append("=" * 60)
    zeilen.append("")
    zeilen.append(
        "HINWEIS: die Trefferquote (Zufalls-Benchmark) ist NICHT Teil "
        "dieses Berichts — nur die AUC. Für die Trefferquote weiterhin "
        "scripts/evaluate.py verwenden.")
    zeilen.append(
        "HINWEIS: die 'primär (a)'/'primär (b)'-Zeilen hier sind eine "
        "Vergleichsrechnung mit identischer Methodik über dieselben fünf "
        "Seeds wie die Cluster-Varianten — NICHT die offizielle "
        "Primärauswertung. Die bleibt ausschließlich evaluate.py's "
        "eigener Lauf mit EVAL_SEED.")
    zeilen.append("")

    for seed in sorted(ergebnisse):
        zeilen.append(f"--- Seed {seed} ---")
        werte_je_name = {}
        for name in _VIER_NAMEN:
            r = ergebnisse[seed][name]
            werte_je_name[name] = r["ci_untergrenze"]
            einheit = "Fälle" if name in ("primär (a)", "primär (b)") else "Cluster"
            zeilen.append(
                f"  {name}: Untergrenze {r['ci_untergrenze']:.4f} "
                f"(AUC {r['auc']:.4f}, Obergrenze {r['ci_obergrenze']:.4f}, "
                f"{r['cluster_anzahl']} {einheit}, n={r['faelle']})")
        unter = [n for n, v in werte_je_name.items() if v <= 0.5]
        ueber = [n for n, v in werte_je_name.items() if v > 0.5]
        if unter and ueber:
            zeilen.append(
                f"  ABWEICHUNG: ≤0,5 bei {', '.join(unter)}; "
                f">0,5 bei {', '.join(ueber)} — nicht entschieden, nur "
                f"ausgewiesen.")
        zeilen.append("")
    return "\n".join(zeilen)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Cluster-Sensitivität der AUC (Registry-Regel #166). "
                    "Nur lesend, nur manuell, schreibt nie ins Repo.")
    ap.add_argument("--sammlung", default="data/forward_collection.json")
    ap.add_argument("--out", default=None,
                    help="Zusätzlich den Bericht in diese Datei schreiben "
                         "(Konsole bleibt immer bedient).")
    args = ap.parse_args(argv)

    if args.out:
        # Relativ zum Repo-Root aufgelöst — konsistent mit --sammlung
        # (Zeile unten) und unabhängig vom tatsächlichen Arbeitsverzeichnis
        # des Aufrufers (Guardian-Nit, 08.10.2026, PR #167).
        out_aufgeloest = (REPO_ROOT / args.out).resolve()
        for verboten in _VERBOTENE_ZIELE:
            if out_aufgeloest == (REPO_ROOT / verboten).resolve():
                print(f"[evaluate_cluster_sensitivity] VERWEIGERT: --out "
                      f"zeigt auf eine geschützte Projektdatei ({verboten}) "
                      f"— das darf dieses Skript nie beschreiben.",
                      file=sys.stderr)
                return 2

    sammlung_pfad = REPO_ROOT / args.sammlung
    coll = json.loads(sammlung_pfad.read_text(encoding="utf-8"))

    cases_a, zaehlwerk_a = ev.build_population(coll)
    if zaehlwerk_a["auswertbar"] < EVAL_MIN_N:
        print(f"[evaluate_cluster_sensitivity] VERWEIGERT: nur "
              f"{zaehlwerk_a['auswertbar']} auswertbare Fälle in Population "
              f"(a) (nötig: {EVAL_MIN_N}). Kein offizielles Ergebnis, wie "
              f"evaluate.py::run() ohne --vorschau.", file=sys.stderr)
        return 1

    coll_b, _entfernt = fss.filtere(coll)
    cases_b, _zaehlwerk_b = ev.build_population(coll_b)

    ergebnisse = berechne(cases_a, cases_b)
    text = bericht(ergebnisse)
    print(text)
    if args.out:
        out_aufgeloest.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
