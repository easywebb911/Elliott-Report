"""Tests für scripts/evaluate_nicht_invalidiert.py (Easy-Entscheid Variante B,
10./11.10.2026). Handgebaute Fixtures statt echter Historie — dieses Skript
läuft NIE im Tageslauf."""
from __future__ import annotations

import hashlib
import random
import re
import sys
from pathlib import Path

import pytest

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
    """KORREKTUR 11.10.2026 (Easy-Entscheid, Variante A, #178): diese
    Prüfung verlangte ursprünglich (PR #176), dass KEIN Workflow das
    Skript je erwähnt — das war zu eng für das, was heute ausdrücklich
    gewollt ist (Zufalls-Baseline im Runner, manuell per Tap). Die EINE
    bewusste Ausnahme ist jetzt namentlich erlaubt; jeder ANDERE Workflow
    bleibt weiterhin verboten. Die eigentliche Absicherung — 'nie
    automatisch' — prüft der eigene Test
    `test_eval_nicht_invalidiert_workflow_nur_dispatch_und_nur_contents_read`
    weiter unten, nicht dieser hier."""
    erlaubt = {"eval_nicht_invalidiert.yml"}
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        if wf.name in erlaubt:
            continue
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


# ===========================================================================
# VERLUSTBILD (Easy-Entscheid, Variante A, 11.10.2026, #177)
# ===========================================================================
def _neutral(ticker: str, r_erreicht_basis, end_of_w4: bool = False) -> dict:
    rec = {"invalidated": 0, "target_hit": 0, "r_erreicht_basis": r_erreicht_basis,
          "count_wave_labels": (
              [{"index": 0, "wave": 4}] if end_of_w4 else [{"index": 0, "wave": 2}])}
    return {"ticker": ticker, "rec": rec, "hit": 0, "first_seen_date": "2026-01-01"}


def _invalidiert(ticker: str, entry: float, inval_price: float,
                 closes: list) -> dict:
    """`closes` wird 1:1 als price_path (nur 'close') übernommen."""
    rec = {
        "invalidated": 1, "target_hit": 0, "r_erreicht_basis": -1.0,
        "entry_close": entry, "invalidation_price": inval_price,
        "risiko_abstand": entry - inval_price,
        "price_path": [{"close": c, "date": f"2026-01-{i+1:02d}"}
                       for i, c in enumerate(closes)],
        "count_wave_labels": [{"index": 0, "wave": 4}],
    }
    return {"ticker": ticker, "rec": rec, "hit": 0, "first_seen_date": "2026-01-01"}


def _zielzonen_treffer(ticker: str, entry: float, tag10_close: float) -> dict:
    rec = {
        "invalidated": 0, "target_hit": 1, "entry_close": entry,
        "price_path": [{"close": tag10_close, "date": "2026-01-10"}],
        "count_wave_labels": [{"index": 0, "wave": 4}],
    }
    return {"ticker": ticker, "rec": rec, "hit": 1, "first_seen_date": "2026-01-01"}


# ---------------------------------------------------------------------------
# (1) Neutrale Fälle: r < 0, r == 0, r > 0
# ---------------------------------------------------------------------------
_N_MINUS = _neutral("NM", -0.3)
_N_NULL = _neutral("NN", 0.0)
_N_PLUS = _neutral("NP", 0.4)


def test_neutral_verlustbild_trennt_minus_null_plus():
    r = eni.neutral_verlustbild([_N_MINUS, _N_NULL, _N_PLUS], min_n=0)
    assert r["im_minus_strikt"] == 1
    assert r["genau_null"] == 1
    assert r["im_plus_strikt"] == 1
    assert r["mittelwert"] == pytest.approx((-0.3 + 0.0 + 0.4) / 3)
    assert r["median"] == pytest.approx(0.0)


def test_neutral_verlustbild_unter_min_n_wird_ausgewiesen():
    r = eni.neutral_verlustbild([_N_MINUS], min_n=30)
    assert "zu wenige Fälle" in r["hinweis"]
    # Zahlen trotzdem berechnet, nur als "nicht interpretieren" markiert:
    assert r["im_minus_strikt"] == 1


def test_neutral_verlustbild_ohne_messwert():
    ohne = _neutral("X", None)
    r = eni.neutral_verlustbild([ohne], min_n=0)
    assert r["mit_messwert"] == 0
    assert r["hinweis"] == "keine Fälle"


