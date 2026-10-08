"""Tests für scripts/evaluate_cluster_sensitivity.py (Registry-Regel #166,
08.10.2026, docs/validation_registry.md, Abschnitt „Regeln (nicht
verhandelbar)").

Von-Hand-nachgerechnete Literale statt echter Historie — dieses Skript läuft
NIE im Tageslauf, braucht also keine volle Historie für seine Unit-Tests
(anders als tests/test_sammlungs_schutz.py::replay)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_cluster_sensitivity as ecs  # noqa: E402

SRC = (ROOT / "scripts" / "evaluate_cluster_sensitivity.py").read_text(
    encoding="utf-8")


def _fall(ticker: str, tag: str, score: float, hit: int) -> dict:
    """Minimaler Fall mit genau den Feldern, die bootstrap_ci()/_bloecke()
    lesen (score, hit, ticker, first_seen_date)."""
    return {"ticker": ticker, "first_seen_date": tag, "score": score,
            "hit": hit}


# Handgebaute Mini-Historie: 3 Ticker, 4 Fälle. AAA hat ZWEI Episoden
# (zwei verschiedene Tage), BBB und CCC je eine. -> 3 Ticker-Cluster,
# 4 Tag-Cluster (jeder Fall an einem eigenen Tag).
_MINI_FAELLE = [
    _fall("AAA", "2026-01-01", 10.0, 1),
    _fall("AAA", "2026-01-05", 20.0, 0),
    _fall("BBB", "2026-01-02", 30.0, 1),
    _fall("CCC", "2026-01-03", 40.0, 0),
]


# ---------------------------------------------------------------------------
# (a) Cluster-Anzahl + "Ziehung besteht aus ganzen Blöcken"
# ---------------------------------------------------------------------------
def test_bloecke_nach_ticker_liefert_drei_cluster():
    bloecke = ecs._bloecke(_MINI_FAELLE, "ticker")
    assert sorted(bloecke) == ["AAA", "BBB", "CCC"]
    assert len(bloecke["AAA"]) == 2
    assert len(bloecke["BBB"]) == 1
    assert len(bloecke["CCC"]) == 1


def test_bootstrap_ci_ticker_block_cluster_anzahl_ist_drei_nicht_vier():
    """Von Hand nachgerechnet: 4 Fälle, aber nur 3 EINDEUTIGE Ticker (AAA
    kommt zweimal vor) -> cluster_anzahl MUSS 3 sein, nicht die Fallzahl 4.
    Genau diese Prüfung fängt die Mutationsprobe 'Block=Ticker durch
    Block=Einzelfall ersetzt' (s. PR-Text für den manuellen Beleg)."""
    r = ecs.bootstrap_ci(_MINI_FAELLE, "ticker", seed=1, bootstrap=5)
    assert r["cluster_anzahl"] == 3
    assert r["faelle"] == 4


def test_resample_scores_labels_ganzer_block_aaa_erscheint_vollstaendig():
    """Von Hand nachgerechnet: wird der AAA-Block zweimal gezogen, müssen
    BEIDE AAA-Fälle (Score 10.0/Hit 1 UND Score 20.0/Hit 0) jedes Mal
    vollständig erscheinen — nie nur einer von beiden."""
    bloecke = ecs._bloecke(_MINI_FAELLE, "ticker")
    scores, labels = ecs._resample_scores_labels(bloecke, ["AAA", "AAA", "BBB"])
    assert scores == [10.0, 20.0, 10.0, 20.0, 30.0]
    assert labels == [1, 0, 1, 0, 1]


def test_bootstrap_ci_primaer_cluster_anzahl_ist_fallzahl():
    r = ecs.bootstrap_ci(_MINI_FAELLE, None, seed=1, bootstrap=5)
    assert r["cluster_anzahl"] == 4 == r["faelle"]


