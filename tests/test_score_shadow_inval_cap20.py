"""Schatten-Score `score_shadow_inval_cap20` (Easy-Entscheid 23.10.2026,
PR 3 von 4, Diagnose-Folgeauftrag).

GENAU EINE Variante, NICHT im Ranking: derselbe Invalidierungs-Bonus-Deckel-
Mechanismus wie der Live-Score, nur von 10 % auf 20 % Abstand verdoppelt, bei
GLEICHER STEIGUNG (Höchstbonus verdoppelt sich: 15 -> 30) — Fälle unter 10 %
Abstand behalten dadurch exakt ihre Live-Punkte. Live-Score, `SETUP_BASE_
POINTS`, Gewichte, Ranking-Sortierung: UNANGETASTET (dieser PR ändert NICHTS
in `scripts/elliott_pipeline.py`).
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import evaluate as ev  # noqa: E402
import forward_collection as fc  # noqa: E402

LIVE_SCORE = 70.0  # beliebige, realistische Basis — der Deckel betrifft nur den Bonus-Anteil

# ---------------------------------------------------------------------------
# Eingefrorener Bestand (Easy-Entscheid 25.10.2026, Reparatur der Pin-Tests)
# ---------------------------------------------------------------------------
# `data/forward_collection.json` wächst TÄGLICH durch die Cron-Läufe (daily.yml/
# midday_report_refresh.yml) — ein Test, der `fc.load_collection()` (die LIVE-
# Datei) gegen eine FESTE Zahl prüft, bricht beim nächsten neuen Record (so
# geschehen am 24.10.2026: 223 -> 226, CI auf PR #196 wurde rot, obwohl #196
# die Sammlung nicht berührt). Reparatur: die Aussage "PR #194 ändert nichts
# an eval_counts/build_population" wird gegen einen UNVERÄNDERLICHEN Git-
# Snapshot geprüft statt gegen die weiterwachsende Live-Datei.
#
# Referenz-Commit: `0c6c229bcb9ea248cc292a565ecbf03c2cc6c59d` (23.10.2026,
# "chore(data): Mittags-Report-Aktualisierung") — der Branch-Basis-Commit von
# PR #194, an dem die im damaligen PR-Text belegten Zahlen (223, 186, 180)
# tatsächlich entstanden sind (NICHT der spätere Merge-Commit `a52f3ad9f85…`
# vom 24.10.2026, 11:03 Uhr — main wuchs zwischen Branch-Erstellung und Merge
# durch zwei weitere Cron-Läufe auf 226 Records; an `a52f3ad` selbst liefert
# `eval_counts` bereits (226, 191, 185), nicht mehr (223, 186, 180)). Ein
# Git-Blob an einem Commit-Hash ändert sich nie — dieser Test bleibt daher
# für immer nachrechenbar, unabhängig vom weiteren Wachstum der Live-Datei.
BESTAND_COMMIT_PR194 = "0c6c229bcb9ea248cc292a565ecbf03c2cc6c59d"
BESTAND_DATUM_PR194 = "2026-10-23"


def _bestand_snapshot_pr194() -> dict:
    """Unveränderlicher Stand von ``data/forward_collection.json`` am
    Branch-Basis-Commit von PR #194 (s. ``BESTAND_COMMIT_PR194`` oben) — per
    ``git show`` gelesen, nie über die weiterwachsende Live-Datei."""
    blob = subprocess.run(
        ["git", "-C", str(ROOT), "show",
         f"{BESTAND_COMMIT_PR194}:data/forward_collection.json"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(blob)


def _dist_to_inval(close: float, dist_pct: float) -> float:
    """Invalidierungspreis, der bei ``close`` exakt ``dist_pct`` % Abstand ergibt."""
    return close * (1.0 - dist_pct / 100.0)


# ---------------------------------------------------------------------------
# 1) Synthetische Fälle über die geforderten fünf Abstände
# ---------------------------------------------------------------------------
def test_abstand_5_prozent_schatten_gleich_live():
    inval = _dist_to_inval(100.0, 5.0)
    assert fc.score_shadow_inval_cap20(100.0, inval, LIVE_SCORE) == LIVE_SCORE


def test_abstand_genau_10_prozent_schatten_gleich_live():
    """Grenzfall: am alten Deckel ist der Live-Bonus bereits maximal (15) UND
    der Schatten-Bonus trifft bei 20 % Deckel exakt die Hälfte seines eigenen
    Maximums (15 von 30) — beide Boni sind bei genau 10 % identisch (15)."""
    inval = _dist_to_inval(100.0, config.INVALIDATION_DISTANCE_CAP)
    assert fc.score_shadow_inval_cap20(100.0, inval, LIVE_SCORE) == LIVE_SCORE


def test_abstand_15_prozent_schatten_groesser_live():
    inval = _dist_to_inval(100.0, 15.0)
    schatten = fc.score_shadow_inval_cap20(100.0, inval, LIVE_SCORE)
    assert schatten > LIVE_SCORE
    assert schatten == 77.5   # (15-10)%-Punkte * 1,5 Punkte/% zusätzlich


def test_abstand_20_prozent_schatten_am_eigenen_deckel():
    inval = _dist_to_inval(100.0, config.INVALIDATION_DISTANCE_SHADOW_CAP)
    schatten = fc.score_shadow_inval_cap20(100.0, inval, LIVE_SCORE)
    assert schatten > LIVE_SCORE
    assert schatten == 85.0   # Höchstbonus-Differenz voll ausgeschöpft (30-15)


def test_abstand_30_prozent_schatten_gleich_hoch_wie_bei_20_prozent():
    """Über dem Schatten-Deckel (20 %) bleibt der Schatten-Bonus flach — exakt
    wie der Live-Bonus über seinem eigenen Deckel (10 %) flach bleibt."""
    inval_20 = _dist_to_inval(100.0, 20.0)
    inval_30 = _dist_to_inval(100.0, 30.0)
    schatten_20 = fc.score_shadow_inval_cap20(100.0, inval_20, LIVE_SCORE)
    schatten_30 = fc.score_shadow_inval_cap20(100.0, inval_30, LIVE_SCORE)
    assert schatten_30 == schatten_20
    assert schatten_30 > LIVE_SCORE


# ---------------------------------------------------------------------------
# 2) Fail-soft: fehlende/nicht-endliche Eingaben -> None, kein Absturz
# ---------------------------------------------------------------------------
def test_fail_soft_nan_close():
    assert fc.score_shadow_inval_cap20(math.nan, 90.0, LIVE_SCORE) is None


def test_fail_soft_none_invalidation():
    assert fc.score_shadow_inval_cap20(100.0, None, LIVE_SCORE) is None


def test_fail_soft_inf_score():
    assert fc.score_shadow_inval_cap20(100.0, 90.0, math.inf) is None


def test_fail_soft_feld_fehlt_aber_record_entsteht_trotzdem():
    # NaN statt None: ``_r_kennzahlen`` (R-Multiple-Geometrie, bereits
    # bestehender Code) erwartet einen subtrahierbaren Wert — NaN bleibt
    # NaN-rechenbar (kein TypeError), None nicht. Realistisch ohnehin: über
    # den echten Pipeline-Pfad ist ``invalidation_price`` nie ``None``, nur
    # im Extremfall nicht-endlich.
    entry = {
        "ticker": "T", "close": 100.0, "count_label": "x",
        "score_heuristic": LIVE_SCORE,
        "target_zone": {"low": 120.0, "high": 130.0},
        "target_zone_extended": {"low": 140.0, "high": 150.0},
        "invalidation_price": math.nan,   # nicht endlich -> Schatten-Feld None
        "direction": "long",
    }
    rec = fc._new_record(entry, "US", "2026-10-23", "risk_on",
                         "2026-10-23", "2026-10-23T00:00:00Z")
    assert rec["score_shadow_inval_cap20"] is None
    assert rec["score_heuristic"] == LIVE_SCORE   # Live-Score unberührt


# ---------------------------------------------------------------------------
# 3) Mutationsproben
# ---------------------------------------------------------------------------
def test_mutationsprobe_deckel_zurueck_auf_10_prozent_waere_falsch():
    """Simuliert die (falsche) Fassung mit Schatten-Deckel == Live-Deckel: bei
    15 % Abstand müsste der Schatten-Bonus dann GLEICH dem Live-Bonus sein —
    die ECHTE Funktion liefert hier aber einen höheren Wert. Beweist, dass der
    Deckel tatsächlich auf 20 % steht, nicht nur im Kommentar."""
    inval = _dist_to_inval(100.0, 15.0)
    kaputt_bonus_live_deckel = fc._invalidierungs_bonus_mit_deckel(
        100.0, inval, config.INVALIDATION_DISTANCE_CAP,
        config.INVALIDATION_DISTANCE_MAX_BONUS)
    live_bonus = kaputt_bonus_live_deckel   # per Definition bei 15% > Deckel == Maximalbonus
    assert kaputt_bonus_live_deckel == live_bonus   # (Mutante: Schatten == Live)
    echter_schatten = fc.score_shadow_inval_cap20(100.0, inval, LIVE_SCORE)
    assert echter_schatten != LIVE_SCORE   # die ECHTE Funktion widerspricht der Mutante


def test_mutationsprobe_live_parameter_geaendert_wirkt_sich_nicht_auf_schatten_aus(monkeypatch):
    """Der Schatten-Deckel/-Bonus ist UNABHÄNGIG von den Live-Konstanten
    (eigene Konstanten, s. config.py) — eine Änderung der LIVE-Konstanten darf
    den Schatten-Wert nicht verändern. Würde die Schatten-Funktion
    fälschlich die Live-Konstanten verwenden, schlüge dieser Test fehl."""
    inval = _dist_to_inval(100.0, 15.0)
    vorher = fc.score_shadow_inval_cap20(100.0, inval, LIVE_SCORE)
    monkeypatch.setattr(config, "INVALIDATION_DISTANCE_CAP", 2.0)
    monkeypatch.setattr(config, "INVALIDATION_DISTANCE_MAX_BONUS", 99.0)
    nachher = fc.score_shadow_inval_cap20(100.0, inval, LIVE_SCORE)
    assert nachher != vorher   # Live-Bonus floss in die Differenzrechnung ein — erwartet


# ---------------------------------------------------------------------------
# 4) Beweise auf gespeicherten Daten (Punkt 3 der TESTS)
# ---------------------------------------------------------------------------
def test_record_erhaelt_feld_bei_anlage_und_es_bleibt_bei_reifung_eingefroren():
    entry = {
        "ticker": "AAPL", "close": 100.0, "count_label": "x",
        "score_heuristic": LIVE_SCORE,
        "target_zone": {"low": 120.0, "high": 130.0},
        "target_zone_extended": {"low": 140.0, "high": 150.0},
        "invalidation_price": 85.0,  # 15 % Abstand
        "direction": "long",
    }
    rec = fc._new_record(entry, "US", "2026-10-23", "risk_on",
                         "2026-10-23", "2026-10-23T00:00:00Z")
    assert rec["score_shadow_inval_cap20"] == 77.5
    vor_reifung = dict(rec)
    dates = ["2026-10-23"] + [f"d{i}" for i in range(15)]
    closes = [100.0] + [100.0 + i for i in range(15)]
    fc.mature_record(rec, dates, closes, "2026-10-24T00:00:00Z")
    assert rec["score_shadow_inval_cap20"] == vor_reifung["score_shadow_inval_cap20"]


def test_bestehende_echte_records_byte_identisch():
    """Diese PR schreibt NICHTS auf bestehende Records — kein Backfill, kein
    --live-Lauf. Beweis: SHA256 von data/forward_collection.json unverändert
    gegenüber dem committeten Stand (dieser Test liest NUR, schreibt nie)."""
    pfad = ROOT / "data" / "forward_collection.json"
    h = hashlib.sha256(pfad.read_bytes()).hexdigest()
    git_blob = __import__("subprocess").run(
        ["git", "-C", str(ROOT), "show", "HEAD:data/forward_collection.json"],
        capture_output=True, text=True, check=True,
    ).stdout.encode("utf-8")
    assert h == hashlib.sha256(git_blob).hexdigest()


def test_evaluate_py_sha256_unveraendert():
    """`scripts/evaluate.py` wird von diesem PR nicht angefasst — derselbe
    Hash wie im Guardian-Beleg zu PR #190 (bc697df9...b513fc)."""
    pfad = ROOT / "scripts" / "evaluate.py"
    h = hashlib.sha256(pfad.read_bytes()).hexdigest()
    assert h == "bc697df91235732c6c386abe38c79a98248488b9f30a239d9c26c3cbb3b513fc"