# ---------------------------------------------------------------------------
# (2) Randfall "Zone UND invalidiert" ist strukturell ausgeschlossen (s.
# test_proactive_watcher/test_handover_sync-Pendant in PR #176) — hier statt
# dessen der angeforderte Randfall "Close GENAU auf der Marke".
# ---------------------------------------------------------------------------
def test_gap_messung_randfall_close_genau_auf_marke():
    # entry=100, inval_price=90 — Tag 0 Close == 90 exakt.
    fall = _invalidiert("EXAKT", entry=100.0, inval_price=90.0,
                        closes=[90.0, 95.0])
    r = eni.gap_messung([fall])
    assert r["durchrutscht"] == 0
    assert r["genau_auf_marke"] == 1
    assert r["median_prozent"] == pytest.approx(0.0)
    assert r["median_r"] == pytest.approx(-1.0)  # (90-100)/(100-90) = -1.0


def test_gap_messung_echter_durchrutsch():
    # entry=100, inval_price=90, Close faellt auf 80 -> 11.11% unter der Marke
    fall = _invalidiert("GAP", entry=100.0, inval_price=90.0,
                        closes=[95.0, 80.0, 85.0])
    r = eni.gap_messung([fall])
    assert r["durchrutscht"] == 1
    assert r["genau_auf_marke"] == 0
    erwartet_prozent = (80.0 - 90.0) / 90.0 * 100
    assert r["median_prozent"] == pytest.approx(erwartet_prozent)
    erwartet_r = (80.0 - 100.0) / (100.0 - 90.0)
    assert r["median_r"] == pytest.approx(erwartet_r)


def test_gap_messung_findet_ERSTEN_treffer_nicht_den_tiefsten():
    """Randfall: Tag 0 trifft die Marke knapp (Close=89), Tag 1 faellt viel
    tiefer (Close=50). Die Messung muss den ERSTEN Tag nehmen (89), nicht
    den tiefsten (50) — identisch zum Tie-Break in simulate_nicht_invalidiert/
    forward_collection.mature_record."""
    fall = _invalidiert("ERSTER-TAG", entry=100.0, inval_price=90.0,
                        closes=[89.0, 50.0])
    r = eni.gap_messung([fall])
    erwartet_prozent = (89.0 - 90.0) / 90.0 * 100
    assert r["median_prozent"] == pytest.approx(erwartet_prozent)


def test_gap_messung_median_und_maximum_ueber_mehrere_faelle():
    f1 = _invalidiert("F1", 100.0, 90.0, [85.0])   # -5.56 %
    f2 = _invalidiert("F2", 100.0, 90.0, [45.0])   # -50.00 % (groesster Durchrutsch)
    f3 = _invalidiert("F3", 100.0, 90.0, [88.0])   # -2.22 %
    r = eni.gap_messung([f1, f2, f3])
    assert r["mit_messwert"] == 3
    assert r["maximum_prozent"] == pytest.approx((45.0 - 90.0) / 90.0 * 100)
    # Median der drei Prozentwerte (sortiert: -50, -5.56, -2.22 -> Median -5.56)
    assert r["median_prozent"] == pytest.approx((85.0 - 90.0) / 90.0 * 100)


# ---------------------------------------------------------------------------
# (3) Gesamt-Verlustbild + Zielzonen-Treffer unter Einstieg
# ---------------------------------------------------------------------------
def test_gesamt_verlustbild_zaehlt_invalidiert_plus_neutral_minus():
    cases = [_C_INVAL, _N_MINUS, _N_PLUS]  # 1 invalidiert + 1 neutral-minus + 1 neutral-plus
    r = eni.gesamt_verlustbild(cases)
    assert r["n"] == 3
    assert r["invalidiert"] == 1
    assert r["neutral_im_minus"] == 1
    assert r["anzahl"] == 2
    assert r["anteil"] == pytest.approx(2 / 3)


def test_ziel_treffer_unter_einstieg_zaehlt_korrekt():
    ueber = _zielzonen_treffer("UEBER", entry=100.0, tag10_close=110.0)
    unter = _zielzonen_treffer("UNTER", entry=100.0, tag10_close=95.0)
    r = eni.ziel_treffer_unter_einstieg([ueber, unter])
    assert r["zielzonen_treffer"] == 2
    assert r["unter_einstieg_am_tag_10"] == 1