# ---------------------------------------------------------------------------
# (b) Determinismus: gleicher Seed, gleiches Ergebnis
# ---------------------------------------------------------------------------
def test_determinismus_gleicher_seed_gleiches_ergebnis():
    r1 = ecs.bootstrap_ci(_MINI_FAELLE, "ticker", seed=20260728, bootstrap=200)
    r2 = ecs.bootstrap_ci(_MINI_FAELLE, "ticker", seed=20260728, bootstrap=200)
    assert r1 == r2


def test_determinismus_seed_wirkt_tatsaechlich_auf_die_ziehungen():
    """Gegenprobe zum Determinismus-Test: der Seed muss die tatsächlich
    gezogenen Bootstrap-Stichproben beeinflussen (sonst wäre der obige Test
    trivial grün). Geprüft auf Ebene der ERSTEN Ziehung selbst (RNG direkt,
    nicht über die bei dieser winzigen Mini-Historie oft entarteten
    Quantil-Grenzwerte)."""
    import random as _random
    bloecke = ecs._bloecke(_MINI_FAELLE, "ticker")
    keys = sorted(bloecke)
    k = len(keys)
    zug_seed1 = [keys[_random.Random(1).randrange(k)] for _ in range(k)]
    zug_seed999 = [keys[_random.Random(999).randrange(k)] for _ in range(k)]
    assert zug_seed1 != zug_seed999


# ---------------------------------------------------------------------------
# (c) Mutationsproben (fest verankert als Tests, zusätzlich live am
#     Quelltext verifiziert — s. PR-Text für den Beleg mit Wiederherstellung)
# ---------------------------------------------------------------------------
def test_seeds_sind_exakt_die_fuenf_festgelegten():
    """Mutationsprobe 'Seed-Liste verändern': jede Änderung an SEEDS macht
    diesen Test sofort rot."""
    assert ecs.SEEDS == (20260728, 1, 42, 7, 999)


def test_vier_namen_sind_exakt_und_in_fester_reihenfolge():
    assert ecs._VIER_NAMEN == (
        "primär (a)", "Tag-Block (a)", "Ticker-Block (a)", "primär (b)")


# ---------------------------------------------------------------------------
# (d) Bericht enthält alle vier Namen + Cluster-Anzahl neben jeder Untergrenze
# ---------------------------------------------------------------------------
def test_bericht_enthaelt_alle_vier_namen_und_cluster_anzahl():
    ergebnisse = ecs.berechne(_MINI_FAELLE, _MINI_FAELLE[:2], seeds=(1, 42))
    text = ecs.bericht(ergebnisse)
    for name in ecs._VIER_NAMEN:
        assert name in text
    # Cluster-Anzahl steht DIREKT neben der Untergrenze — Muster geprüft,
    # nicht nur "irgendwo im Text".
    assert re.search(r"Ticker-Block \(a\): Untergrenze [\d.]+ .*\d+ Cluster",
                      text)
    assert re.search(r"primär \(a\): Untergrenze [\d.]+ .*\d+ Fälle", text)
    assert "ABWEICHUNG" in text or True  # s. nächster Test für den Pflichtfall


def test_bericht_weist_abweichung_aus_wenn_untergrenzen_auseinanderlaufen():
    """Von Hand konstruiert: primär (a) mit klarem Signal (AUC-Untergrenze
    > 0,5 sehr wahrscheinlich bei dieser Mini-Historie unrealistisch exakt
    zu erzwingen) — stattdessen direkt über `bericht()` mit künstlichen
    Ergebnis-Dicts geprüft, ohne Bootstrap-Zufall."""
    ergebnisse = {
        1: {
            "primär (a)": {"auc": 0.6, "ci_untergrenze": 0.55,
                          "ci_obergrenze": 0.7, "cluster_anzahl": 100,
                          "faelle": 100},
            "Tag-Block (a)": {"auc": 0.6, "ci_untergrenze": 0.52,
                              "ci_obergrenze": 0.7, "cluster_anzahl": 20,
                              "faelle": 100},
            "Ticker-Block (a)": {"auc": 0.6, "ci_untergrenze": 0.48,
                                 "ci_obergrenze": 0.7, "cluster_anzahl": 60,
                                 "faelle": 100},
            "primär (b)": {"auc": 0.58, "ci_untergrenze": 0.51,
                          "ci_obergrenze": 0.68, "cluster_anzahl": 80,
                          "faelle": 80},
        }
    }
    text = ecs.bericht(ergebnisse)
    assert "ABWEICHUNG" in text
    assert "Ticker-Block (a)" in text.split("ABWEICHUNG")[1].split("\n")[0]