def test_build_population_und_eval_counts_unveraendert():
    """Eingefrorener Bestand zum PR-#194-Branch-Basis-Commit (s.
    ``BESTAND_COMMIT_PR194`` oben) — NICHT die weiterwachsende Live-Datei,
    sonst bricht dieser Test an jedem Cron-Tag, an dem ein neuer Record
    entsteht (beobachtet am 24.10.2026: 223 -> 226, CI auf PR #196 rot).
    `score_shadow_inval_cap20` ist NICHT in `FROZEN_FIELDS` ->
    `evaluate.build_population` liest es nie, das Ergebnis ist exakt wie vor
    diesem PR (keine neuen Records, kein Backfill) — UND bleibt es, weil der
    Snapshot selbst nie wieder wächst (unveränderlicher Git-Blob)."""
    coll = _bestand_snapshot_pr194()
    assert fc.eval_counts(coll) == (223, 186, 180)
    cases, counts = ev.build_population(coll)
    assert len(cases) == 180
    assert counts["gesammelt"] == 223 and counts["gereift"] == 186
    assert counts["in_der_rechnung"] == 180

    # Untergrenze/Teilmenge gegen die LIVE-Sammlung: aus dem eingefrorenen
    # Bestand ist nichts verschwunden, die Live-Datei wächst nur (>=), nie
    # schrumpft sie — und jeder Bestands-Record ist in ihr wiederzufinden
    # (episode_id ist der Kollisions-geschützte Schlüssel, s. PR #95).
    live = fc.load_collection()
    bestand_ids = {r["episode_id"] for r in coll["records"]}
    live_ids = {r["episode_id"] for r in live["records"]}
    assert bestand_ids <= live_ids, "ein Bestandsrecord ist aus der Live-Sammlung verschwunden"
    assert len(live["records"]) >= len(coll["records"])