# ---------------------------------------------------------------------------
# (4) Stopp-Baseline — reines Komplement, kein neuer p-Wert
# ---------------------------------------------------------------------------
def test_stopp_baseline_ist_komplement_ohne_neue_ziehung():
    bench = {"durchfuehrbar": True, "beobachtete_quote": 0.79,
            "zufalls_quote_mittel": 0.5, "zufalls_quote_p05": 0.4,
            "zufalls_quote_p95": 0.6, "p_wert": 0.0123, "ziehungen": 10000,
            "faelle": 157}
    r = eni.stopp_baseline(bench)
    assert r["beobachtete_quote"] == pytest.approx(0.21)
    assert r["zufalls_quote_mittel"] == pytest.approx(0.5)
    assert r["zufalls_quote_p05"] == pytest.approx(0.4)   # 1 - p95(0.6)
    assert r["zufalls_quote_p95"] == pytest.approx(0.6)   # 1 - p05(0.4)
    assert r["p_wert"] == 0.0123  # UNVERÄNDERT übernommen, keine neue Ziehung


def test_stopp_baseline_nicht_durchfuehrbar_wenn_bench_nicht_durchfuehrbar():
    bench = {"durchfuehrbar": False, "grund": "keine Kursbasis (Momentaufnahme fehlt)"}
    r = eni.stopp_baseline(bench)
    assert r["durchfuehrbar"] is False
    assert r["grund"] == "keine Kursbasis (Momentaufnahme fehlt)"


# ---------------------------------------------------------------------------
# (5) Mutationsproben — mindestens 2, Test MUSS rot werden
# ---------------------------------------------------------------------------
def test_mutationsprobe_minus_vs_minus_gleich_bei_neutral():
    """Eine kaputte Variante, die `<=` statt `<` für 'im Minus' nutzt, würde
    den Randfall r==0 FÄLSCHLICH als Verlust zählen. Die echte Funktion
    (strikt `<`) muss das von der kaputten Variante unterscheiden."""
    def kaputt_im_minus(cases):
        return sum(1 for c in cases if (c["rec"]["r_erreicht_basis"] or 0) <= 0)

    kaputt = kaputt_im_minus([_N_MINUS, _N_NULL, _N_PLUS])
    echt = eni.neutral_verlustbild([_N_MINUS, _N_NULL, _N_PLUS], min_n=0)
    assert kaputt == 2            # zaehlt r==0 FÄLSCHLICH mit
    assert echt["im_minus_strikt"] == 1   # echte Funktion: nur r<0
    assert kaputt != echt["im_minus_strikt"]


def test_mutationsprobe_gap_am_falschen_tag_gerechnet():
    """Eine kaputte Variante, die den LETZTEN statt den ERSTEN Tag unter der
    Marke nimmt, würde bei F1 unten einen anderen (tieferen) Gap-Prozentsatz
    liefern als die echte Funktion — muss sich unterscheiden."""
    fall = _invalidiert("LETZTER-TAG", entry=100.0, inval_price=90.0,
                        closes=[89.0, 85.0, 70.0])  # alle drei <= 90

    def kaputt_letzter_tag_statt_erster(cases):
        out = []
        for c in cases:
            pfad = c["rec"]["price_path"]
            treffer = [t["close"] for t in pfad if t["close"] <= c["rec"]["invalidation_price"]]
            if treffer:
                out.append(treffer[-1])  # FALSCH: letzter statt erster Treffer
        return out

    kaputt = kaputt_letzter_tag_statt_erster([fall])
    echt = eni.gap_messung([fall])
    assert kaputt == [70.0]                       # kaputte Variante nimmt Tag 3
    assert echt["median_prozent"] == pytest.approx((89.0 - 90.0) / 90.0 * 100)  # echt: Tag 1
    assert kaputt[0] != 89.0


# ---------------------------------------------------------------------------
# (6) Determinismus
# ---------------------------------------------------------------------------
def test_verlustbild_determinismus():
    cases = [_N_MINUS, _N_NULL, _N_PLUS, _C_INVAL]
    r1 = (eni.neutral_verlustbild(cases, min_n=0),
         eni.gesamt_verlustbild(cases))
    r2 = (eni.neutral_verlustbild(cases, min_n=0),
         eni.gesamt_verlustbild(cases))
    assert r1 == r2


# ---------------------------------------------------------------------------
# (7) Echter Lauf gegen die reale Sammlung — Verlustbild-Zahlen reproduzierbar
# ---------------------------------------------------------------------------
def test_echter_lauf_verlustbild_zahlen(capsys):
    rc = eni.main([])
    assert rc == 0
    ausgabe = capsys.readouterr().out
    assert "VERLUSTBILD" in ausgabe
    assert "andere Fallbasis" in ausgabe.lower() or "ANDERE FALLBASIS" in ausgabe


