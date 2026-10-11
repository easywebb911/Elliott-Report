#!/usr/bin/env python3
"""Sekundäre Erfolgsregel „nicht invalidiert" — NACHTRÄGLICH definiert
(Easy-Entscheid, Variante B, 10./11.10.2026 — NACH Kenntnis des
Primärverdikts vom 06.09.2026 und der #121-Ergebnisse).

WAS DAS IST (und was nicht)
  Zone erreicht, Extension erreicht und gereift-neutral (Zeitablauf ohne
  Invalidierung) zählen hier POSITIV; nur „invalidiert" zählt NEGATIV. Das
  ist eine weichere Latte als die Primärwertung (`target_hit`) — sie macht
  die Erfolgsquote per Konstruktion größer, nie kleiner. Diese Zahl ist
  EXPLORATIV, ersetzt die Primärwertung nicht und fließt nirgendwo in
  Score/Filter/`evaluate.py` zurück.

HARTE GRENZEN (wie `evaluate_cluster_sensitivity.py`, Zeile für Zeile
übernommen)
  - läuft **nie** im Tageslauf (kein Aufruf in `.github/workflows/`, kein
    Import aus `elliott_pipeline`/`notify`/`health_check` — per Test
    abgesichert),
  - sendet **keinen** Push,
  - schreibt **nie** in `forward_collection.json`, **nie** in `report.json`
    und **nie** in `docs/validation_registry.md` oder `scripts/evaluate.py`
    (per Test abgesichert) — Ausgabe NUR auf die Konsole, optional zusätzlich
    in eine vom Aufrufer per `--out` benannte Datei,
  - läuft **nur auf Anfrage**, nie automatisch (analog #167),
  - die HARTE SPERRE aus PR #162 (keine `--live`-Markierung von
    `mark_stale_market_records.py`, keine offizielle Auswertung unter dieser
    Markierung) bleibt unberührt — dieses Skript liest nur, schreibt nichts
    in Datenfiles.

DIAGNOSE 10./11.10.2026 — WARUM EINE EIGENE SIMULATIONSFUNKTION NÖTIG IST
  `evaluate.simulate_hit`/`evaluate.benchmark_test` geben für die
  Zufalls-Baseline NUR ein einzelnes Bit zurück („Beobachtungszone zuerst erreicht,
  ja/nein") — die Information, ob ein Nicht-Treffer an einer Invalidierung
  oder an bloßem Zeitablauf lag, wird beim Rückgabewert verworfen. Die
  Erfolgsregel „nicht invalidiert" lässt sich deshalb NICHT durch einen
  unveränderten Aufruf der bestehenden Funktion abbilden, ohne
  `evaluate.py` selbst zu ändern (verboten, s. HARTE GRENZEN).
  Lösung: `simulate_nicht_invalidiert()` unten läuft exakt denselben Pfad
  wie `evaluate.simulate_hit` (dieselben relativen Abstände, derselbe
  Horizont, dieselbe Gleichstands-Regel — Gleichstand am selben Tag zählt
  als Invalidierung, Zeilen für Zeile wie `forward_collection.mature_record`
  Zeilen 269/274), gibt aber `1 - invalidiert` zurück statt `target_hit`.
  `evaluate.py` wird dabei an keiner Stelle verändert oder reimportiert mit
  anderer Bedeutung — reiner Parallel-Code, Eligibility (`_eligible_starts`)
  bleibt WIEDERVERWENDET, nicht nachgebaut.

POPULATION: WIEDERVERWENDET, nicht nachgebaut. `evaluate.build_population`
  liefert dieselben `_Case`-Objekte wie die Primärauswertung; jedes trägt
  das Original-Record unter `rec` — `rec["invalidated"]` ist exakt das
  Feld, das auch die Primärwertung (indirekt, über `target_hit`) nutzt.
  Keine zweite Populationsdefinition.

SETUP-TYP (W2/W4): `forward_collection._is_end_of_w4` WIEDERVERWENDET
  (identisch zu `evaluate.py`s eigenem `_is_end_of_w4 = fc._is_end_of_w4`,
  Zeile 427) — Pflicht-Stratifizierung laut PR #170 (08.10.2026-Ergänzung).

NEUTRAL-KOMPOSITION IST KEINE EIGENE TESTZELLE: „gereift · neutral" (nicht
  invalidiert UND nicht target_hit — reiner Zeitablauf) ist per Konstruktion
  eine TEILMENGE der „nicht invalidiert"-Positiven, keine unabhängige
  Vergleichsgruppe. Eine Quote „neutral vs. Zufall" wäre tautologisch (die
  Quote wäre immer 100 %) — deshalb wird die Aufteilung
  neutral/nicht-neutral NUR als Zusammensetzung der Positiven berichtet,
  OHNE eigenen p-Wert, und zählt NICHT in die FDR-Familie unten (die
  53/63 „gereift · neutral"-Fälle tragen laut GEPARKT-Eintrag 29.09.2026
  eine Selektionsverzerrung — s. `KOMPOSITIONS_WARNUNG`).

ZÄHLUNG DER GERECHNETEN AUSWERTUNGEN (Regel aus #169): JEDE Zelle, für die
  tatsächlich eine Quote UND ein p-Wert gegen die Zufalls-Baseline berechnet
  wird (gesamt, Ende W4, Ende W2 — sofern Kursbasis vorhanden UND
  n ≥ SECONDARY_MIN_N), zählt in die FDR-Familie. Benjamini-Hochberg
  (FDR_ALPHA, unten begründet) korrigiert NUR diese Familie — die
  Primärkriterien bleiben unverändert bei Holm in `evaluate.py`, keine
  Vermischung der beiden Verfahren.

FDR_ALPHA = 0,10: in diesem Repo bisher KEIN Benjamini-Hochberg-Code
  vorhanden (nachgeprüft, nichts zum Wiederverwenden) — dieser Wert ist eine
  eigene, hier erstmals getroffene, transparent benannte Wahl für diesen
  explorativen Rahmen (bewusst lockerer als `EVAL_ALPHA = 0,05` der
  Primär-Familie, wie für FDR-Verfahren in der Literatur üblich), KEINE
  Übernahme aus der Registry.

KURSBASIS: dieselbe Momentaufnahme-Datei wie `evaluate.py`
  (`data/eval_prices.json` — KORREKTUR 11.10.2026: entgegen einer früheren
  Aussage hier im Modul ist diese Datei NICHT durch `.gitignore` geschützt,
  nur durch Konvention nie committet; `.gitignore` deckt bisher nur
  `eval_prices_snapshot.json`/`data/forward_collection_sensitivity.json`
  ab — als Sicherheitsnetz in diesem PR nachgezogen). Fehlt die Datei oder
  ist sie ohne verwertbare Kurse (z. B. nach einem gescheiterten
  `--kurse-holen`-Versuch), meldet dieses Skript den Baseline-Vergleich —
  wie `evaluate.benchmark_test` — als „nicht durchführbar", bricht aber
  NICHT ab: die rohen Quoten werden trotzdem berichtet.

VERLUSTBILD (Easy-Entscheid, Variante A, 11.10.2026) — ZUSÄTZLICH zur
  Quote aus PR #176, NACHTRÄGLICH definiert, explorativ:
  - **Neutrale Fälle:** `rec["r_erreicht_basis"]` ist für gereift-neutrale
    Fälle bereits die `neutral_r`-Rechnung aus `forward_collection.
    mature_record` (Tag-10-Schlusskurs relativ zum Risiko) — WIEDER-
    VERWENDET, nicht neu berechnet. **Fragile Annahme, hier bewusst
    geprüft statt angenommen:** „< 0 heißt Verlust am Tag 10" stimmt NUR,
    weil `neutral_r` exakt `(Tag-10-Close - Entry) / Risiko` ist (Zeile
    328 dort) — ein negativer Wert bedeutet per Definition einen
    Schlusskurs unter dem Einstieg. Keine Mehrdeutigkeit, kein Mini-Stopp
    nötig.
  - **Gap-Messung bei Invalidierten:** eigener Tages-Scan über
    `price_path` (derselbe Tie-Break wie `simulate_nicht_invalidiert`
    oben: `close <= invalidation_price`), weil kein Feld im Record den
    tatsächlichen Schlusskurs am Invalidierungstag festhält (nur die
    harte Konvention `r_erreicht_basis = -1.0`). R-Definition
    WIEDERVERWENDET aus `forward_collection.py` Zeile 751/756
    (`risiko_abstand = entry_close - invalidation_price`, aus dem Record
    gelesen, nicht neu gerechnet). **Close-basiert, NICHT Intraday** —
    ein echter Intraday-Durchrutsch kann größer sein, als dieser
    Tages-Close zeigt; das wird in der Ausgabe ausdrücklich vermerkt.
  - **Stopp-gerissen-Baseline:** reines Komplement der bereits in diesem
    Skript gezogenen Zufalls-Verteilung (PR #176) — KEINE neue Simulation,
    keine neuen Ziehungen. „Zufalls-Quote invalidiert niedrig" ist
    dasselbe Ereignis wie „Zufalls-Quote nicht-invalidiert hoch" — der
    p-Wert aus `benchmark_nicht_invalidiert("gesamt")` wird unverändert
    übernommen, nur die angezeigten Quoten werden gespiegelt (1 - x).

CLUSTER-SENSITIVITÄT (Easy-Entscheid 11.10.2026, Anlass: Lauf 38149306463 —
  21,0 % vs. 15,2 %; 24/33 Invalidierungen teilen sich einen Kalendertag,
  32/33 eine ISO-Woche, 38/103 Ticker haben mehrere Kandidaten — die
  unabhängige Ziehung pro Fall in `benchmark_nicht_invalidiert` blendet das
  aus, exakt dieselbe bereits dokumentierte Lücke wie bei der Primär-
  Trefferquote, s. Diagnose 03.10.2026/#164 — Registry-Regel #166/#167
  schloss sie bisher NUR für die AUC, nicht für eine Quoten-Differenz).

  ÜBERTRAGUNG, NICHT KOPIE: Block-Bildung (`_bloecke`, Tag-/Ticker-Block)
  WIEDERVERWENDET aus `evaluate_cluster_sensitivity.py` (#166/#167) — per
  Import, keine zweite Implementierung. Das STATISTIK dort (AUC je Draw)
  passt nicht direkt: #166/#167 bootstrapped Scores/Labels für die AUC;
  hier gibt es stattdessen, je Fall, bereits einen vorgezogenen Pool
  möglicher Zufalls-Ausgänge (ein Eintrag je zulässigem zufälligem
  Einstiegstag im selben Ticker, aus `benchmark_nicht_invalidiert`
  ausgelagert in `_outcome_pools` — EINMAL berechnet, von beiden Zellen
  geteilt, teuerster Teil ist der Tage-Scan je Ticker). Die eigene
  Übertragung hier: je Bootstrap-Ziehung werden ganze Blöcke (Tag oder
  Ticker) von FÄLLEN gezogen (wie #166/#167), aber die Statistik je Draw
  ist die Differenz „beobachtete Quote − Zufalls-Quote" über die gezogenen
  Fälle (Zufalls-Anteil: je Fall EIN frischer Zug aus seinem eigenen Pool,
  nicht wiederverwendet über Draws). Fünf feste Seeds (20260728, 1, 42, 7,
  999, identisch zu #166/#167), 10.000 Ziehungen, CI-Niveau 0,975 —
  dieselben Werte, aber KEINE Übernahme der Registry-Vorgabe (die galt nur
  für die AUC): hier eine eigene, bewusst identisch gewählte Wiederholung
  der Parameter für Konsistenz der Berichtsform, s. Registry-Nachtrag.
  NUR Zelle „gesamt" — wie #166/#167 nur Population (a), keine
  Stratifizierung nach Setup-Typ (Umfangsbegrenzung, nicht Zufall).

  Stopp-gerissen-Variante: reine Spiegelung (Differenz × −1, CI-Grenzen
  vertauscht und gespiegelt) — KEINE zweite Bootstrap-Rechnung, aus
  demselben Grund wie `stopp_baseline()` oben (dasselbe Ereignis).

VERWENDUNG (nur manuell):
  python scripts/evaluate_nicht_invalidiert.py
      [--sammlung data/forward_collection.json] [--kurse data/eval_prices.json]
      [--out DATEI]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import repo_path  # noqa: F401 — legt Repo-Root + scripts/ auf sys.path

REPO_ROOT = repo_path.REPO_ROOT

import evaluate as ev  # noqa: E402 — NUR LESEND genutzt, s. Moduldoc oben
import evaluate_cluster_sensitivity as ecs  # noqa: E402 — NUR `_bloecke()`, s. Moduldoc
import forward_collection as fc  # noqa: E402
from numeric import finite  # noqa: E402

# ---------------------------------------------------------------------------
# Parameter — getrennt von evaluate.py's eigenen Konstanten (keine
# Übernahme, keine Veränderung dort).
# ---------------------------------------------------------------------------
BENCH_DRAWS = ev.BENCH_DRAWS
SECONDARY_MIN_N = ev.SECONDARY_MIN_N
EVAL_SEED = ev.EVAL_SEED
HORIZON_DAYS = ev.HORIZON_DAYS
FDR_ALPHA = 0.10  # eigene Wahl dieses Skripts, s. Moduldoc — KEIN Repo-Wert

# Cluster-Sensitivität (11.10.2026): dieselben Werte wie #166/#167, aber
# eigens hier gesetzt — s. Moduldoc „CLUSTER-SENSITIVITÄT" für die
# Begründung, warum das KEINE stille Übernahme der Registry-Vorgabe ist.
CLUSTER_BOOTSTRAP_DRAWS = 10_000
CLUSTER_CI_NIVEAU = 0.975
CLUSTER_SEEDS = (20260728, 1, 42, 7, 999)

_VERBOTENE_ZIELE = (
    "data/forward_collection.json",
    "data/report.json",
    "docs/validation_registry.md",
    "scripts/evaluate.py",
)

KOMPOSITIONS_WARNUNG = (
    "Die weichere Latte macht die Zahl besser, das ist kein Score-Beleg. "
    "Die neutralen Fälle (gereift, nicht invalidiert, nicht target_hit — "
    "reiner Zeitablauf) haben Selektionsverzerrung (GEPARKT-Eintrag "
    "29.09.2026, SESSION_HANDOVER.md): sie sind bereits durch Nichttreffen "
    "vorselektiert. Zusätzlich (Easy-Entscheid 11.10.2026): die Fälle sind "
    "nicht unabhängig — mehrere Kandidaten teilen sich Kalendertage/Wochen "
    "und Ticker; s. Cluster-Sensitivität weiter unten für die "
    "Intervallbreite unter dieser Annahme."
)

KOPFZEILE = (
    "NACHTRÄGLICH DEFINIERT (nach Kenntnis des Primärergebnisses vom "
    "06.09.2026) — explorativ, ersetzt die Primärwertung nicht."
)


# ---------------------------------------------------------------------------
# Simulation der Zufalls-Baseline — s. Moduldoc „DIAGNOSE" oben, warum dies
# NICHT `evaluate.simulate_hit` wiederverwenden kann.
# ---------------------------------------------------------------------------
def simulate_nicht_invalidiert(closes: Sequence[float], start: int,
                               ratio_target: float, ratio_inval: float,
                               horizon: int = HORIZON_DAYS) -> Optional[int]:
    """Exakt derselbe Pfad wie `evaluate.simulate_hit` (identische relative
    Abstände, Horizont, Gleichstands-Regel) — gibt `1 - invalidiert` zurück,
    nicht `target_hit`. None, wenn nicht genügend gültige Folge-Bars
    vorliegen (identisch zu `evaluate.simulate_hit`)."""
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
    invalidiert = 1 if (inval_day is not None
                       and (target_day is None or inval_day <= target_day)) else 0
    return 1 - invalidiert


def _outcome_pools(cases: Sequence[Dict], prices: Optional[Dict]
                   ) -> "tuple[List[Optional[List[int]]], str, str, List[str]]":
    """Je Fall die Liste möglicher Zufalls-Ausgänge (0/1) über alle
    zulässigen Einstiegstage im selben Ticker — EINMAL berechnet (teuerster
    Teil: der Tage-Scan je Ticker), von `benchmark_nicht_invalidiert` UND
    `cluster_sensitivitaet_nicht_invalidiert` geteilt, s. Moduldoc. `None`
    an der Stelle eines Falls ohne verwendbare Kurse — Liste bleibt
    1:1-ausgerichtet zu `cases`, nichts wird stillschweigend weggelassen."""
    von = min(c["first_seen_date"] for c in cases)
    bis = max(c["first_seen_date"] for c in cases)
    outcomes: List[Optional[List[int]]] = []
    ohne_kurse: List[str] = []
    for c in cases:
        ser = (prices or {}).get(c["ticker"])
        entry, tlow, inval = c["entry"], c["tlow"], c["inval"]
        if not ser or not all(finite(v) for v in (entry, tlow, inval)) or entry <= 0:
            ohne_kurse.append(c["ticker"])
            outcomes.append(None)
            continue
        dates, closes = ser.get("dates") or [], ser.get("closes") or []
        starts = ev._eligible_starts(dates, closes, von, bis)
        r_t, r_i = tlow / entry, inval / entry
        vals = [h for h in (simulate_nicht_invalidiert(closes, s, r_t, r_i)
                            for s in starts) if h is not None]
        if not vals:
            ohne_kurse.append(c["ticker"])
            outcomes.append(None)
            continue
        outcomes.append(vals)
    return outcomes, von, bis, ohne_kurse


def benchmark_nicht_invalidiert(cases: Sequence[Dict], prices: Optional[Dict],
                                rng: random.Random,
                                draws: int = BENCH_DRAWS) -> Dict:
    """Null-Verteilung der 'nicht invalidiert'-Quote — Struktur IDENTISCH zu
    `evaluate.benchmark_test` (gleicher Ticker, zufälliger Einstiegstag im
    selben Zeitraum, dieselben relativen Abstände, derselbe Horizont,
    Add-One-p-Wert), nur mit `simulate_nicht_invalidiert` statt
    `evaluate.simulate_hit`. `_eligible_starts` WIEDERVERWENDET."""
    beobachtet = (sum(1 - c["rec"]["invalidated"] for c in cases) / len(cases)
                 if cases else None)
    if not cases:
        return {"durchfuehrbar": False, "grund": "keine Fälle",
                "beobachtete_quote": None}
    if not prices:
        return {"durchfuehrbar": False,
                "grund": "keine Kursbasis (Momentaufnahme fehlt)",
                "beobachtete_quote": beobachtet}

    pools, von, bis, ohne_kurse = _outcome_pools(cases, prices)

    if ohne_kurse:
        return {"durchfuehrbar": False,
                "grund": f"Kursbasis unvollständig ({len(ohne_kurse)} von "
                         f"{len(cases)} Fällen ohne verwendbare Kurse)",
                "beobachtete_quote": beobachtet,
                "fehlende_ticker": sorted(set(ohne_kurse))}

    outcomes: List[List[int]] = pools  # keine None mehr, s. Guard oben
    n = len(outcomes)
    verteilung: List[float] = []
    for _ in range(draws):
        s = 0
        for vals in outcomes:
            s += vals[rng.randrange(len(vals))]
        verteilung.append(s / n)
    verteilung.sort()
    mind_so_hoch = sum(1 for v in verteilung if v >= beobachtet)
    p = (1 + mind_so_hoch) / (draws + 1)
    return {
        "durchfuehrbar": True,
        "beobachtete_quote": beobachtet,
        "zufalls_quote_mittel": sum(verteilung) / len(verteilung),
        "zufalls_quote_p05": ev._quantil(verteilung, 0.05),
        "zufalls_quote_p95": ev._quantil(verteilung, 0.95),
        "p_wert": p,
        "ziehungen": draws,
        "faelle": n,
        "treffer": sum(1 - c["rec"]["invalidated"] for c in cases),
        "zeitraum": {"von": von, "bis": bis},
    }


# ---------------------------------------------------------------------------
# Benjamini-Hochberg — nur für die explorative Sekundär-Familie dieses
# Skripts (s. Moduldoc FDR_ALPHA). KEIN Repo-Code zum Wiederverwenden.
# ---------------------------------------------------------------------------
def benjamini_hochberg(pvalues: Dict[str, float],
                       alpha: float = FDR_ALPHA) -> Dict[str, Dict]:
    """Standard-BH: größter Rang mit p <= (Rang/m)*alpha entscheidet, alle
    Ränge darunter gelten ebenfalls als signifikant."""
    m = len(pvalues)
    if m == 0:
        return {}
    geordnet = sorted(pvalues.items(), key=lambda kv: kv[1])
    schwellen = [(rang, key, p, (rang / m) * alpha)
                for rang, (key, p) in enumerate(geordnet, start=1)]
    signifikant_bis = max(
        (rang for rang, _key, p, schwelle in schwellen if p <= schwelle),
        default=0)
    return {
        key: {"p_wert": p, "rang": rang, "schwelle": schwelle,
             "signifikant": rang <= signifikant_bis}
        for rang, key, p, schwelle in schwellen
    }


# ---------------------------------------------------------------------------
# Stratifizierung + Komposition
# ---------------------------------------------------------------------------
def quote_nicht_invalidiert(cases: Sequence[Dict]) -> Optional[float]:
    if not cases:
        return None
    return sum(1 - c["rec"]["invalidated"] for c in cases) / len(cases)


def komposition(cases: Sequence[Dict]) -> Dict:
    """Zusammensetzung der 'nicht invalidiert'-Positiven: echte Beobachtungszonen-
    Treffer vs. gereift-neutral (reiner Zeitablauf). KEIN p-Wert — s.
    Moduldoc NEUTRAL-KOMPOSITION."""
    positive = [c for c in cases if not c["rec"]["invalidated"]]
    target_hit = sum(1 for c in positive if c["hit"])
    neutral = len(positive) - target_hit
    return {
        "positive_gesamt": len(positive),
        "davon_target_hit": target_hit,
        "davon_neutral": neutral,
        "warnung": KOMPOSITIONS_WARNUNG,
    }


def stratifizieren(cases: Sequence[Dict]) -> Dict[str, List[Dict]]:
    """Pflicht-Stratifizierung Setup-Typ (PR #170, 08.10.2026) —
    `forward_collection._is_end_of_w4` WIEDERVERWENDET."""
    w4 = [c for c in cases if fc._is_end_of_w4(c["rec"])]
    w2 = [c for c in cases if not fc._is_end_of_w4(c["rec"])]
    return {"gesamt": list(cases), "Ende W4": w4, "Ende W2": w2}


# ---------------------------------------------------------------------------
# VERLUSTBILD (Easy-Entscheid, Variante A, 11.10.2026) — s. Moduldoc.
# ---------------------------------------------------------------------------
def neutrale_faelle(cases: Sequence[Dict]) -> List[Dict]:
    """Gereift-neutral: nicht invalidiert UND nicht target_hit (reiner
    Zeitablauf) — dieselbe Definition wie `komposition()`."""
    return [c for c in cases if not c["rec"]["invalidated"] and not c["hit"]]


def neutral_verlustbild(cases: Sequence[Dict],
                        min_n: int = SECONDARY_MIN_N) -> Dict:
    """Verlustbild der gereift-neutralen Fälle über `r_erreicht_basis`
    (= `neutral_r` aus `forward_collection.mature_record`, Zeile 328:
    Tag-10-Close relativ zum Risiko) — WIEDERVERWENDET, nicht neu
    gerechnet. Strikt `< 0` für 'im Minus' (Randfall `== 0` separat
    ausgewiesen, s. Moduldoc fragile Annahme)."""
    neutral = neutrale_faelle(cases)
    werte = [c["rec"].get("r_erreicht_basis") for c in neutral]
    werte = [w for w in werte if w is not None]
    if not werte:
        return {"faelle": len(neutral), "mit_messwert": 0, "hinweis": "keine Fälle"}
    sortiert = sorted(werte)
    n = len(sortiert)
    median = (sortiert[n // 2] if n % 2 == 1 else
             (sortiert[n // 2 - 1] + sortiert[n // 2]) / 2)
    eintrag = {
        "faelle": len(neutral),
        "mit_messwert": n,
        "im_minus_strikt": sum(1 for w in werte if w < 0),
        "genau_null": sum(1 for w in werte if w == 0),
        "im_plus_strikt": sum(1 for w in werte if w > 0),
        "mittelwert": sum(werte) / n,
        "median": median,
    }
    if n < min_n:
        eintrag["hinweis"] = "zu wenige Fälle (< SECONDARY_MIN_N) — nicht interpretieren"
    return eintrag


def ziel_treffer_unter_einstieg(cases: Sequence[Dict]) -> Dict:
    """Von den echten Zielzonen-Treffern (`target_hit=1`): wie viele
    liegen am Tag 10 (letzter `price_path`-Close) UNTER dem Einstieg?
    Reine Zusatz-Information — fließt NICHT in eine Quote ein (Auftrag
    Teil 1b: 'nur ausweisen, nicht in die Quote mischen')."""
    treffer = [c for c in cases if c["hit"] and not c["rec"]["invalidated"]]
    mit_pfad = [c for c in treffer
               if (c["rec"].get("price_path") and c["rec"].get("entry_close") is not None)]
    unter_einstieg = sum(
        1 for c in mit_pfad
        if c["rec"]["price_path"][-1]["close"] < c["rec"]["entry_close"])
    return {"zielzonen_treffer": len(treffer), "mit_tag10_daten": len(mit_pfad),
           "unter_einstieg_am_tag_10": unter_einstieg}


def gesamt_verlustbild(cases: Sequence[Dict]) -> Dict:
    """Anteil 'invalidiert ODER neutral-im-Minus' an der Gesamtpopulation —
    die Kehrseite der 79,0-%-Quote aus PR #176."""
    n = len(cases)
    invalidiert = sum(1 for c in cases if c["rec"]["invalidated"])
    neutral_minus = sum(
        1 for c in neutrale_faelle(cases)
        if (c["rec"].get("r_erreicht_basis") or 0) < 0
        and c["rec"].get("r_erreicht_basis") is not None)
    anzahl = invalidiert + neutral_minus
    return {
        "n": n, "invalidiert": invalidiert, "neutral_im_minus": neutral_minus,
        "anzahl": anzahl, "anteil": anzahl / n if n else None,
    }


def gap_messung(cases: Sequence[Dict]) -> Dict:
    """Close-basierte Durchrutsch-Messung bei den invalidierten Fällen:
    erster Tag in `price_path` mit `close <= invalidation_price` (gleicher
    Tie-Break wie `simulate_nicht_invalidiert`), Close gegenüber der Marke
    in Prozent UND in R (`risiko_abstand` aus dem Record, Zeile 751/756
    `forward_collection.py` — WIEDERVERWENDET). NICHT Intraday."""
    invalidiert = [c for c in cases if c["rec"]["invalidated"]]
    prozent_werte: List[float] = []
    r_werte: List[float] = []
    durchrutscht = 0
    genau_auf_marke = 0
    ohne_messwert = 0
    for c in invalidiert:
        rec = c["rec"]
        inval_price = rec.get("invalidation_price")
        pfad = rec.get("price_path") or []
        risiko = rec.get("risiko_abstand")
        if inval_price is None or not pfad:
            ohne_messwert += 1
            continue
        gap_close = None
        for tag in pfad:
            close = tag.get("close")
            if close is not None and close <= inval_price:
                gap_close = close
                break
        if gap_close is None:
            ohne_messwert += 1
            continue
        prozent = (gap_close - inval_price) / inval_price * 100
        prozent_werte.append(prozent)
        if gap_close < inval_price:
            durchrutscht += 1
        else:
            genau_auf_marke += 1
        if risiko and finite(risiko) and risiko > 0 and rec.get("entry_close") is not None:
            r_werte.append((gap_close - rec["entry_close"]) / risiko)
    def _median(xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        s = sorted(xs)
        m = len(s)
        return s[m // 2] if m % 2 == 1 else (s[m // 2 - 1] + s[m // 2]) / 2
    return {
        "faelle_gesamt": len(invalidiert),
        "mit_messwert": len(prozent_werte),
        "ohne_messwert": ohne_messwert,
        "durchrutscht": durchrutscht,
        "genau_auf_marke": genau_auf_marke,
        "median_prozent": _median(prozent_werte),
        "maximum_prozent": min(prozent_werte) if prozent_werte else None,  # "Maximum" = größter Durchrutsch = kleinster (negativster) Wert
        "median_r": _median(r_werte),
        "r_faelle": len(r_werte),
        "hinweis": "Close-basiert, NICHT Intraday — ein echter Durchrutsch "
                  "kann größer sein als dieser Tages-Close zeigt.",
    }


def stopp_baseline(bench_gesamt: Dict) -> Dict:
    """Stopp-gerissen-Quote als reines Komplement der bereits gezogenen
    Zufalls-Verteilung (KEINE neue Simulation, s. Moduldoc). 'Zufalls-Quote
    invalidiert niedrig' ist dasselbe Ereignis wie 'Zufalls-Quote
    nicht-invalidiert hoch' — der p-Wert wird unverändert übernommen."""
    if not bench_gesamt.get("durchfuehrbar"):
        return {"durchfuehrbar": False, "grund": bench_gesamt.get("grund")}
    return {
        "durchfuehrbar": True,
        "beobachtete_quote": 1 - bench_gesamt["beobachtete_quote"],
        "zufalls_quote_mittel": 1 - bench_gesamt["zufalls_quote_mittel"],
        "zufalls_quote_p05": 1 - bench_gesamt["zufalls_quote_p95"],
        "zufalls_quote_p95": 1 - bench_gesamt["zufalls_quote_p05"],
        "p_wert": bench_gesamt["p_wert"],
        "p_wert_hinweis": "identisch zum p-Wert von 'nicht invalidiert' "
                         "(gesamt) — dasselbe Ereignis gespiegelt, keine "
                         "zweite Ziehung.",
        "ziehungen": bench_gesamt["ziehungen"],
        "faelle": bench_gesamt["faelle"],
    }


# ---------------------------------------------------------------------------
# CLUSTER-SENSITIVITÄT (Easy-Entscheid 11.10.2026) — s. Moduldoc
# "CLUSTER-SENSITIVITÄT" für die Begründung der Übertragung aus #166/#167.
# ---------------------------------------------------------------------------
_CLUSTER_BLOCK_FELDER = (("Tag-Block", "first_seen_date"), ("Ticker-Block", "ticker"))


def cluster_sensitivitaet_nicht_invalidiert(
        cases: Sequence[Dict], prices: Optional[Dict], *,
        seeds: Sequence[int] = CLUSTER_SEEDS,
        draws: int = CLUSTER_BOOTSTRAP_DRAWS,
        ci_level: float = CLUSTER_CI_NIVEAU) -> Dict:
    """Block-Bootstrap (Tag-/Ticker-Block, `evaluate_cluster_sensitivity.
    _bloecke` WIEDERVERWENDET) auf die Differenz 'beobachtete Quote minus
    Zufalls-Quote'. NUR Zelle 'gesamt' (Umfangsbegrenzung wie #166/#167).
    Punktschätzung EINMAL auf den echten Fällen (Zufalls-Seite als
    Pool-Mittelwert, nicht eine einzelne Ziehung — deterministisch, kein
    Seed nötig dafür); die Bootstrap-Verteilung bestimmt NUR das
    Konfidenzintervall um diese Differenz."""
    if not cases:
        return {"durchfuehrbar": False, "grund": "keine Fälle"}
    if not prices:
        return {"durchfuehrbar": False,
                "grund": "keine Kursbasis (Momentaufnahme fehlt)"}

    pools, _von, _bis, ohne_kurse = _outcome_pools(cases, prices)
    if ohne_kurse:
        return {"durchfuehrbar": False,
                "grund": f"Kursbasis unvollständig ({len(ohne_kurse)} von "
                         f"{len(cases)} Fällen ohne verwendbare Kurse)"}

    nutzbar = list(zip(cases, pools))  # keine None mehr, s. Guard oben
    n = len(nutzbar)
    pool_by_id = {id(c): p for c, p in nutzbar}
    beobachtete_quote_punkt = sum(1 - c["rec"]["invalidated"] for c, _ in nutzbar) / n
    zufalls_mittel_punkt = sum(sum(p) / len(p) for _c, p in nutzbar) / n
    diff_punkt = beobachtete_quote_punkt - zufalls_mittel_punkt

    alpha = 1.0 - ci_level
    ergebnisse: Dict[str, Dict[int, Dict]] = {}
    for feld_name, feld in _CLUSTER_BLOCK_FELDER:
        bloecke = ecs._bloecke([c for c, _ in nutzbar], feld)
        keys = sorted(bloecke)
        k = len(keys)
        je_seed: Dict[int, Dict] = {}
        for seed in seeds:
            rng = random.Random(seed)
            diffs: List[float] = []
            for _ in range(draws):
                gezogene_keys = [keys[rng.randrange(k)] for _ in range(k)]
                resampled: List[Dict] = []
                for key in gezogene_keys:
                    resampled.extend(bloecke[key])
                m = len(resampled)
                beob = sum(1 - c["rec"]["invalidated"] for c in resampled) / m
                basis = sum(
                    (p := pool_by_id[id(c)])[rng.randrange(len(p))]
                    for c in resampled) / m
                diffs.append(beob - basis)
            diffs.sort()
            je_seed[seed] = {
                "ci_untergrenze": ev._quantil(diffs, alpha / 2),
                "ci_obergrenze": ev._quantil(diffs, 1 - alpha / 2),
                "schliesst_0_ein": (ev._quantil(diffs, alpha / 2) <= 0
                                    <= ev._quantil(diffs, 1 - alpha / 2)),
            }
        ergebnisse[feld_name] = {
            "cluster_anzahl": k, "je_seed": je_seed,
        }

    return {
        "durchfuehrbar": True,
        "diff_punkt": diff_punkt,
        "beobachtete_quote": beobachtete_quote_punkt,
        "zufalls_mittel": zufalls_mittel_punkt,
        "faelle": n,
        "ziehungen": draws,
        "ci_niveau": ci_level,
        "seeds": list(seeds),
        "bloecke": ergebnisse,
    }


def cluster_sensitivitaet_stopp_gerissen(ni_ergebnis: Dict) -> Dict:
    """Stopp-gerissen-Spiegelung — KEINE zweite Bootstrap-Rechnung (s.
    Moduldoc, derselbe Grund wie `stopp_baseline`): Differenz × −1,
    CI-Grenzen vertauscht und gespiegelt."""
    if not ni_ergebnis.get("durchfuehrbar"):
        return {"durchfuehrbar": False, "grund": ni_ergebnis.get("grund")}
    gespiegelt: Dict[str, Dict] = {}
    for feld_name, eintrag in ni_ergebnis["bloecke"].items():
        je_seed = {
            seed: {
                "ci_untergrenze": -werte["ci_obergrenze"],
                "ci_obergrenze": -werte["ci_untergrenze"],
                "schliesst_0_ein": werte["schliesst_0_ein"],
            }
            for seed, werte in eintrag["je_seed"].items()
        }
        gespiegelt[feld_name] = {"cluster_anzahl": eintrag["cluster_anzahl"],
                                 "je_seed": je_seed}
    return {
        "durchfuehrbar": True,
        "diff_punkt": -ni_ergebnis["diff_punkt"],
        "beobachtete_quote": 1 - ni_ergebnis["beobachtete_quote"],
        "zufalls_mittel": 1 - ni_ergebnis["zufalls_mittel"],
        "faelle": ni_ergebnis["faelle"],
        "ziehungen": ni_ergebnis["ziehungen"],
        "ci_niveau": ni_ergebnis["ci_niveau"],
        "seeds": ni_ergebnis["seeds"],
        "bloecke": gespiegelt,
    }


# ---------------------------------------------------------------------------
# Bericht
# ---------------------------------------------------------------------------
def berechne(cases: Sequence[Dict], prices: Optional[Dict],
            seed: int = EVAL_SEED, draws: int = BENCH_DRAWS) -> Dict:
    strata = stratifizieren(cases)
    rng = random.Random(seed)
    zellen: Dict[str, Dict] = {}
    gerechnet = 0
    p_werte: Dict[str, float] = {}
    for name, teilmenge in strata.items():
        quote = quote_nicht_invalidiert(teilmenge)
        eintrag: Dict = {"faelle": len(teilmenge), "quote": quote}
        if len(teilmenge) < SECONDARY_MIN_N:
            eintrag["hinweis"] = "zu wenige Fälle (< SECONDARY_MIN_N)"
            eintrag["baseline"] = None
        else:
            bench = benchmark_nicht_invalidiert(teilmenge, prices, rng, draws)
            eintrag["baseline"] = bench
            if bench.get("durchfuehrbar"):
                gerechnet += 1
                p_werte[name] = bench["p_wert"]
        zellen[name] = eintrag
    fdr = benjamini_hochberg(p_werte) if p_werte else {}

    bench_gesamt = zellen["gesamt"].get("baseline") or {"durchfuehrbar": False,
                                                        "grund": "keine Fälle"}

    return {
        "kopfzeile": KOPFZEILE,
        "zaehlwerk": {
            "gesamt_faelle": len(cases),
            "zellen_insgesamt": len(strata),
            "gerechnete_auswertungen": gerechnet,
            "hinweis": f"{len(strata)} Zellen betrachtet (gesamt, Ende W4, "
                      f"Ende W2), davon {gerechnet} mit tatsächlich "
                      f"berechnetem p-Wert gegen die Zufalls-Baseline — "
                      f"FDR gilt NUR für diese {gerechnet}. Zusätzlich: "
                      f"Cluster-Sensitivität (Block-Bootstrap nach Tag und "
                      f"nach Ticker, {len(CLUSTER_SEEDS)} Seeds) NUR für "
                      f"Zelle 'gesamt' — s. unten.",
        },
        "zellen": zellen,
        "fdr_benjamini_hochberg": {"alpha": FDR_ALPHA, "ergebnis": fdr},
        "komposition": komposition(cases),
        "verlustbild": {
            "neutral_gesamt": neutral_verlustbild(cases),
            "neutral_ende_w4": neutral_verlustbild(strata["Ende W4"]),
            "neutral_ende_w2": neutral_verlustbild(strata["Ende W2"]),
            "zielzonen_treffer_unter_einstieg": ziel_treffer_unter_einstieg(cases),
            "gesamt_verlustbild": gesamt_verlustbild(cases),
            "gap_messung": gap_messung(cases),
            "stopp_baseline": stopp_baseline(bench_gesamt),
        },
        "cluster_sensitivitaet": _cluster_sensitivitaet_bericht(cases, prices),
        "seed": seed,
        "warnung": KOMPOSITIONS_WARNUNG,
    }


def _cluster_sensitivitaet_bericht(cases: Sequence[Dict],
                                   prices: Optional[Dict]) -> Dict:
    ni = cluster_sensitivitaet_nicht_invalidiert(cases, prices)
    return {"nicht_invalidiert": ni,
           "stopp_gerissen": cluster_sensitivitaet_stopp_gerissen(ni)}


def _pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{x * 100:.1f} %"


def render_text(res: Dict, primaer_trefferquote: Optional[float],
                primaer_n: Optional[int],
                heute_target_hit_quote: Optional[float],
                heute_n: int) -> str:
    z: List[str] = []
    z.append(res["kopfzeile"])
    z.append("=" * len(res["kopfzeile"]))
    z.append("")
    z.append(f"Seed: {res['seed']}")
    z.append(res["zaehlwerk"]["hinweis"])
    z.append("")
    z.append(f"Primärzahl (eingefrorene Auswertung vom 06.09.2026): "
             f"{_pct(primaer_trefferquote)} bei n={primaer_n}.")
    z.append(f"Explorativ, zum Vergleich daneben — ANDERE FALLBASIS, KEIN "
             f"VERGLEICH, KEIN VERDIKT: heutige Trefferquote nach "
             f"Primärregel (target_hit) {_pct(heute_target_hit_quote)} "
             f"bei n={heute_n}.")
    z.append("")
    for name in ("gesamt", "Ende W4", "Ende W2"):
        zelle = res["zellen"][name]
        z.append(f"--- {name} (n={zelle['faelle']}) ---")
        z.append(f"  Quote 'nicht invalidiert': {_pct(zelle['quote'])}")
        if zelle.get("hinweis"):
            z.append(f"  {zelle['hinweis']}")
        elif zelle["baseline"] and not zelle["baseline"].get("durchfuehrbar"):
            z.append(f"  Zufalls-Baseline nicht durchführbar: "
                     f"{zelle['baseline']['grund']}")
        elif zelle["baseline"]:
            b = zelle["baseline"]
            z.append(f"  Zufalls-Baseline: Mittel {_pct(b['zufalls_quote_mittel'])} "
                     f"(5.–95. Perzentil {_pct(b['zufalls_quote_p05'])}–"
                     f"{_pct(b['zufalls_quote_p95'])}), p={b['p_wert']:.4f}, "
                     f"Differenz {_pct(zelle['quote'] - b['zufalls_quote_mittel'])}")
            fdr_eintrag = res["fdr_benjamini_hochberg"]["ergebnis"].get(name)
            if fdr_eintrag:
                z.append(f"  FDR (Benjamini-Hochberg, alpha="
                         f"{res['fdr_benjamini_hochberg']['alpha']}): "
                         f"Rang {fdr_eintrag['rang']}, "
                         f"signifikant={fdr_eintrag['signifikant']}")
        z.append("")
    k = res["komposition"]
    z.append(f"Zusammensetzung der {k['positive_gesamt']} 'nicht "
            f"invalidiert'-Fälle: {k['davon_target_hit']} echte "
            f"Beobachtungszonen-Treffer, {k['davon_neutral']} gereift-neutral "
            f"(reiner Zeitablauf).")
    z.append("")
    z.append(f"WARNUNG: {res['warnung']}")
    z.append("")

    v = res["verlustbild"]
    z.append("=== VERLUSTBILD (Easy-Entscheid Variante A, 11.10.2026) ===")
    z.append("")

    gv = v["gesamt_verlustbild"]
    z.append(f"Gesamt-Verlustbild: {gv['anzahl']} von {gv['n']} "
            f"({_pct(gv['anteil'])}) sind invalidiert ODER gereift-neutral "
            f"im Minus am Tag 10 — invalidiert: {gv['invalidiert']}, "
            f"neutral-im-Minus: {gv['neutral_im_minus']}. Zum Vergleich "
            f"direkt daneben: 'nicht invalidiert' (PR #176) = "
            f"{_pct(res['zellen']['gesamt']['quote'])}.")

    zt = v["zielzonen_treffer_unter_einstieg"]
    z.append(f"Von den {zt['zielzonen_treffer']} echten "
            f"Beobachtungszonen-Treffern liegen {zt['unter_einstieg_am_tag_10']} "
            f"(von {zt['mit_tag10_daten']} mit Tag-10-Daten) am Tag 10 "
            f"UNTER dem Einstieg — nur ausgewiesen, NICHT in eine Quote "
            f"gemischt.")
    z.append("")

    for label, key in (("gesamt", "neutral_gesamt"), ("Ende W4", "neutral_ende_w4"),
                       ("Ende W2", "neutral_ende_w2")):
        nv = v[key]
        z.append(f"--- Neutrale Fälle, {label} (n={nv['faelle']}) ---")
        if nv.get("mit_messwert", 0) == 0:
            z.append(f"  {nv.get('hinweis', 'keine Fälle')}")
            z.append("")
            continue
        z.append(f"  im Minus (< 0): {nv['im_minus_strikt']}, "
                f"genau 0: {nv['genau_null']}, im Plus (> 0): "
                f"{nv['im_plus_strikt']} — Mittel {nv['mittelwert']:.3f} R, "
                f"Median {nv['median']:.3f} R")
        if nv.get("hinweis"):
            z.append(f"  {nv['hinweis']}")
        z.append("")

    gm = v["gap_messung"]
    z.append(f"--- Gap-Messung Invalidierte (n={gm['faelle_gesamt']}, "
            f"{gm['mit_messwert']} mit Messwert, {gm['ohne_messwert']} "
            f"ohne) ---")
    if gm["mit_messwert"]:
        z.append(f"  Durchrutsch (Close < Marke): {gm['durchrutscht']}, "
                f"genau auf Marke: {gm['genau_auf_marke']}")
        z.append(f"  Median {gm['median_prozent']:.2f} %, größter "
                f"Durchrutsch {gm['maximum_prozent']:.2f} % "
                f"(Close-basiert, NICHT Intraday)")
        if gm["median_r"] is not None:
            z.append(f"  In R (risiko_abstand): Median {gm['median_r']:.3f} "
                    f"({gm['r_faelle']} Fälle mit gültigem Risiko)")
    z.append(f"  {gm['hinweis']}")
    z.append("")

    sb = v["stopp_baseline"]
    z.append("--- Stopp-gerissen-Quote (Komplement der Baseline oben) ---")
    if not sb.get("durchfuehrbar"):
        z.append(f"  Zufalls-Baseline nicht durchführbar: {sb.get('grund')}")
    else:
        z.append(f"  Beobachtet {_pct(sb['beobachtete_quote'])}, Zufalls-Mittel "
                f"{_pct(sb['zufalls_quote_mittel'])} (5.–95. Perzentil "
                f"{_pct(sb['zufalls_quote_p05'])}–{_pct(sb['zufalls_quote_p95'])}), "
                f"p={sb['p_wert']:.4f} ({sb['p_wert_hinweis']})")
    z.append("")

    cs = res["cluster_sensitivitaet"]
    z.append("=== CLUSTER-SENSITIVITÄT (Easy-Entscheid 11.10.2026) ===")
    z.append("Anlass: Stopp-gerissen 21,0 % gegen Zufalls-Mittel 15,2 % "
             "(Lauf 38149306463) — Kandidaten teilen sich Kalendertage/"
             "Wochen und Ticker. Block-Bootstrap nach Registry-Regel "
             "#166/#167, übertragen auf die Differenz 'beobachtet minus "
             "Zufall'. Zeigt nur die Breite des Intervalls unter der "
             "Cluster-Annahme — KEIN VERDIKT.")
    z.append("")
    for titel, key in (("'nicht invalidiert'", "nicht_invalidiert"),
                       ("Stopp-gerissen (gespiegelt, keine zweite "
                        "Bootstrap-Rechnung)", "stopp_gerissen")):
        eintrag = cs[key]
        z.append(f"--- {titel} ---")
        if not eintrag.get("durchfuehrbar"):
            z.append(f"  nicht durchführbar: {eintrag.get('grund')}")
            z.append("")
            continue
        z.append(f"  Punktschätzung Differenz (beobachtet minus Zufall): "
                 f"{_pct(eintrag['diff_punkt'])} (beobachtet "
                 f"{_pct(eintrag['beobachtete_quote'])}, Zufalls-Mittel "
                 f"{_pct(eintrag['zufalls_mittel'])}, n={eintrag['faelle']}, "
                 f"{eintrag['ziehungen']} Ziehungen je Seed)")
        for feld_name, block_eintrag in eintrag["bloecke"].items():
            z.append(f"  {feld_name} ({block_eintrag['cluster_anzahl']} "
                     f"Cluster):")
            for seed, werte in block_eintrag["je_seed"].items():
                z.append(f"    Seed {seed}: CI "
                         f"[{_pct(werte['ci_untergrenze'])}, "
                         f"{_pct(werte['ci_obergrenze'])}] — Intervall "
                         f"schließt 0 ein: "
                         f"{'ja' if werte['schliesst_0_ein'] else 'nein'}")
        z.append("")

    return "\n".join(z)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Sekundäre Erfolgsregel 'nicht invalidiert' "
                    "(Easy-Entscheid, Variante B). Nur lesend, nur manuell, "
                    "schreibt nie ins Repo.")
    ap.add_argument("--sammlung", default="data/forward_collection.json")
    ap.add_argument("--kurse", default="data/eval_prices.json",
                    help="Momentaufnahme für den Zufalls-Benchmark "
                         "(dieselbe Datei wie evaluate.py)")
    ap.add_argument("--primaer", default="data/evaluation/ergebnis.json",
                    help="Für die Vergleichs-Trefferquote (nur Anzeige)")
    ap.add_argument("--seed", type=int, default=EVAL_SEED)
    ap.add_argument("--out", default=None,
                    help="Zusätzlich den Bericht in diese Datei schreiben "
                         "(Konsole bleibt immer bedient).")
    args = ap.parse_args(argv)

    if args.out:
        out_aufgeloest = (REPO_ROOT / args.out).resolve()
        for verboten in _VERBOTENE_ZIELE:
            if out_aufgeloest == (REPO_ROOT / verboten).resolve():
                print(f"[evaluate_nicht_invalidiert] VERWEIGERT: --out "
                     f"zeigt auf eine geschützte Projektdatei ({verboten}) "
                     f"— das darf dieses Skript nie beschreiben.",
                     file=sys.stderr)
                return 2

    sammlung_pfad = REPO_ROOT / args.sammlung
    coll = json.loads(sammlung_pfad.read_text(encoding="utf-8"))
    cases, zaehlwerk = ev.build_population(coll)

    kurse_pfad = REPO_ROOT / args.kurse
    prices_payload = (json.loads(kurse_pfad.read_text(encoding="utf-8"))
                      if kurse_pfad.exists() else None)
    prices = (prices_payload or {}).get("kurse") if prices_payload else None

    primaer_trefferquote = None
    primaer_n = None
    primaer_pfad = REPO_ROOT / args.primaer
    if primaer_pfad.exists():
        try:
            primaer = json.loads(primaer_pfad.read_text(encoding="utf-8"))
            primaer_trefferquote = (
                primaer.get("primaer", {})
                      .get("trefferquote_vs_zufall", {})
                      .get("beobachtete_quote"))
            primaer_n = primaer.get("zaehlwerk", {}).get("auswertbar")
        except (json.JSONDecodeError, OSError):
            primaer_trefferquote = None

    heute_n = len(cases)
    heute_target_hit_quote = (sum(c["hit"] for c in cases) / heute_n
                              if heute_n else None)

    res = berechne(cases, prices, seed=args.seed)
    res["auswertbare_population"] = zaehlwerk
    text = render_text(res, primaer_trefferquote, primaer_n,
                       heute_target_hit_quote, heute_n)
    print(text)
    if args.out:
        out_aufgeloest.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