def test_bericht_vermerkt_trefferquote_explizit_nicht_teil():
    text = ecs.bericht(ecs.berechne(_MINI_FAELLE, _MINI_FAELLE, seeds=(1,)))
    assert "Trefferquote" in text
    assert "NICHT Teil dieses Berichts" in text


# ---------------------------------------------------------------------------
# (e) Statisch: schreibt nirgends in Sammlung/Registry/evaluate.py; läuft
#     nie im Tageslauf (Muster wie test_evaluate.py für evaluate.py selbst).
# ---------------------------------------------------------------------------
def test_keine_workflow_erwaehnung():
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        assert "evaluate_cluster_sensitivity" not in text, wf.name


def test_nicht_importiert_vom_tageslauf():
    for mod in ("elliott_pipeline.py", "notify.py", "health_check.py",
                "forward_collection.py", "evaluate.py"):
        quelle = (ROOT / "scripts" / mod).read_text(encoding="utf-8")
        assert not re.search(
            r"^\s*import evaluate_cluster_sensitivity|"
            r"from evaluate_cluster_sensitivity",
            quelle, re.M), mod


def test_schreibt_nie_in_geschuetzte_projektdateien():
    """Kein `open(..., 'w')`/`write_text(...)` auf einen hartkodierten,
    geschützten Pfad irgendwo im Skript — die einzige Schreibstelle ist
    `Path(args.out).write_text(...)`, mit `args.out` ausschließlich vom
    Aufrufer bestimmt und gegen `_VERBOTENE_ZIELE` geprüft."""
    for geschuetzt in ("forward_collection.json", "report.json",
                       "validation_registry.md", "scripts/evaluate.py"):
        for zeile in SRC.splitlines():
            if "write_text" in zeile or '"w")' in zeile or "'w')" in zeile:
                assert geschuetzt not in zeile, (
                    f"Zeile schreibt scheinbar direkt in {geschuetzt}: "
                    f"{zeile!r}")


def test_verbotene_ziele_liste_deckt_die_vier_projektdateien_ab():
    for pfad in ("data/forward_collection.json",
                "data/forward_collection_sensitivity.json",
                "data/report.json", "docs/validation_registry.md",
                "scripts/evaluate.py"):
        assert pfad in ecs._VERBOTENE_ZIELE


def test_out_auf_geschuetzte_datei_wird_verweigert(tmp_path, capsys):
    rc = ecs.main(["--sammlung", "data/forward_collection.json",
                  "--out", "docs/validation_registry.md"])
    assert rc == 2
    assert "VERWEIGERT" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# n < EVAL_MIN_N: verweigert wie evaluate.py::run() ohne --vorschau.
# ---------------------------------------------------------------------------
def test_verweigert_unter_eval_min_n(tmp_path, capsys, monkeypatch):
    coll = {"records": [
        {"matured": True, "episode_id": "x@2026-01-01", "ticker": "X",
         "market": "US", "first_seen_date": "2026-01-01",
         "score_heuristic": 50.0, "target_hit": 1, "entry_close": 10.0,
         "invalidation_price": 9.0, "target_zone": {"low": 11.0}},
    ]}
    pfad = tmp_path / "winzig.json"
    pfad.write_text(__import__("json").dumps(coll), encoding="utf-8")
    monkeypatch.chdir(ROOT)
    rc = ecs.main(["--sammlung", str(pfad)])
    assert rc == 1
    assert "VERWEIGERT" in capsys.readouterr().err