# ===========================================================================
# WORKFLOW eval_nicht_invalidiert.yml (Easy-Entscheid, Variante A, 11.10.2026,
# #178) — Zufalls-Baseline im GitHub-Runner, nur Job-Summary, nichts committet.
# ===========================================================================
WORKFLOW_PFAD = ROOT / ".github/workflows/eval_nicht_invalidiert.yml"
WORKFLOW_TEXT = WORKFLOW_PFAD.read_text(encoding="utf-8")


def test_eval_nicht_invalidiert_workflow_existiert():
    assert WORKFLOW_PFAD.exists()
    assert "--kurse-holen" in WORKFLOW_TEXT
    assert "evaluate_nicht_invalidiert.py" in WORKFLOW_TEXT


def test_eval_nicht_invalidiert_workflow_nur_dispatch_und_nur_contents_read():
    """Mindest-Test laut Auftrag: NUR workflow_dispatch, NUR contents: read.
    Mutationsprobe (manuell durchgeführt, s. PR-Text): Trigger um `schedule:`
    erweitert ODER Recht um `pull-requests: write` erweitert -> beide Asserts
    unten schlagen fehl."""
    ohne_kommentare = "\n".join(
        z for z in WORKFLOW_TEXT.splitlines() if not z.lstrip().startswith("#"))
    trigger = ohne_kommentare[ohne_kommentare.index("\non:"):
                             ohne_kommentare.index("\npermissions:")]
    assert "workflow_dispatch" in trigger
    for verboten in ("schedule:", "push:", "workflow_run:", "pull_request:"):
        assert verboten not in trigger, f"feuert automatisch: {verboten}"
    assert "permissions:\n  contents: read" in ohne_kommentare
    for verboten in ("write", "contents: write", "pull-requests"):
        assert verboten not in ohne_kommentare.split("permissions:")[1].split(
            "concurrency:")[0], f"Recht zu weit: {verboten}"


def test_eval_nicht_invalidiert_workflow_committet_und_mergt_nie():
    """Kommentare ausgeschlossen (Muster aus test_evaluate.py::
    test_laeuft_nicht_im_tageslauf) — ein Kommentar, der 'KEIN
    continue-on-error' BENENNT, ist kein Verstoß dagegen."""
    ohne_kommentare = "\n".join(
        z for z in WORKFLOW_TEXT.splitlines() if not z.lstrip().startswith("#"))
    for verboten in ("git commit", "git push", "git add", "gh pr create",
                    "gh pr merge", "continue-on-error"):
        assert verboten not in ohne_kommentare, verboten


def test_eval_nicht_invalidiert_workflow_kein_schreibender_schritt_ausser_kursdatei():
    """Beweis-Schritt (`git status --porcelain`) muss im Workflow stehen —
    die eigentliche Durchsetzung, nicht nur die Behauptung im Kommentar."""
    assert "git status --porcelain" in WORKFLOW_TEXT
    assert "::error::" in WORKFLOW_TEXT


def test_eval_nicht_invalidiert_wird_von_der_bestehenden_tageslauf_pruefung_erfasst():
    """Der generische Test in test_evaluate.py::test_laeuft_nicht_im_tageslauf
    scannt ALLE Workflows, die 'evaluate' erwähnen — dieser hier muss darin
    automatisch mit erfasst werden, keine zweite, abweichende Prüfung."""
    assert "evaluate" in WORKFLOW_TEXT


def test_keine_workflow_run_kette_reagiert_auf_diesen_workflow():
    """Kein anderer Workflow darf per `workflow_run` an diesen hier anknüpfen
    — er soll ein isolierter, manueller Lauf bleiben, keine Kette."""
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        if wf.name == "eval_nicht_invalidiert.yml":
            continue
        text = wf.read_text(encoding="utf-8")
        assert "Zufalls-Baseline für 'nicht invalidiert'" not in text, wf.name
        assert "eval_nicht_invalidiert" not in text, wf.name


# ===========================================================================
# CLUSTER-SENSITIVITÄT (Easy-Entscheid 11.10.2026) — Block-Bootstrap nach
# Tag und nach Ticker auf die Differenz 'beobachtet minus Zufall', analog
# Registry-Regel #166/#167 (`evaluate_cluster_sensitivity._bloecke`
# WIEDERVERWENDET, s. Moduldoc). Handgebaute, synthetische Fixtures mit
# echten (aber künstlichen) Kursreihen — dieses Skript holt hier KEINE
# echten Kurse, nur eigene `prices`-Dicts.
# ===========================================================================
def _kurs_fall(ticker: str, date: str, invalidated: int) -> dict:
    """Minimaler Fall für `_outcome_pools`/`cluster_sensitivitaet_*`: braucht
    `ticker`, `first_seen_date`, `entry`/`tlow`/`inval` (top-level, NICHT in
    `rec`) sowie `rec['invalidated']`."""
    return {"rec": {"invalidated": invalidated}, "hit": 0, "ticker": ticker,
           "first_seen_date": date, "entry": 100.0, "tlow": 110.0,
           "inval": 90.0}


