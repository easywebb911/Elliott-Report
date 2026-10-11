"""Tests für scripts/evaluate_nicht_invalidiert.py (Easy-Entscheid Variante B,
10./11.10.2026). Handgebaute Fixtures statt echter Historie — dieses Skript
läuft NIE im Tageslauf."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate as ev  # noqa: E402
import evaluate_nicht_invalidiert as eni  # noqa: E402

SRC = (ROOT / "scripts" / "evaluate_nicht_invalidiert.py").read_text(
    encoding="utf-8")


def _case(ticker: str, invalidated: int, target_hit: int, end_of_w4: bool,
         stale: bool = False) -> dict:
    """Minimaler Fall — genau die Felder, die dieses Skript liest
    (`rec["invalidated"]`, `c["hit"]`, `c["rec"]` für `_is_end_of_w4`)."""
    rec = {
        "invalidated": invalidated, "target_hit": target_hit,
        "count_wave_labels": (
            [{"index": 0, "wave": 0}, {"index": 1, "wave": 4}] if end_of_w4
            else [{"index": 0, "wave": 0}, {"index": 1, "wave": 2}]),
    }
    if stale:
        rec["stale_market_suspect"] = True
    return {"ticker": ticker, "rec": rec, "hit": target_hit,
           "first_seen_date": "2026-01-01"}


# ---------------------------------------------------------------------------
# (1) Status-Fixtures — jeder vorkommende Wert, positiv/negativ
# ---------------------------------------------------------------------------
# A: Zone erreicht (target_hit=1, invalidated=0) -> positiv
_A_ZONE = _case("A", invalidated=0, target_hit=1, end_of_w4=True)
# B: gereift-neutral (invalidated=0, target_hit=0) -> positiv
_B_NEUTRAL = _case("B", invalidated=0, target_hit=0, end_of_w4=False)
# C: invalidiert -> negativ
_C_INVAL = _case("C", invalidated=1, target_hit=0, end_of_w4=True)
# D: zweiter neutraler Fall, Ende W2
_D_NEUTRAL = _case("D", invalidated=0, target_hit=0, end_of_w4=False)
# E (Randfall): stale-markiert, aber sonst normaler Treffer — Marker darf
# die Quote NICHT beeinflussen (dieses Skript liest ihn nirgendwo).
_E_STALE_ZONE = _case("E", invalidated=0, target_hit=1, end_of_w4=True,
                     stale=True)

_ALLE_FAELLE = [_A_ZONE, _B_NEUTRAL, _C_INVAL, _D_NEUTRAL, _E_STALE_ZONE]


def test_quote_nicht_invalidiert_zaehlt_zone_extension_neutral_positiv():
    """4 von 5 Fällen sind 'nicht invalidiert' (A, B, D, E) — nur C ist
    invalidiert und zählt negativ."""
    assert eni.quote_nicht_invalidiert(_ALLE_FAELLE) == 4 / 5


def test_quote_leere_liste_gibt_none():
    assert eni.quote_nicht_invalidiert([]) is None


def test_stale_markierter_fall_aendert_die_quote_nicht():
    """Randfall: `stale_market_suspect` wird von diesem Skript nirgendwo
    gelesen — ein stale-markierter Treffer zählt identisch zu einem
    unmarkierten Treffer."""
    ohne_marker = eni.quote_nicht_invalidiert([_A_ZONE])
    mit_marker = eni.quote_nicht_invalidiert([_E_STALE_ZONE])
    assert ohne_marker == mit_marker == 1.0


def test_komposition_trennt_target_hit_von_neutral():
    k = eni.komposition(_ALLE_FAELLE)
    assert k["positive_gesamt"] == 4
    assert k["davon_target_hit"] == 2  # A, E
    assert k["davon_neutral"] == 2     # B, D
    assert "Selektionsverzerrung" in k["warnung"]


def test_stratifizieren_trennt_w4_w2():
    strata = eni.stratifizieren(_ALLE_FAELLE)
    assert {c["ticker"] for c in strata["Ende W4"]} == {"A", "C", "E"}
    assert {c["ticker"] for c in strata["Ende W2"]} == {"B", "D"}
    assert strata["gesamt"] == _ALLE_FAELLE


# ---------------------------------------------------------------------------
# (2) Randfall "Zone UND invalidiert" — per Tie-Break ausgeschlossen:
# Gleichstand am selben Tag (target_day == inval_day) zählt als
# Invalidierung, NIE als Treffer (identisch zu forward_collection.py
# Zeile 269/274).
# ---------------------------------------------------------------------------
def test_simulate_nicht_invalidiert_gleichstand_zaehlt_als_invalidiert():
    # entry=100, tlow=90 (ratio 0.9), inval=90 (ratio 0.9) — Tag 0 erreicht
    # BEIDE Schwellen gleichzeitig (Close == 90). HORIZON_DAYS=10 Folge-Bars
    # nötig, alle flach bei 95 danach.
    closes = [100.0, 90.0] + [95.0] * 15
    r = eni.simulate_nicht_invalidiert(closes, 0, ratio_target=0.9,
                                       ratio_inval=0.9, horizon=10)
    assert r == 0  # 0 = invalidiert (NICHT 'nicht invalidiert')


def test_simulate_nicht_invalidiert_echter_treffer_vor_invalidierung():
    closes = [100.0, 95.0, 110.0] + [105.0] * 15  # Tag1 Zone, erst danach fiele es
    r = eni.simulate_nicht_invalidiert(closes, 0, ratio_target=1.05,
                                       ratio_inval=0.9, horizon=10)
    assert r == 1  # Zone erreicht, nie invalidiert -> 'nicht invalidiert'


def test_simulate_nicht_invalidiert_neutral_ohne_bewegung():
    closes = [100.0] + [100.0] * 15  # weder Zone (105) noch Invalidierung (90)
    r = eni.simulate_nicht_invalidiert(closes, 0, ratio_target=1.05,
                                       ratio_inval=0.9, horizon=10)
    assert r == 1  # gereift-neutral -> ebenfalls 'nicht invalidiert'


def test_simulate_nicht_invalidiert_zu_wenig_folge_bars_gibt_none():
    closes = [100.0, 95.0]  # nur 1 Folge-Bar, horizon=10
    assert eni.simulate_nicht_invalidiert(closes, 0, 1.05, 0.9, horizon=10) is None


# ---------------------------------------------------------------------------
# (3) Mutationsproben — jeweils eine ABSICHTLICH FALSCHE Variante, die die
# ECHTE Funktion widerlegen MUSS (sonst wäre die Testabdeckung Theater).
# ---------------------------------------------------------------------------
def test_mutationsprobe_invalidiert_faelschlich_positiv_gewertet():
    """Eine kaputte Quote-Funktion, die `rec['invalidated']` DIREKT statt
    `1 - invalidated` summiert, würde Invalidierungen als Erfolg zählen —
    bei _ALLE_FAELLE (1 von 5 invalidiert) käme sie auf 1/5 statt 4/5."""
    def kaputte_quote(cases):
        return sum(c["rec"]["invalidated"] for c in cases) / len(cases)

    kaputt = kaputte_quote(_ALLE_FAELLE)
    echt = eni.quote_nicht_invalidiert(_ALLE_FAELLE)
    assert kaputt != echt
    assert kaputt == 1 / 5
    assert echt == 4 / 5


def test_mutationsprobe_baseline_mit_falscher_regel_gerechnet():
    """Würde `benchmark_nicht_invalidiert` versehentlich `evaluate.
    simulate_hit` statt `simulate_nicht_invalidiert` aufrufen (die FALSCHE,
    primäre Regel als Baseline für die SEKUNDÄRE Fragestellung), käme ein
    anderes Ergebnis heraus — hier an einem reinen Zeitablauf-Pfad gezeigt
    (gereift-neutral: nicht invalidiert, aber auch kein Zonen-Treffer)."""
    closes = [100.0] + [100.0] * 15
    richtig = eni.simulate_nicht_invalidiert(closes, 0, 1.05, 0.9, horizon=10)
    falsch_mit_primaerregel = ev.simulate_hit(closes, 0, 1.05, 0.9, horizon=10)
    assert richtig == 1        # 'nicht invalidiert': ja
    assert falsch_mit_primaerregel == 0  # 'target_hit' (Primärregel): nein
    assert richtig != falsch_mit_primaerregel


# ---------------------------------------------------------------------------
# (4) Benjamini-Hochberg
# ---------------------------------------------------------------------------
def test_benjamini_hochberg_leere_eingabe():
    assert eni.benjamini_hochberg({}) == {}


def test_benjamini_hochberg_alle_signifikant_bei_kleinen_p_werten():
    out = eni.benjamini_hochberg({"a": 0.001, "b": 0.002, "c": 0.003}, alpha=0.10)
    assert all(v["signifikant"] for v in out.values())


def test_benjamini_hochberg_grosse_p_werte_nicht_signifikant():
    out = eni.benjamini_hochberg({"a": 0.9, "b": 0.8}, alpha=0.10)
    assert not any(v["signifikant"] for v in out.values())


def test_benjamini_hochberg_rang_zuordnung():
    out = eni.benjamini_hochberg({"a": 0.05, "b": 0.01}, alpha=0.10)
    assert out["b"]["rang"] == 1
    assert out["a"]["rang"] == 2


# ---------------------------------------------------------------------------
# (5) Determinismus
# ---------------------------------------------------------------------------
def test_determinismus_gleicher_seed_gleiches_ergebnis():
    cases = _ALLE_FAELLE * 10  # > SECONDARY_MIN_N würde echte Kurse brauchen;
    # hier nur die reine Strukturfunktion ohne Baseline geprüft.
    r1 = eni.komposition(cases)
    r2 = eni.komposition(cases)
    assert r1 == r2


# ---------------------------------------------------------------------------
# (6) Harte Grenzen — wie evaluate_cluster_sensitivity.py
# ---------------------------------------------------------------------------
def test_keine_workflow_erwaehnung():
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        assert "evaluate_nicht_invalidiert" not in text, wf.name


def test_nicht_importiert_vom_tageslauf():
    for mod in ("elliott_pipeline.py", "notify.py", "health_check.py",
               "forward_collection.py", "evaluate.py"):
        quelle = (ROOT / "scripts" / mod).read_text(encoding="utf-8")
        assert not re.search(
            r"^\s*import evaluate_nicht_invalidiert|"
            r"from evaluate_nicht_invalidiert",
            quelle, re.M), mod


def test_schreibt_nie_in_geschuetzte_projektdateien():
    for geschuetzt in ("forward_collection.json", "report.json",
                       "validation_registry.md", "scripts/evaluate.py"):
        for zeile in SRC.splitlines():
            if "write_text" in zeile or '"w")' in zeile or "'w')" in zeile:
                assert geschuetzt not in zeile, (
                    f"Zeile schreibt scheinbar direkt in {geschuetzt}: "
                    f"{zeile!r}")


def test_verbotene_ziele_liste_deckt_die_projektdateien_ab():
    for pfad in ("data/forward_collection.json", "data/report.json",
                "docs/validation_registry.md", "scripts/evaluate.py"):
        assert pfad in eni._VERBOTENE_ZIELE


def test_out_auf_geschuetzte_datei_wird_verweigert(capsys):
    rc = eni.main(["--sammlung", "data/forward_collection.json",
                  "--out", "docs/validation_registry.md"])
    assert rc == 2
    assert "VERWEIGERT" in capsys.readouterr().err


def test_live_lauf_schreibt_keine_datei_in_data(tmp_path, capsys):
    """Read-only-Beleg: ein echter Lauf gegen die reale Sammlung darf KEINE
    neue/veränderte Datei unter data/ erzeugen."""
    data_dir = ROOT / "data"
    vorher = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*")
             if p.is_file()}
    rc = eni.main([])
    assert rc == 0
    nachher = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*")
              if p.is_file()}
    assert vorher == nachher


# ---------------------------------------------------------------------------
# (7) Primärausgabe von evaluate.py bleibt unverändert — SHA gepinnt
# (Vorbild: PR #72, "stale_market_suspect ... evaluate.py byte-identisch").
# ---------------------------------------------------------------------------
EVALUATE_PY_SHA256_VOR_DIESEM_PR = (
    "bc697df91235732c6c386abe38c79a98248488b9f30a239d9c26c3cbb3b513fc")


def test_evaluate_py_byte_identisch():
    inhalt = (ROOT / "scripts" / "evaluate.py").read_bytes()
    assert hashlib.sha256(inhalt).hexdigest() == EVALUATE_PY_SHA256_VOR_DIESEM_PR, (
        "scripts/evaluate.py wurde verändert — die Primärwertung muss "
        "UNANGETASTET bleiben (harte Grenze dieses PRs).")
