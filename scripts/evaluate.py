"""Auswertungs-Programm v1 — die Validierungs-Registry in Code.

**BLIND GEBAUT** (28.07.2026, bei 0 gereiften Fällen). Wer die Auswertung erst
schreibt, wenn er die Ergebnisse kennt, biegt sie unbewusst zurecht. Dieses
Programm setzt `docs/validation_registry.md` um — es **definiert nichts neu**.

HARTE GRENZEN (0)
  - läuft **nie** im Tageslauf (kein Aufruf in `.github/workflows/`, kein Import
    aus `elliott_pipeline`/`notify`/`health_check` — per Test abgesichert),
  - sendet **keinen** Push,
  - schreibt **nie** in `forward_collection.json` und **nie** in `report.json`,
  - reines Lesen + eine Ergebnis-Datei.

WAS „AUSWERTBAR" HEISST (1)
  Population = gereift UND nicht per PRU-Guard ausgeschlossen. Die Zähl-Logik
  wird **wiederverwendet**, nicht nachgebaut: `forward_collection.is_excluded`
  ist das Prädikat, und die Populationsgröße wird gegen
  `forward_collection.eval_counts(...)[2]` **geprüft** (Abweichung = Abbruch).
  Ausgeschlossene Records werden separat ausgewiesen, nie stillschweigend
  weggelassen.

NUR EINGEFRORENE FELDER
  Aus jedem Record werden ausschließlich die point-in-time eingefrorenen Felder
  in `FROZEN_FIELDS` gelesen. Es wird **nichts** mit heutigen Kursen
  nachgerechnet — `target_hit` kommt aus der Reifung von damals, nicht aus einer
  neuen Rechnung. Der Test `test_nur_eingefrorene_felder_gelesen` protokolliert
  jeden Feldzugriff und schlägt fehl, sobald ein Feld außerhalb der Liste
  angefasst wird.

DIE KURSBASIS DES ZUFALLS-BENCHMARKS (Registry-Lücke, bewusst benannt)
  Die Registry verlangt „gleiche Aktien, zufällige Einstiegstage" — sagt aber
  nicht, woher die Kurse dieser zufälligen Tage kommen. In der eingefrorenen
  Sammlung stehen sie nicht (dort liegen nur die 10 Bars NACH dem echten
  Einstieg). Umsetzung: die Kursbasis ist eine **separate Momentaufnahme-Datei**,
  die mit `--kurse-holen` einmalig erzeugt und **mitgeliefert** wird. Die
  Auswertung selbst holt **nie** Daten aus dem Netz — sie liest die Datei oder
  meldet den Benchmark als „nicht durchführbar". Fehlt die Datei, kann das
  offizielle Ergebnis nicht „belegt" lauten.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as _dt
import hashlib
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
# Repo-Root MIT auf den Pfad: `config` liegt dort, und forward_collection
# importiert es (beim direkten Aufruf gibt es kein conftest, das das erledigt).
for _p in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import forward_collection as fc  # noqa: E402  — kanonische Definitionen
from numeric import finite  # noqa: E402

# ---------------------------------------------------------------------------
# KONSTANTEN — Teil der datierten Definition „Auswertung v1".
# Eine Änderung erzeugt eine NEUE datierte Version; v1 bleibt stehen.
# ---------------------------------------------------------------------------
EVAL_VERSION = "v1"
EVAL_SEED = 20260728          # fest, im Ergebnis dokumentiert -> reproduzierbar
EVAL_ALPHA = 0.05             # Familien-Fehlerrate der Primär-Familie
BENCH_DRAWS = 10_000          # Ziehungen für die Zufalls-Null-Verteilung
BOOTSTRAP_DRAWS = 10_000      # Bootstrap-Wiederholungen für das AUC-Intervall
PERM_DRAWS = 10_000           # Permutationen für den AUC-p-Wert
SECONDARY_MIN_N = 30          # darunter: „zu wenige Fälle" statt einer Zahl
# Die beauftragten Sekundär-Dimensionen, fest benannt. Sie erscheinen in der
# Ausgabe IMMER — auch ohne einen einzigen Fall. Eine Dimension, die
# stillschweigend fehlt, sieht aus wie eine, die nie vorgesehen war.
SECONDARY_DIMS = (
    "setup_typ", "konfluenz",
    "volumen_w3_zu_w1", "volumen_w4_zu_w3", "volumen_w2_zu_w1",
    "alternation", "momentum_divergenz",
    "ambiguitaet_v1", "ambiguitaet_v2", "agent_einwand",
)
HORIZON_DAYS = fc.HORIZON_DAYS
EVAL_MIN_N = fc.EVAL_MIN_N

# Die Primär-Familie (vorregistriert, Reihenfolge fest).
PRIMARY_KEYS = ("trefferquote_vs_zufall", "score_trennschaerfe")

# Ausschliesslich diese Record-Felder fliessen in die Rechnung. Alles davon ist
# bei Anlage bzw. bei der Reifung eingefroren worden.
FROZEN_FIELDS = (
    # Identität / Population
    "episode_id", "ticker", "market", "matured", "first_seen_date",
    "pre_reached_target", "pre_reached_ext", "pre_guard_contaminated",
    # Primär
    "score_heuristic", "target_hit", "entry_close", "invalidation_price",
    "target_zone",
    # Sekundär (explorativ)
    "count_wave_labels", "confluence", "ambiguity_n", "ambiguity_n_v2",
    "agent_concern_level", "alternation_observed", "w5_momentum_divergence",
    "vol_ratio_w3_w1", "vol_ratio_w4_w3", "vol_ratio_w2_w1",
)
# Die Liste darf weder zu eng noch zu weit sein: ein Test prüft beides — kein
# Zugriff ausserhalb, und kein Eintrag, der nie gelesen wird (eine zu breite
# Allowlist gibt eine Sicherheit vor, die sie nicht hat).


def _log(msg: str) -> None:
    print(f"[evaluate] {msg}")


# ---------------------------------------------------------------------------
# 1 · POPULATION
# ---------------------------------------------------------------------------
class _Case(dict):
    """Ein auswertbarer Fall. Dict, damit die Felder benannt bleiben."""


def build_population(coll: Dict) -> Tuple[List[_Case], Dict]:
    """(Fälle, Zählwerk). Wiederverwendet `is_excluded`/`eval_counts`.

    Die Populationsgrösse wird gegen `eval_counts(...)[2]` GEPRÜFT — driftet
    hier je etwas auseinander, bricht die Auswertung ab, statt still eine
    andere Grundgesamtheit auszuwerten.
    """
    records = coll.get("records") or []
    collected, matured, evaluable = fc.eval_counts(coll)

    population = [r for r in records if r.get("matured") and not fc.is_excluded(r)]
    if len(population) != evaluable:
        raise AssertionError(
            f"Populations-Drift: {len(population)} vs. eval_counts {evaluable} — "
            "Auswertung abgebrochen (Definitionen müssen deckungsgleich sein).")

    ausgeschlossen = [r for r in records if r.get("matured") and fc.is_excluded(r)]
    cases: List[_Case] = []
    ohne_messwert = 0
    for r in population:
        score = r.get("score_heuristic")
        hit = r.get("target_hit")
        if not finite(score) or hit not in (0, 1):
            ohne_messwert += 1
            continue
        cases.append(_Case(
            episode_id=r.get("episode_id"), ticker=r.get("ticker"),
            market=r.get("market"), first_seen_date=r.get("first_seen_date"),
            score=float(score), hit=int(hit),
            entry=r.get("entry_close"), inval=r.get("invalidation_price"),
            tlow=(r.get("target_zone") or {}).get("low"),
            rec=r))
    zaehlwerk = {
        "gesammelt": collected,
        "gereift": matured,
        "auswertbar": evaluable,
        # FÄLLE (jeder Record genau einmal) …
        "ausgeschlossen_pru_guard": len(ausgeschlossen),
        # … gegen NENNUNGEN: ein Record kann mehrere Gründe tragen
        # (`pre_reached_target` UND `pre_reached_ext`). Die Summe der Gründe ist
        # deshalb GRÖSSER als die Zahl der Fälle — im Trockenlauf standen 13
        # Nennungen für 5 Fälle. Der Hinweis steht daneben, damit niemand
        # addiert und sich verrechnet.
        "ausgeschlossen_gruende": _exclusion_reasons(ausgeschlossen),
        "ausgeschlossen_gruende_hinweis": (
            f"Nennungen, Mehrfachnennung möglich — "
            f"{len(ausgeschlossen)} betroffene Fälle"),
        # Transparenz: markiert, aber noch nicht gereift — zählt heute nirgends
        # mit, wäre später aber auch nicht in der Population. Ausdrücklich
        # ausgewiesen, damit niemand die Zahlen gegeneinander verrechnen muss.
        "markiert_noch_nicht_gereift": sum(
            1 for r in records if not r.get("matured") and fc.is_excluded(r)),
        "auswertbar_ohne_messwert": ohne_messwert,
        "in_der_rechnung": len(cases),
    }
    return cases, zaehlwerk


def _exclusion_reasons(recs: Sequence[Dict]) -> Dict[str, int]:
    out = {"pre_reached_target": 0, "pre_reached_ext": 0,
           "pre_guard_contaminated": 0}
    for r in recs:
        for k in out:
            if r.get(k):
                out[k] += 1
    return out


# ---------------------------------------------------------------------------
# 3a · TREFFERQUOTE GEGEN ZUFALLS-BENCHMARK
# ---------------------------------------------------------------------------
def simulate_hit(closes: Sequence[float], start: int, ratio_target: float,
                 ratio_inval: float, horizon: int = HORIZON_DAYS) -> Optional[int]:
    """Ein synthetischer Fall — EXAKT die Treffer-Definition aus `mature_record`.

    Einstieg am Bar `start`, dieselben RELATIVEN Abstände zu Ziel und
    Ungültigkeitsmarke, derselbe Horizont, dieselbe Gleichstands-Regel
    (Gleichstand am selben Tag zählt als Ungültigkeit, nie als Treffer).
    None, wenn nicht genügend gültige Folge-Bars vorliegen.
    """
    entry = closes[start]
    if not finite(entry) or entry <= 0:
        return None
    tlow = entry * ratio_target
    inval = entry * ratio_inval
    fwd: List[float] = []
    for c in closes[start + 1:]:
        if len(fwd) >= horizon:
            break
        if finite(c):
            fwd.append(float(c))
    if len(fwd) < horizon:
        return None
    target_day = inval_day = None
    for i, c in enumerate(fwd):
        if inval_day is None and c <= inval:
            inval_day = i
        if target_day is None and c >= tlow:
            target_day = i
    return 1 if (target_day is not None
                 and (inval_day is None or target_day < inval_day)) else 0


def _eligible_starts(dates: Sequence[str], closes: Sequence[float],
                     von: str, bis: str) -> List[int]:
    """Bars im Sammel-Zeitraum, die noch `HORIZON_DAYS` gültige Folge-Bars haben."""
    out = []
    for i, d in enumerate(dates):
        if not (von <= d <= bis):
            continue
        if not finite(closes[i]) or closes[i] <= 0:
            continue
        rest = sum(1 for c in closes[i + 1:i + 1 + 3 * HORIZON_DAYS] if finite(c))
        if rest >= HORIZON_DAYS:
            out.append(i)
    return out


def benchmark_test(cases: Sequence[_Case], prices: Optional[Dict],
                   rng: random.Random, draws: int = BENCH_DRAWS) -> Dict:
    """Null-Verteilung der Trefferquote aus zufälligen Einstiegstagen.

    Für JEDEN echten Fall wird im SELBEN Ticker über den SELBEN Zeitraum ein
    zufälliger Einstiegstag gezogen und mit denselben relativen Abständen
    gerechnet. Eine Ziehung = ein komplettes Vergleichs-Portfolio; `draws`
    Ziehungen ergeben die Null-Verteilung.

    Die Fall-Ergebnisse werden je Fall **einmal** über alle in Frage kommenden
    Tage vorberechnet; die Ziehungen greifen dann nur noch zu (identisches
    Ergebnis, ohne dieselbe Rechnung zehntausendfach zu wiederholen).
    """
    beobachtet = sum(c["hit"] for c in cases) / len(cases) if cases else None
    if not cases:
        return {"durchfuehrbar": False, "grund": "keine Fälle",
                "beobachtete_quote": None}
    if not prices:
        return {"durchfuehrbar": False,
                "grund": "keine Kursbasis (Momentaufnahme fehlt)",
                "beobachtete_quote": beobachtet}

    von = min(c["first_seen_date"] for c in cases)
    bis = max(c["first_seen_date"] for c in cases)

    outcomes: List[List[int]] = []
    ohne_kurse: List[str] = []
    for c in cases:
        ser = prices.get(c["ticker"])
        entry, tlow, inval = c["entry"], c["tlow"], c["inval"]
        if not ser or not all(finite(v) for v in (entry, tlow, inval)) or entry <= 0:
            ohne_kurse.append(c["ticker"])
            continue
        dates, closes = ser.get("dates") or [], ser.get("closes") or []
        starts = _eligible_starts(dates, closes, von, bis)
        r_t, r_i = tlow / entry, inval / entry
        vals = [h for h in (simulate_hit(closes, s, r_t, r_i) for s in starts)
                if h is not None]
        if not vals:
            ohne_kurse.append(c["ticker"])
            continue
        outcomes.append(vals)

    if ohne_kurse:
        return {"durchfuehrbar": False,
                "grund": f"Kursbasis unvollständig ({len(ohne_kurse)} von "
                         f"{len(cases)} Fällen ohne verwendbare Kurse)",
                "beobachtete_quote": beobachtet,
                "fehlende_ticker": sorted(set(ohne_kurse))}

    n = len(outcomes)
    verteilung: List[float] = []
    for _ in range(draws):
        s = 0
        for vals in outcomes:
            s += vals[rng.randrange(len(vals))]
        verteilung.append(s / n)
    verteilung.sort()
    mind_so_hoch = sum(1 for v in verteilung if v >= beobachtet)
    p = (1 + mind_so_hoch) / (draws + 1)      # Add-One: nie p = 0
    return {
        "durchfuehrbar": True,
        "beobachtete_quote": beobachtet,
        "zufalls_quote_mittel": sum(verteilung) / len(verteilung),
        "zufalls_quote_p05": _quantil(verteilung, 0.05),
        "zufalls_quote_p95": _quantil(verteilung, 0.95),
        "p_wert": p,
        "ziehungen": draws,
        "faelle": n,
        "treffer": sum(c["hit"] for c in cases),
        "zeitraum": {"von": von, "bis": bis},
    }


def _quantil(sortiert: Sequence[float], q: float) -> float:
    if not sortiert:
        return float("nan")
    i = min(len(sortiert) - 1, max(0, int(round(q * (len(sortiert) - 1)))))
    return sortiert[i]


# ---------------------------------------------------------------------------
# 3b · SCORE-TRENNSCHÄRFE (AUC)
# ---------------------------------------------------------------------------
def auc(scores: Sequence[float], labels: Sequence[int]) -> Optional[float]:
    """Rang-basierte AUC (Mann-Whitney). Gleichstände zählen mit 0,5.

    None, wenn eine der beiden Gruppen leer ist (dann ist Trennschärfe nicht
    definiert — kein Ersatzwert, keine stille 0,5).
    """
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    paare = 0.0
    neg_sorted = sorted(neg)
    for s in pos:
        # bisect aus der Standardbibliothek — eine selbstgeschriebene binäre
        # Suche war hier bereits einmal falsch herum und lieferte still AUC 0,5
        # (der Selbsttest „starker Zusammenhang" fing es). Nie wieder von Hand.
        kleiner = bisect.bisect_left(neg_sorted, s)
        gleich = bisect.bisect_right(neg_sorted, s) - kleiner
        paare += kleiner + 0.5 * gleich
    return paare / (len(pos) * len(neg))


def auc_test(cases: Sequence[_Case], rng: random.Random, *, ci_level: float,
             bootstrap: int = BOOTSTRAP_DRAWS, perm: int = PERM_DRAWS) -> Dict:
    """AUC mit Bootstrap-Intervall (Perzentil) und Permutations-p-Wert."""
    scores = [c["score"] for c in cases]
    labels = [c["hit"] for c in cases]
    if not cases:
        return {"durchfuehrbar": False, "grund": "keine Fälle"}
    punkt = auc(scores, labels)
    if punkt is None:
        return {"durchfuehrbar": False,
                "grund": "alle Fälle haben denselben Ausgang — "
                         "Trennschärfe nicht bestimmbar"}
    n = len(cases)
    werte: List[float] = []
    for _ in range(bootstrap):
        idx = [rng.randrange(n) for _ in range(n)]
        a = auc([scores[i] for i in idx], [labels[i] for i in idx])
        if a is not None:
            werte.append(a)
    werte.sort()
    alpha = 1.0 - ci_level
    lo = _quantil(werte, alpha / 2) if werte else float("nan")
    hi = _quantil(werte, 1 - alpha / 2) if werte else float("nan")

    perm_labels = list(labels)
    mind = 0
    for _ in range(perm):
        rng.shuffle(perm_labels)
        a = auc(scores, perm_labels)
        if a is not None and a >= punkt:
            mind += 1
    p = (1 + mind) / (perm + 1)
    return {
        "durchfuehrbar": True,
        "auc": punkt,
        "ci_untergrenze": lo,
        "ci_obergrenze": hi,
        "ci_niveau": ci_level,
        "p_wert": p,
        "bootstrap_ziehungen": bootstrap,
        "permutationen": perm,
        "faelle": n,
        "treffer": sum(labels),
    }


# ---------------------------------------------------------------------------
# HOLM über die Primär-Familie
# ---------------------------------------------------------------------------
def holm(pvalues: Dict[str, float], alpha: float = EVAL_ALPHA) -> Dict[str, Dict]:
    """Holm-Bonferroni. Gibt je Test das eigene Niveau und das Urteil zurück.

    Das **Niveau** (`alpha_stufe`) wird mitgegeben, weil die Registry für die
    AUC kein p-Kriterium nennt, sondern eine **Intervall-Untergrenze > 0,5** —
    dieses Intervall wird auf demselben Holm-Niveau gebildet, damit beide
    Primär-Kriterien dieselbe Familien-Fehlerrate teilen.
    """
    k = len(pvalues)
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    out: Dict[str, Dict] = {}
    lauf_max = 0.0
    weiter = True
    for rang, (key, p) in enumerate(ordered):
        stufe = alpha / (k - rang)
        adj = min(1.0, max(lauf_max, p * (k - rang)))
        lauf_max = adj
        signifikant = weiter and p <= stufe
        if not signifikant:
            weiter = False            # ab hier stoppt Holm
        out[key] = {"p_wert": p, "alpha_stufe": stufe,
                    "p_korrigiert": adj, "signifikant": signifikant}
    return out


# ---------------------------------------------------------------------------
# 4 · SEKUNDÄR — explorativ, NICHT beweisend
# ---------------------------------------------------------------------------
# Setup-Typ aus der Sammlung WIEDERVERWENDET, nicht nachgebaut (29.07.2026).
# Hier stand eine wortgleiche eigene Fassung — ausgerechnet in dem Modul, dessen
# Kernaussage „wiederverwenden statt nachbauen" ist. KEINE Definitionsänderung:
# `tests/test_one_count_source.py` stellt die entfernte Fassung nach und prüft,
# dass beide für dieselben Fälle dieselbe Gruppe liefern. „Auswertung v1" bleibt
# inhaltlich unverändert.
_is_end_of_w4 = fc._is_end_of_w4


def _hat_konfluenz(rec: Dict) -> Optional[bool]:
    conf = rec.get("confluence")
    if conf is None:
        return None
    return bool((conf.get("target") or []) or (conf.get("invalidation") or []))


def _gruppen(cases: Sequence[_Case]) -> Dict[str, Dict[str, List[int]]]:
    """Je Dimension: Gruppenname -> Liste der Ausgänge (0/1)."""
    dims: Dict[str, Dict[str, List[int]]] = {}

    def add(dim: str, gruppe: Optional[str], hit: int) -> None:
        if gruppe is None:
            return
        dims.setdefault(dim, {}).setdefault(gruppe, []).append(hit)

    for c in cases:
        r = c["rec"]
        hit = c["hit"]
        add("setup_typ", "Ende W4" if _is_end_of_w4(r) else "Ende W2", hit)
        k = _hat_konfluenz(r)
        add("konfluenz", None if k is None else ("mit" if k else "ohne"), hit)
        for feld, dim in (("vol_ratio_w3_w1", "volumen_w3_zu_w1"),
                          ("vol_ratio_w4_w3", "volumen_w4_zu_w3"),
                          ("vol_ratio_w2_w1", "volumen_w2_zu_w1")):
            v = r.get(feld)
            add(dim, None if not finite(v) else ("≥ 1" if v >= 1 else "< 1"), hit)
        a = r.get("alternation_observed")
        add("alternation", None if a is None else ("ja" if a else "nein"), hit)
        d = r.get("w5_momentum_divergence")
        add("momentum_divergenz", None if d is None else ("ja" if d else "nein"), hit)
        for feld, dim in (("ambiguity_n", "ambiguitaet_v1"),
                          ("ambiguity_n_v2", "ambiguitaet_v2")):
            v = r.get(feld)
            add(dim, None if v is None else f"{int(v)} Lesart(en)", hit)
        cl = r.get("agent_concern_level")
        add("agent_einwand", None if cl is None else str(cl), hit)
    return dims


def secondary(cases: Sequence[_Case], min_n: int = SECONDARY_MIN_N) -> Dict:
    """Explorativ. Unter `min_n` Fällen wird KEINE Quote gemeldet.

    Bewusst ohne p-Werte und ohne Intervalle: diese Dimensionen sind nicht
    vorregistriert, jede Zahl mit Signifikanz-Anstrich wäre eine Einladung zum
    Nachträglich-Erzählen.

    JEDE beauftragte Dimension erscheint — auch die ohne einen einzigen Fall
    (29.07.2026). Vorher fiel eine leere Dimension ersatzlos aus der Ausgabe;
    wer sie las, sah nicht, dass sie geprüft wurde und keine Daten hatte
    (Trockenlauf: `momentum_divergenz` war komplett verschwunden). Abwesenheit
    ist keine Aussage — „keine Fälle" ist eine.
    """
    gefunden = _gruppen(cases)
    out: Dict[str, Dict] = {}
    for dim in SECONDARY_DIMS:
        gruppen = gefunden.get(dim) or {}
        eintrag: Dict = {"faelle_gesamt": sum(len(h) for h in gruppen.values()),
                         "gruppen": {}, "hinweis": None}
        if not gruppen:
            eintrag["hinweis"] = "keine Fälle"
        for name, hits in sorted(gruppen.items()):
            eintrag["gruppen"][name] = (
                {"faelle": len(hits), "quote": None, "hinweis": "zu wenige Fälle"}
                if len(hits) < min_n else
                {"faelle": len(hits), "quote": sum(hits) / len(hits),
                 "hinweis": None})
        out[dim] = eintrag
    return out


# ---------------------------------------------------------------------------
# 5 · AUSGABE — Klartext + Zahlenanhang
# ---------------------------------------------------------------------------
def _pct(x: Optional[float]) -> str:
    return "—" if x is None or not finite(x) else f"{x * 100:.0f} von 100"


def klartext(res: Dict) -> List[str]:
    """Wenige Sätze, einfache Sprache, keine Fachbegriffe.

    Ein Nein steht hier genauso klar wie ein Ja — das ist der Zweck.
    """
    z = res["zaehlwerk"]
    saetze: List[str] = []
    if not res["gueltig"]:
        saetze.append(
            "VORSCHAU — NICHT GÜLTIG. Es sind noch zu wenige Fälle fertig "
            f"beobachtet ({z['auswertbar']} von {EVAL_MIN_N}). Die Zahlen unten "
            "sind ein Blick auf den Zwischenstand, kein Ergebnis.")

    saetze.append(
        "Geprüft wurde zweierlei: Geht es öfter wie erhofft aus, als wenn man "
        "an zufällig gewählten Tagen mit denselben Abständen dasselbe versucht "
        "hätte? Und: Gehen Fälle mit hoher Punktzahl öfter gut aus als Fälle "
        "mit niedriger?")

    b = res["primaer"]["trefferquote_vs_zufall"]
    if not b.get("durchfuehrbar"):
        saetze.append(f"Der erste Vergleich war nicht möglich: {b.get('grund')}.")
    else:
        saetze.append(
            f"Von {b['faelle']} fertig beobachteten Fällen gingen "
            f"{b['treffer']} wie erhofft aus — das sind "
            f"{_pct(b['beobachtete_quote'])}. Wählt man stattdessen zufällige "
            f"Tage, sind es {_pct(b['zufalls_quote_mittel'])}.")

    a = res["primaer"]["score_trennschaerfe"]
    if not a.get("durchfuehrbar"):
        saetze.append(f"Der zweite Vergleich war nicht möglich: {a.get('grund')}.")
    else:
        saetze.append(
            "Stellt man je einen guten und einen schlechten Ausgang gegenüber, "
            f"hatte der gute in {_pct(a['auc'])} Fällen die höhere Punktzahl.")

    urteil = res["urteil"]
    if urteil["belegt"]:
        saetze.append(
            "Beides hält auch der strengen Prüfung stand: Der Ansatz hat den "
            "Test bestanden. Das heißt nicht, dass er in Zukunft funktioniert — "
            "es heißt, dass das Bisherige nicht durch Zufall zu erklären ist.")
    elif res["gueltig"]:
        saetze.append(
            "Das reicht nicht aus: Der Ansatz hat den Test nicht bestanden. "
            f"Der Grund: {urteil['begruendung']} Die Punktzahl bleibt damit "
            "das, was sie war — eine Schätzung ohne Nachweis.")
    else:
        saetze.append(
            "Ein Urteil gibt es hier bewusst nicht — dafür ist es zu früh.")

    saetze.append(
        "Alles Weitere unten ist nur zum Nachschlagen. Was dort steht, ist "
        "Beiwerk: es kann Ideen liefern, aber nichts beweisen.")
    return saetze


def _urteil(primaer: Dict, holm_out: Dict, gueltig: bool) -> Dict:
    b, a = primaer["trefferquote_vs_zufall"], primaer["score_trennschaerfe"]
    gruende: List[str] = []
    if not b.get("durchfuehrbar"):
        gruende.append("der Vergleich mit zufälligen Tagen war nicht möglich")
    elif not holm_out.get("trefferquote_vs_zufall", {}).get("signifikant"):
        gruende.append("der Vorsprung gegenüber zufällig gewählten Tagen ist "
                       "zu klein, um ihn vom Zufall zu unterscheiden")
    if not a.get("durchfuehrbar"):
        gruende.append("die Trennschärfe der Punktzahl war nicht bestimmbar")
    else:
        if not holm_out.get("score_trennschaerfe", {}).get("signifikant"):
            gruende.append("die Punktzahl trennt gute von schlechten Ausgängen "
                           "nicht deutlich genug")
        elif not (finite(a.get("ci_untergrenze")) and a["ci_untergrenze"] > 0.5):
            gruende.append("die Punktzahl trennt gute von schlechten Ausgängen "
                           "nicht sicher genug (der ungünstigste Fall wäre "
                           "immer noch Zufall)")
    belegt = bool(gueltig and not gruende)
    return {"belegt": belegt,
            "begruendung": ("" if belegt else "; ".join(gruende) + "."),
            "gilt_nur_wenn": "beide Primär-Kriterien erfüllt (Registry)"}


# ---------------------------------------------------------------------------
# LAUF
# ---------------------------------------------------------------------------
def run(coll: Dict, prices: Optional[Dict] = None, *, seed: int = EVAL_SEED,
        alpha: float = EVAL_ALPHA, now: Optional[str] = None,
        vorschau: bool = False, bench_draws: int = BENCH_DRAWS,
        bootstrap_draws: int = BOOTSTRAP_DRAWS,
        perm_draws: int = PERM_DRAWS) -> Dict:
    """Reine Funktion: Sammlung rein, Ergebnis raus. Schreibt nichts."""
    cases, zaehlwerk = build_population(coll)
    gueltig = zaehlwerk["auswertbar"] >= EVAL_MIN_N
    if not gueltig and not vorschau:
        raise RuntimeError(
            f"Nur {zaehlwerk['auswertbar']} auswertbare Fälle (nötig: "
            f"{EVAL_MIN_N}). Ein offizielles Ergebnis gibt es nicht. Für den "
            "Zwischenstand: --vorschau (das Ergebnis ist dann ausdrücklich "
            "NICHT gültig).")

    rng = random.Random(seed)
    bench = benchmark_test(cases, prices, rng, draws=bench_draws)

    p_map: Dict[str, float] = {}
    if bench.get("durchfuehrbar"):
        p_map["trefferquote_vs_zufall"] = bench["p_wert"]

    # Das AUC-Intervall braucht sein Holm-Niveau — darum zwei Schritte: erst mit
    # dem konservativsten Niveau rechnen (alpha/k), dann Holm über beide p-Werte.
    k = len(PRIMARY_KEYS)
    auc_res = auc_test(cases, rng, ci_level=1.0 - alpha / k,
                       bootstrap=bootstrap_draws, perm=perm_draws)
    if auc_res.get("durchfuehrbar"):
        p_map["score_trennschaerfe"] = auc_res["p_wert"]

    holm_out = holm(p_map, alpha=alpha) if p_map else {}
    primaer = {"trefferquote_vs_zufall": bench, "score_trennschaerfe": auc_res}
    urteil = _urteil(primaer, holm_out, gueltig)

    res = {
        "auswertung_version": EVAL_VERSION,
        "gueltig": gueltig,
        "modus": "offiziell" if gueltig else "vorschau",
        "erstellt_utc": now or _dt.datetime.now(_dt.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "zaehlwerk": zaehlwerk,
        "primaer": primaer,
        "holm": holm_out,
        "urteil": urteil,
        "sekundaer_explorativ": secondary(cases),
        "definitionen": {
            "quelle": "docs/validation_registry.md",
            "auswertbar": "gereift UND nicht per PRU-Guard ausgeschlossen "
                          "(forward_collection.eval_counts[2])",
            "treffer": "Zielzonen-Unterkante VOR der Ungültigkeitsmarke erreicht; "
                       "Gleichstand am selben Tag zählt als Ungültigkeit",
            "horizont_handelstage": HORIZON_DAYS,
            "mindestfaelle": EVAL_MIN_N,
            "benchmark": "gleicher Ticker, zufälliger Einstiegstag im selben "
                         "Zeitraum, gleiche relative Abstände, gleicher Horizont",
            "familie": list(PRIMARY_KEYS),
            "korrektur": "Holm-Bonferroni über die Primär-Familie; das "
                         "AUC-Intervall nutzt dasselbe Niveau",
            "sekundaer": "explorativ, nicht beweisend; unter "
                         f"{SECONDARY_MIN_N} Fällen keine Quote",
        },
        "reproduzierbarkeit": {
            "seed": seed, "alpha": alpha,
            "ziehungen_benchmark": bench_draws,
            "ziehungen_bootstrap": bootstrap_draws,
            "permutationen": perm_draws,
            "horizont": HORIZON_DAYS,
            "sekundaer_mindestfaelle": SECONDARY_MIN_N,
        },
    }
    res["fazit_klartext"] = klartext(res)
    return res


# ---------------------------------------------------------------------------
# KURSBASIS (getrennter Modus — die Auswertung selbst holt NIE Daten)
# ---------------------------------------------------------------------------
def _close_spalte(df) -> Tuple[Optional[List], Optional[str]]:
    """Die EINE Close-Spalte eines Ticker-Downloads — oder ein Grund (30.07.2026).

    Vorher stand hier `df["Close"].to_numpy().ravel().tolist()`. Das trug nur,
    solange je Ticker genau EINE Close-Spalte zurückkam: `ravel()` macht jede
    Form flach, also hätte es zwei Spalten **zeilenweise ineinander
    verschränkt** und die verformten Zahlen als gültige Kursreihe in die
    Momentaufnahme geschrieben — die Datei, die später der einzige Beleg dafür
    ist, WELCHE Kurse in den Benchmark geflossen sind.

    Deshalb: erst die Spalten auf die Normalform der Pipeline bringen
    (`_normalize_columns`, dieselbe Funktion, kein Nachbau), dann prüfen, dass
    genau eine Close-Spalte übrig ist. Alles andere ist ein GRUND, den Ticker
    namentlich als „ohne Kurse" auszuweisen — nicht etwas, das man flach macht.

    Rückgabe: (roh_closes, None) im Normalfall, (None, grund) sonst.
    """
    # Lokaler Import wie `yfinance`: nur dieser Modus braucht ihn. Der
    # Auswertungs-Modus bleibt damit frei von der Pipeline (die ihrerseits
    # `notify` zieht) — die Auswertung darf nie in die Nähe eines Pushes kommen.
    from elliott_pipeline import _normalize_columns  # noqa: PLC0415

    if df is None or getattr(df, "empty", True):
        return None, "leere Antwort"
    df = _normalize_columns(df)
    spalten = list(getattr(df, "columns", []))
    if "Close" not in spalten:
        return None, f"keine 'Close'-Spalte; Spalten={spalten}"
    spalte = df["Close"]
    # ndim != 1 heisst: mehrere gleichnamige Close-Spalten (z. B. ein Download
    # mit mehreren Tickern). Genau der Fall, den `ravel()` still verformt hätte.
    if getattr(spalte, "ndim", 1) != 1:
        return None, (f"mehrdeutige Close-Spalte: shape="
                      f"{getattr(spalte, 'shape', None)}, Spalten={spalten}")
    # KEIN `ravel()` mehr: die Spalte ist hier nachweislich eindimensional,
    # und ein Flachmacher, der nie greifen darf, ist nur eine stille Falle.
    return spalte.to_numpy().tolist(), None


def fetch_prices(coll: Dict, out_path: Path, *, jahre: int = 2) -> Dict:
    """Momentaufnahme der Kurshistorie je Ticker der Population.

    BEWUSST ein eigener Modus: die Auswertung liest ausschliesslich diese Datei
    und geht nie selbst ins Netz. So bleibt ein Auswertungslauf offline,
    wiederholbar und prüfbar — und es ist jederzeit belegbar, WELCHE Kurse in
    den Benchmark geflossen sind (Prüfsumme im Ergebnis).

    EIN GESCHEITERTER ABRUF MUSS SOFORT SICHTBAR SCHEITERN (29.07.2026). Der
    Trockenlauf zeigte das Gegenteil: yfinance meldet einen Fehlschlag **nicht**
    als Ausnahme, sondern als leeren DataFrame. Der landete als gültig
    aussehender Eintrag mit 0 Bars in der Datei, das Log meldete „Kursbasis
    geschrieben (4 Ticker)" und der Rückgabewert war 0 — der Fehler wäre erst
    Monate später beim Auswerten aufgefallen. Jetzt: leere Antworten kommen
    **gar nicht erst** in die Datei, am Ende steht eine Zusammenfassung, und
    der Modus endet mit einem Rückgabewert ungleich 0, sobald auch nur ein
    Ticker fehlt.
    """
    import yfinance as yf  # lokal: nur dieser Modus braucht die Abhängigkeit

    ticker = sorted({r.get("ticker") for r in (coll.get("records") or [])
                     if r.get("ticker")})
    daten: Dict[str, Dict] = {}
    ohne: List[str] = []
    luecken: List[Dict] = []      # Ticker MIT Kursen, aber mit Löchern
    for t in ticker:
        try:
            df = yf.download(t, period=f"{jahre}y", interval="1d",
                             auto_adjust=True, progress=False, threads=False)
            roh_closes, grund = _close_spalte(df)
            roh_dates = list(getattr(df, "index", []))
        except Exception as exc:  # noqa: BLE001 — je Ticker gefangen, aber gezählt
            _log(f"{t}: keine Kurse ({exc})")
            ohne.append(t)
            continue
        if roh_closes is None:
            _log(f"{t}: keine Kurse ({grund})")
            ohne.append(t)
            continue
        # UNBRAUCHBARE ZEILEN VERWERFEN — wie die Pipeline (30.07.2026).
        # Vorher wanderte ein nicht endlicher Kurs unverändert durch: die Datei
        # enthielt dann literales `NaN` (kein gültiges JSON — genau die Klasse
        # aus #51; Python liest es klaglos zurück, der Standard kennt es nicht),
        # und der Abruf meldete trotzdem Erfolg. Jetzt: Zeile fliegt raus, Datum
        # bleibt ausgerichtet, der Ticker wird namentlich als lückenhaft
        # ausgewiesen. Die Auswertung war nie gefährdet (`_eligible_starts` und
        # `simulate_hit` prüfen `finite`) — die MOMENTAUFNAHME war es.
        # ROH-Längen ZUERST vergleichen: `zip` würde eine Ungleichheit still
        # abschneiden und den Versatz-Guard damit wirkungslos machen (genau das
        # hat der bestehende Test gefangen). Ein Versatz zwischen Datum und Kurs
        # ist der Defekt aus #53 — er darf hier gar nicht hineinkommen.
        if len(roh_dates) != len(roh_closes):
            _log(f"{t}: verworfen — {len(roh_dates)} Daten vs. "
                 f"{len(roh_closes)} Kurse")
            ohne.append(t)
            continue
        dates, closes, verworfen = [], [], 0
        for d_roh, c_roh in zip(roh_dates, roh_closes):
            if not finite(c_roh):
                verworfen += 1
                continue
            try:
                dates.append(d_roh.strftime("%Y-%m-%d"))
            except Exception:  # noqa: BLE001 — Index ohne Datum: Bar unbrauchbar
                verworfen += 1
                continue
            closes.append(float(c_roh))
        if verworfen:
            _log(f"{t}: {verworfen} unbrauchbare Zeile(n) verworfen")
            luecken.append({"ticker": t, "verworfen": verworfen})
        if not dates or not closes:
            _log(f"{t}: keine Kurse (leere Antwort — kein Eintrag geschrieben)")
            ohne.append(t)
            continue
        daten[t] = {"dates": dates, "closes": closes}
        _log(f"{t}: {len(dates)} Bars")

    payload = {"erstellt_utc": _dt.datetime.now(_dt.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
               "jahre": jahre, "ticker": len(daten),
               "ticker_angefragt": len(ticker),
               "ticker_ohne_kurse": ohne,
               "ticker_mit_luecken": luecken, "kurse": daten}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    _log(f"Kursbasis geschrieben: {out_path} — "
         f"{len(daten)} von {len(ticker)} Tickern mit Kursen")
    if luecken:
        _log("MIT LUECKEN: " + ", ".join(
            f"{x['ticker']}(-{x['verworfen']})" for x in luecken))
    if ohne:
        _log(f"OHNE KURSE: {len(ohne)} von {len(ticker)} — {', '.join(ohne)}")
        _log("Die Kursbasis ist damit UNVOLLSTÄNDIG; der Zufalls-Vergleich "
             "wäre nicht durchführbar. Abruf wiederholen.")
    return payload


def _pruefsumme(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def render_text(res: Dict) -> str:
    """Zweiteilig: erst Klartext, dann Zahlenanhang."""
    lines = ["=" * 68,
             f"AUSWERTUNG {res['auswertung_version'].upper()} — "
             f"{'OFFIZIELLES ERGEBNIS' if res['gueltig'] else 'VORSCHAU (NICHT GÜLTIG)'}",
             "=" * 68, ""]
    for s in res["fazit_klartext"]:
        lines += [s, ""]
    lines += ["-" * 68, "ZAHLEN ZUM NACHSCHLAGEN", "-" * 68,
              json.dumps({k: res[k] for k in
                          ("zaehlwerk", "primaer", "holm", "urteil",
                           "sekundaer_explorativ", "definitionen",
                           "reproduzierbarkeit", "erstellt_utc")},
                         ensure_ascii=False, indent=1)]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Auswertungs-Programm v1 (liest nur, schreibt nur die "
                    "Ergebnis-Datei).")
    ap.add_argument("--sammlung", default="data/forward_collection.json")
    ap.add_argument("--kurse", default="data/eval_prices.json",
                    help="Momentaufnahme für den Zufalls-Benchmark")
    ap.add_argument("--out", default="data/evaluation/ergebnis.json")
    ap.add_argument("--seed", type=int, default=EVAL_SEED)
    ap.add_argument("--alpha", type=float, default=EVAL_ALPHA)
    ap.add_argument("--vorschau", action="store_true",
                    help="Zwischenstand unter n<%d — ausdrücklich NICHT gültig"
                         % EVAL_MIN_N)
    ap.add_argument("--kurse-holen", action="store_true",
                    help="NUR die Kursbasis holen und schreiben (eigener Modus)")
    ap.add_argument("--now", default=None, help="Zeitstempel festnageln (Tests)")
    args = ap.parse_args(argv)

    coll_path = REPO_ROOT / args.sammlung
    coll = json.loads(coll_path.read_text(encoding="utf-8"))

    if args.kurse_holen:
        payload = fetch_prices(coll, REPO_ROOT / args.kurse)
        # Rückgabewert ungleich 0, sobald ein Ticker fehlt: ein unvollständiger
        # Abruf darf nicht wie ein geglückter aussehen (auch nicht in einem
        # Workflow-Schritt, der nur auf den Exit-Code schaut).
        # Rueckgabewert ungleich 0 auch bei LUECKEN: ein Abruf, der stumm
        # Zeilen verloren hat, darf nicht wie ein vollstaendiger aussehen.
        return 3 if (payload["ticker_ohne_kurse"]
                     or payload["ticker_mit_luecken"]) else 0

    prices_payload = None
    kurse_path = REPO_ROOT / args.kurse
    if kurse_path.exists():
        prices_payload = json.loads(kurse_path.read_text(encoding="utf-8"))

    try:
        res = run(coll, (prices_payload or {}).get("kurse"), seed=args.seed,
                  alpha=args.alpha, now=args.now, vorschau=args.vorschau)
    except RuntimeError as exc:
        print(str(exc))
        return 2

    res["kursbasis"] = ({"datei": args.kurse,
                         "erstellt_utc": prices_payload.get("erstellt_utc"),
                         "ticker": prices_payload.get("ticker"),
                         "pruefsumme": _pruefsumme(prices_payload.get("kurse"))}
                        if prices_payload else None)

    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(render_text(res))
    _log(f"Ergebnis geschrieben: {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