def _kurs_serie() -> dict:
    return {"dates": [f"2026-01-{d:02d}" for d in range(1, 29)],
           "closes": [100.0 + ((j % 7) - 3) * 0.5 for j in range(28)]}


# Stark geclustert: 20 Fälle, aber nur 2 Kalendertage UND nur 2 Ticker.
_GECLUSTERT = [
    _kurs_fall("A" if i % 2 == 0 else "B",
              "2026-01-01" if i < 10 else "2026-01-02",
              1 if i % 4 == 0 else 0)
    for i in range(20)
]
_GECLUSTERT_PREISE = {"A": _kurs_serie(), "B": _kurs_serie()}

# Verstreut: 40 Fälle über 10 Ticker und 5 Tage — genug Blöcke für
# Seed-Sensitivität (s. Prototyp-Lauf in der Diagnose dieses PRs).
_VERSTREUT = [
    _kurs_fall(f"T{i % 10}", f"2026-01-{(i % 5) + 1:02d}", 1 if i % 3 == 0 else 0)
    for i in range(40)
]
_VERSTREUT_PREISE = {f"T{i}": _kurs_serie() for i in range(10)}


def test_cluster_sensitivitaet_nicht_durchfuehrbar_ohne_faelle():
    r = eni.cluster_sensitivitaet_nicht_invalidiert([], _GECLUSTERT_PREISE)
    assert r == {"durchfuehrbar": False, "grund": "keine Fälle"}


def test_cluster_sensitivitaet_nicht_durchfuehrbar_ohne_kursbasis():
    r = eni.cluster_sensitivitaet_nicht_invalidiert(_GECLUSTERT, None)
    assert r["durchfuehrbar"] is False
    assert "Kursbasis" in r["grund"]


def test_cluster_sensitivitaet_rechnet_nur_fuer_zelle_gesamt():
    """Umfangsbegrenzung wie #166/#167 (s. Docstring der Funktion) — die
    Funktion nimmt die ihr übergebene Fallmenge als EINE Zelle, keine eigene
    Stratifizierung nach Setup-Typ."""
    r = eni.cluster_sensitivitaet_nicht_invalidiert(
        _VERSTREUT, _VERSTREUT_PREISE, seeds=(1,), draws=200)
    assert r["durchfuehrbar"] is True
    assert r["faelle"] == 40
    assert set(r["bloecke"]) == {"Tag-Block", "Ticker-Block"}


def test_cluster_sensitivitaet_determinismus_gleicher_seed_gleiches_ergebnis():
    r1 = eni.cluster_sensitivitaet_nicht_invalidiert(
        _VERSTREUT, _VERSTREUT_PREISE, seeds=(42,), draws=300)
    r2 = eni.cluster_sensitivitaet_nicht_invalidiert(
        _VERSTREUT, _VERSTREUT_PREISE, seeds=(42,), draws=300)
    assert r1 == r2


def test_cluster_sensitivitaet_stopp_gerissen_ist_spiegelung_ohne_neue_ziehung():
    """Wie `stopp_baseline` (PR #177): Differenz × −1, CI-Grenzen vertauscht
    und gespiegelt — KEINE zweite Bootstrap-Rechnung."""
    ni = eni.cluster_sensitivitaet_nicht_invalidiert(
        _VERSTREUT, _VERSTREUT_PREISE, seeds=(1, 2), draws=300)
    sg = eni.cluster_sensitivitaet_stopp_gerissen(ni)
    assert sg["diff_punkt"] == pytest.approx(-ni["diff_punkt"])
    assert sg["beobachtete_quote"] == pytest.approx(1 - ni["beobachtete_quote"])
    assert sg["zufalls_mittel"] == pytest.approx(1 - ni["zufalls_mittel"])
    for feld in ("Tag-Block", "Ticker-Block"):
        for seed in (1, 2):
            n_werte = ni["bloecke"][feld]["je_seed"][seed]
            s_werte = sg["bloecke"][feld]["je_seed"][seed]
            assert s_werte["ci_untergrenze"] == pytest.approx(
                -n_werte["ci_obergrenze"])
            assert s_werte["ci_obergrenze"] == pytest.approx(
                -n_werte["ci_untergrenze"])