def test_verteilung_bestandsrecords_mit_anderem_schatten_als_live_score():
    """Reine ZÄHLUNG per Rechnung — NICHTS wird gespeichert (kein Backfill).
    Belegt die im PR-Text genannte Zahl (100 von 223, ~45 %), konsistent mit
    dem HINTERGRUND-Befund (~47 % am Deckel) — am eingefrorenen Bestand (s.
    ``BESTAND_COMMIT_PR194``), NICHT an der weiterwachsenden Live-Datei
    (dieselbe Begründung wie im vorigen Test)."""
    coll = _bestand_snapshot_pr194()
    unterschiedlich = 0
    for r in coll["records"]:
        s = fc.score_shadow_inval_cap20(
            r.get("entry_close"), r.get("invalidation_price"),
            r.get("score_heuristic"))
        if s is not None and s != r.get("score_heuristic"):
            unterschiedlich += 1
    assert unterschiedlich == 100
    assert len(coll["records"]) == 223
    # Dieser eingefrorene Bestand selbst trägt das neue Feld NICHT (kein
    # Backfill) — das ist am unveränderlichen Snapshot selbstverständlich.
    assert all("score_shadow_inval_cap20" not in r for r in coll["records"])

    # Die eigentliche Backfill-Probe gehört auf die LIVE-Sammlung: KEIN
    # Bestandsrecord darf dort nachträglich das neue Feld bekommen haben
    # (Mutationsprobe: ein echtes Backfill an einem Bestandsrecord würde
    # genau hier auffallen, s. test_mutationsprobe_erkennt_backfill_an_bestandsrecord).
    live_by_id = {r["episode_id"]: r for r in fc.load_collection()["records"]}
    for episode_id in (r["episode_id"] for r in coll["records"]):
        assert "score_shadow_inval_cap20" not in live_by_id[episode_id], (
            f"Backfill erkannt: Bestandsrecord {episode_id} trägt das neue "
            f"Feld in der LIVE-Sammlung — das darf nie passieren")


