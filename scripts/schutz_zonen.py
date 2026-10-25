#!/usr/bin/env python3
"""Geschützte Zonen — EINE Quelle (Auftrag 3 von 6, Easy-Entscheid
24./25.10.2026, Schritt-0-Inventur + Easy-Entscheidung zum Mini-Stopp
25.10.2026, OPTION 4 — Schutz-Sperre OHNE Freigabe-Label).

Reine Datenhaltung, KEINE Logik. Zwei Konsumenten lesen diese Liste:

  - `scripts/schutz_sperre.py` (neuer PR-Check): ein Treffer ist IMMER rot,
    ohne Ausnahme, unabhängig von Label/Titel.
  - `scripts/proactive_watcher.py::beruehrt_rote_linie` (Agenten-Selbst-
    beschränkung): strenger als die Sperre — ALLES Unbekannte gilt dort
    zusätzlich als rote Linie (Default-Deny), diese Liste liefert nur die
    explizit benannten Treffer, die beide Konsumenten EINHEITLICH sehen
    müssen (das behebt den Schritt-0b-Befund: vorher behandelte
    `proactive_watcher` jede ``.md``-Datei — auch `docs/validation_registry.md`
    — als „nie rote Linie"; das ist falsch und hier korrigiert).

`config.py` steht hier BEWUSST NICHT als ganze Datei in `GESCHUETZTE_DATEIEN`
(anders als bei `proactive_watcher`, das die Datei weiterhin vollständig
sperrt — gröber, aber nicht falsch, keine Änderung dort). `schutz_sperre.py`
prüft `config.py` stattdessen auf Zeilen-/Symbol-Ebene gegen
`GESCHUETZTE_CONFIG_KONSTANTEN` (siehe Moduldoc dort) — eine FEINERE,
zusätzliche Prüfung, kein Widerspruch zur gröberen Datei-Sperre anderswo.
"""
from __future__ import annotations

# Datei-Ebene: ein Treffer auf einen dieser Pfade (angelegt, geändert,
# umbenannt VON oder NACH, gelöscht, oder als Symlink/Typechange betroffen)
# ist immer ein Zonen-Treffer.
GESCHUETZTE_DATEIEN = frozenset({
    # Score/Ranking/Signal + Filter/Zählregel (überwiegend dieselbe Datei)
    "scripts/elliott_pipeline.py",
    "scripts/rules.py",
    "scripts/zigzag.py",
    "scripts/in_session.py",
    # Push-/Alarm-Entscheidung
    "scripts/health_check.py",
    "scripts/notify.py",
    # Auswertung
    "scripts/evaluate.py",
    "scripts/evaluate_cluster_sensitivity.py",
    "scripts/evaluate_nicht_invalidiert.py",
    "scripts/auswertung_stichtage.py",
    "scripts/filter_sensitivity_sammlung.py",
    "docs/validation_registry.md",
    # Daten + Record-Schreibweg
    "data/forward_collection.json",
    "docs/data/forward_collection.json",
    "scripts/forward_collection.py",
    "scripts/mark_episode_splits.py",
    "scripts/mark_in_session_creation.py",
    "scripts/mark_stale_market_records.py",
    "scripts/mark_invertiertes_risiko_anlage.py",
    # Die Sperre selbst (darf sich nicht selbst freischalten)
    "scripts/schutz_sperre.py",
    "scripts/schutz_zonen.py",
    "tests/test_schutz_sperre.py",
})

# Verzeichnis-Präfixe, die VOLLSTÄNDIG geschützt sind — jede Datei darunter,
# unabhängig vom Namen.
GESCHUETZTE_VERZEICHNIS_PRAEFIXE = (
    ".github/workflows/",
)

# config.py: NUR diese Konstanten sind geschützt (Symbol-Ebene). Wörtlich aus
# Schritt 0a: "Score-Berechnung, Invalidierungs-Bonus, Fib-Bonus,
# SETUP_BASE_POINTS, SCORE_WEIGHTS, INVALIDATION_DISTANCE_* (Live UND
# Schatten), Ranking-Sortierung, TOP_N" + "Push-Gating, Schwellen
# (min_candidates, bar_lag_crit, WARN_REPEAT_RUNS, max_fetch_error_pct)".
GESCHUETZTE_CONFIG_KONSTANTEN = frozenset({
    "SCORE_WEIGHTS",
    "SETUP_BASE_POINTS",
    "FIB_PROXIMITY_MAX_BONUS",
    "FIB_PROXIMITY_TOLERANCE",
    "INVALIDATION_DISTANCE_MAX_BONUS",
    "INVALIDATION_DISTANCE_CAP",
    "INVALIDATION_DISTANCE_SHADOW_MAX_BONUS",
    "INVALIDATION_DISTANCE_SHADOW_CAP",
    "TOP_N",
    "HEALTH_MIN_CANDIDATES",
    "HEALTH_MAX_FETCH_ERROR_PCT",
    "HEALTH_WARN_REPEAT_RUNS",
    "HEALTH_BAR_LAG_CRIT",
})

CONFIG_DATEI = "config.py"