def test_cluster_sensitivitaet_stopp_gerissen_nicht_durchfuehrbar_wird_weitergegeben():
    ni = {"durchfuehrbar": False, "grund": "keine Kursbasis (Momentaufnahme fehlt)"}
    sg = eni.cluster_sensitivitaet_stopp_gerissen(ni)
    assert sg == {"durchfuehrbar": False, "grund": ni["grund"]}


def test_cluster_sensitivitaet_seeds_koennen_unterschiedliche_ergebnisse_liefern():
    """EXZELLENZ-Punkt 7 (Determinismus): verschiedene Seeds dürfen (müssen
    nicht, aber können) verschiedene Intervalle liefern — Beleg an der
    Ticker-Block-Fixture, empirisch ermittelt (Prototyp-Lauf dieses PRs:
    Seed 1/4 -> -0.425, Seed 2/3/5 -> -0.45 an der Untergrenze)."""
    r = eni.cluster_sensitivitaet_nicht_invalidiert(
        _VERSTREUT, _VERSTREUT_PREISE, seeds=(1, 2, 3, 4, 5), draws=1000)
    untergrenzen = {w["ci_untergrenze"]
                   for w in r["bloecke"]["Ticker-Block"]["je_seed"].values()}
    assert len(untergrenzen) > 1, (
        "alle Seeds liefern dieselbe Untergrenze — Fixture oder "
        "Seed-Verwendung prüfen")


# ---------------------------------------------------------------------------
# Mutationsproben — jeweils eine ABSICHTLICH FALSCHE Variante, die sich vom
# echten Ergebnis unterscheiden MUSS (sonst wäre die Testabdeckung Theater).
# ---------------------------------------------------------------------------
def test_mutationsprobe_blockbildung_entfernt_aendert_das_intervall():
    """Eine kaputte Variante, die die Blockbildung (`_bloecke`) WEGLÄSST und
    stattdessen jeden Einzelfall als eigenen 'Block' zieht (gewöhnlicher
    Fall-Bootstrap statt Block-Bootstrap), muss ein ANDERES Konfidenzintervall
    liefern als die echte Funktion — an der stark geclusterten Fixture
    (nur 2 Tage) zeigt sich der Unterschied deutlich."""
    echt = eni.cluster_sensitivitaet_nicht_invalidiert(
        _GECLUSTERT, _GECLUSTERT_PREISE, seeds=(20260728,), draws=2000)
    echt_tag = echt["bloecke"]["Tag-Block"]["je_seed"][20260728]

    pools, _von, _bis, ohne_kurse = eni._outcome_pools(_GECLUSTERT,
                                                       _GECLUSTERT_PREISE)
    assert not ohne_kurse
    nutzbar = list(zip(_GECLUSTERT, pools))
    n = len(nutzbar)
    pool_by_id = {id(c): p for c, p in nutzbar}
    rng = random.Random(20260728)
    diffs = []
    for _ in range(2000):
        resampled = [nutzbar[rng.randrange(n)][0] for _ in range(n)]
        m = len(resampled)
        beob = sum(1 - c["rec"]["invalidated"] for c in resampled) / m
        basis = sum((p := pool_by_id[id(c)])[rng.randrange(len(p))]
                   for c in resampled) / m
        diffs.append(beob - basis)
    diffs.sort()
    kaputt_u = ev._quantil(diffs, (1 - echt["ci_niveau"]) / 2)
    kaputt_o = ev._quantil(diffs, 1 - (1 - echt["ci_niveau"]) / 2)

    assert (kaputt_u, kaputt_o) != (
        echt_tag["ci_untergrenze"], echt_tag["ci_obergrenze"])