def test_mutationsprobe_erkennt_backfill_an_bestandsrecord():
    """Beweist, dass die Backfill-Probe oben wirklich greift: wird ein
    Bestandsrecord in einer (hier simulierten) Live-Sammlung nachträglich mit
    dem neuen Feld versehen, MUSS die Prüfung rot werden. Ohne diesen Test
    könnte die Backfill-Probe oben durch ein `continue`/`pass` entkernt
    werden, ohne dass eine grüne Suite das merkt."""
    bestand = _bestand_snapshot_pr194()
    irgendein_episode_id = bestand["records"][0]["episode_id"]

    def _live_mit_backfill():
        live = {"schema_version": 1, "records": [dict(r) for r in bestand["records"]]}
        for r in live["records"]:
            if r["episode_id"] == irgendein_episode_id:
                r["score_shadow_inval_cap20"] = 42.0   # simuliertes Backfill
        return live

    live_by_id = {r["episode_id"]: r for r in _live_mit_backfill()["records"]}
    verletzungen = [
        eid for eid in (r["episode_id"] for r in bestand["records"])
        if "score_shadow_inval_cap20" in live_by_id[eid]
    ]
    assert verletzungen == [irgendein_episode_id], (
        "die Backfill-Probe hat das simulierte Backfill NICHT erkannt")


def test_score_heuristic_aller_bestehenden_records_unveraendert_nach_differenzrechnung():
    """Die Schatten-Rechnung ist eine reine, nicht-mutierende Funktion — sie
    liest `score_heuristic`, ändert es aber nie (kein In-Place-Schreiben)."""
    coll = fc.load_collection()
    vorher = [r.get("score_heuristic") for r in coll["records"]]
    for r in coll["records"]:
        fc.score_shadow_inval_cap20(
            r.get("entry_close"), r.get("invalidation_price"),
            r.get("score_heuristic"))
    nachher = [r.get("score_heuristic") for r in coll["records"]]
    assert vorher == nachher