def test_mutationsprobe_seed_ignoriert_liefert_immer_dasselbe_ergebnis():
    """Eine kaputte Variante, die den `seed`-Parameter ignoriert (immer
    `random.Random(0)` statt `random.Random(seed)`), liefert für
    verschiedene angeforderte Seeds IMMER dasselbe Ergebnis — die echte
    Funktion muss sich (an der verstreuten Fixture) zwischen mindestens zwei
    der angeforderten Seeds unterscheiden."""
    seeds = (1, 2, 3, 4, 5)
    echt = eni.cluster_sensitivitaet_nicht_invalidiert(
        _VERSTREUT, _VERSTREUT_PREISE, seeds=seeds, draws=1000)
    echt_werte = [tuple(echt["bloecke"]["Ticker-Block"]["je_seed"][s].values())[:2]
                 for s in seeds]
    assert len(set(echt_werte)) > 1  # echte Funktion: nicht alle gleich

    pools, _von, _bis, _ohne = eni._outcome_pools(_VERSTREUT, _VERSTREUT_PREISE)
    nutzbar = list(zip(_VERSTREUT, pools))
    pool_by_id = {id(c): p for c, p in nutzbar}
    bloecke = eni.ecs._bloecke(_VERSTREUT, "ticker")
    keys = sorted(bloecke)
    k = len(keys)

    def kaputt_mit_ignoriertem_seed(_seed: int) -> "tuple[float, float]":
        rng = random.Random(0)  # FALSCH: ignoriert `_seed`
        diffs = []
        for _ in range(1000):
            gezogene = [keys[rng.randrange(k)] for _ in range(k)]
            resampled = [c for key in gezogene for c in bloecke[key]]
            m = len(resampled)
            beob = sum(1 - c["rec"]["invalidated"] for c in resampled) / m
            basis = sum((p := pool_by_id[id(c)])[rng.randrange(len(p))]
                       for c in resampled) / m
            diffs.append(beob - basis)
        diffs.sort()
        return (ev._quantil(diffs, 0.0125), ev._quantil(diffs, 0.9875))

    kaputt_werte = [kaputt_mit_ignoriertem_seed(s) for s in seeds]
    assert len(set(kaputt_werte)) == 1  # kaputte Variante: immer gleich
    assert set(kaputt_werte) != set(echt_werte)  # unterscheidet sich von echt


def test_cluster_sensitivitaet_schreibt_keine_datei_in_data(tmp_path):
    """Read-only-Beleg wie bei der bestehenden Baseline — die neue Rechnung
    hängt am selben `main()`, der bereits geprüft ist, hier zusätzlich
    direkt an der Funktion selbst."""
    data_dir = ROOT / "data"
    vorher = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*")
             if p.is_file()}
    eni.cluster_sensitivitaet_nicht_invalidiert(
        _VERSTREUT, _VERSTREUT_PREISE, seeds=(1,), draws=50)
    nachher = {p: p.stat().st_mtime_ns for p in data_dir.rglob("*")
              if p.is_file()}
    assert vorher == nachher


def test_cluster_sensitivitaet_erscheint_im_bericht_und_im_text():
    """`berechne()` liefert den neuen Schlüssel, `render_text()` druckt die
    Schlusszeile ohne Verdikt-Sprache."""
    res = eni.berechne(_VERSTREUT, _VERSTREUT_PREISE, draws=200)
    assert "cluster_sensitivitaet" in res
    assert set(res["cluster_sensitivitaet"]) == {"nicht_invalidiert",
                                                  "stopp_gerissen"}
    text = eni.render_text(res, None, None, None, 0)
    assert "CLUSTER-SENSITIVITÄT" in text
    assert "Intervall schließt 0 ein:" in text
    assert "verdikt" not in text.lower() or "KEIN VERDIKT" in text


# ===========================================================================
# „OHNE MARKIERTE FÄLLE" (Easy-Entscheid Variante A, 14.10.2026,
# Diagnose-Folgeauftrag) — invertiertes Risiko bei Anlage.
# ===========================================================================
import invertiertes_risiko_anlage as ira  # noqa: E402


def _markiert(fall: dict) -> dict:
    """Kopiert einen Fall und setzt den Marker auf dessen `rec` — die
    Original-Fixture bleibt unverändert (sonst verfälscht das andere Tests,
    die dieselbe Modul-Konstante weiterverwenden)."""
    import copy
    f = copy.deepcopy(fall)
    f["rec"][ira.MARKER] = True
    return f


def test_ohne_markierte_faelle_filtert_nur_den_marker():
    faelle = [_A_ZONE, _markiert(_B_NEUTRAL), _C_INVAL, _markiert(_D_NEUTRAL)]
    gefiltert = eni.ohne_markierte_faelle(faelle)
    assert [c["ticker"] for c in gefiltert] == ["A", "C"]


def test_ohne_markierte_faelle_ohne_marker_aendert_nichts():
    faelle = [_A_ZONE, _B_NEUTRAL, _C_INVAL]
    assert eni.ohne_markierte_faelle(faelle) == faelle


def test_mutationsprobe_marker_filter_aus_der_neuen_zeile_entfernt():
    """Mutationsprobe (Auftrag TESTS): eine kaputte Variante, die den
    Marker-Filter vergisst (`cases` statt `ohne_markierte_faelle(cases)`),
    würde dieselbe Fallzahl wie die ungefilterte Zeile liefern. Echt und
    kaputt müssen sich hier unterscheiden."""
    faelle = [_A_ZONE, _markiert(_B_NEUTRAL), _C_INVAL, _markiert(_D_NEUTRAL)]

    def kaputt_ohne_markierte_faelle(cases):
        return list(cases)  # FALSCH: filtert nichts

    echt = eni.ohne_markierte_faelle(faelle)
    kaputt = kaputt_ohne_markierte_faelle(faelle)
    assert len(echt) != len(kaputt)
    assert len(echt) == 2 and len(kaputt) == 4


def test_berechne_enthaelt_ohne_markierte_faelle_block():
    faelle = list(_VERSTREUT)
    faelle[0] = _markiert(faelle[0])
    faelle[1] = _markiert(faelle[1])
    res = eni.berechne(faelle, _VERSTREUT_PREISE, draws=200)

    zelle = res["zelle_ohne_markierte_faelle"]
    assert zelle["entfernt"] == 2
    assert zelle["faelle"] == len(faelle) - 2

    v = res["verlustbild"]["ohne_markierte_faelle"]
    assert v["entfernt"] == 2
    assert v["faelle"] == len(faelle) - 2

    assert "cluster_sensitivitaet_ohne_markierte_faelle" in res
    assert set(res["cluster_sensitivitaet_ohne_markierte_faelle"]) == \
           {"nicht_invalidiert", "stopp_gerissen"}


def test_berechne_kandidaten_und_zufallsseite_auf_derselben_fallmenge():
    """EXZELLENZ-Anforderung: Stopp-Quote-Zähler (Kandidatenseite) und die
    `_outcome_pools`-Eingabe (Zufallsseite) der neuen Zeile laufen auf
    EXAKT derselben gefilterten Fallliste — kein getrenntes Rezept je
    Seite."""
    faelle = list(_VERSTREUT)
    faelle[3] = _markiert(faelle[3])
    gefiltert = eni.ohne_markierte_faelle(faelle)

    res = eni.berechne(faelle, _VERSTREUT_PREISE, draws=200)
    zelle = res["zelle_ohne_markierte_faelle"]
    assert zelle["faelle"] == len(gefiltert)
    if zelle["baseline"] and zelle["baseline"].get("durchfuehrbar"):
        assert zelle["baseline"]["faelle"] == len(gefiltert)


def test_render_text_zeigt_den_abschnitt_ohne_markierte_faelle():
    faelle = list(_VERSTREUT)
    faelle[0] = _markiert(faelle[0])
    res = eni.berechne(faelle, _VERSTREUT_PREISE, draws=200)
    text = eni.render_text(res, None, None, None, 0)
    assert "OHNE MARKIERTE FÄLLE" in text
    assert "entfernt: 1 markierte Fälle" in text
    assert "dieselbe Cluster-Sensitivität, ohne markierte Fälle" in text


def test_zaehlwerk_schreibt_die_zusatz_zeile_fort():
    """'Kopfzeile NACHTRÄGLICH DEFINIERT bleibt, Zählung gerechneter
    Auswertungen fortschreiben' (Auftrag TEIL 1.3) — die Zusatz-Zeile zählt
    in `zellen_insgesamt` mit."""
    res = eni.berechne(list(_VERSTREUT), _VERSTREUT_PREISE, draws=200)
    assert res["zaehlwerk"]["zellen_insgesamt"] == len(res["zellen"]) + 1
    assert res["kopfzeile"] == eni.KOPFZEILE


def test_echter_lauf_zeigt_ohne_markierte_faelle_block(capsys):
    """Echter Lauf gegen die reale Sammlung — Beleg statt Behauptung: der
    Backfill vom 14.10.2026 hat tatsächlich Records markiert, die neue Zeile
    entfernt also > 0 Fälle (bewusst NICHT exakt gepinnt — die Population
    wächst täglich per Cron, s. Begründung bei `test_bestehende_marker_sind_
    unberuehrt` in test_invertiertes_risiko_anlage.py)."""
    rc = eni.main([])
    assert rc == 0
    ausgabe = capsys.readouterr().out
    assert "OHNE MARKIERTE FÄLLE" in ausgabe
    treffer = re.search(r"entfernt: (\d+) markierte Fälle", ausgabe)
    assert treffer and int(treffer.group(1)) > 0


def test_ohne_markierte_faelle_ist_unabhaengig_von_filter_sensitivity_sammlung():
    """0d der Diagnose: diese Zeile hängt NICHT an
    `filter_sensitivity_sammlung.py` — sie liest `ira.MARKER` direkt."""
    assert "filter_sensitivity_sammlung" not in SRC
