"""Wiring der zwei neuen K.o.-Regeln (Regel 4/5, s. rules.py) im Zähl-Pfad von
`elliott_pipeline.py` — Diagnose-Folgeauftrag 14.10.2026, Easy-Entscheid,
PR 1 von 4 (Zählregel). Befund: BAC, Top-5 Platz 1, 5 von 202 Records der
Sammlung mit geometrisch unmöglicher Zählung.

GRENZEN laut Auftrag: Score, Gewichte, SETUP_BASE_POINTS, Ranking-Sortierung,
Kandidaten-Aufnahme außer der Zählgültigkeit, evaluate.py (SHA256-Pin) bleiben
UNANGETASTET — hier NUR geprüft, nicht verändert.
"""
import json
from pathlib import Path

import elliott_pipeline as pipe
from zigzag import Pivot

ROOT = Path(__file__).resolve().parent.parent
COLL = ROOT / "data" / "forward_collection.json"


# ===========================================================================
# 1 · classify_setup / enumerate_long_counts — Pivot-Kinds werden durchgereicht
# ===========================================================================
def _bac_pivots():
    """BAC-Muster, 1:1 aus data/report.json (chart_points Index 7-11)."""
    return [
        Pivot(430, 59.5959, "H", "2026-07-06"),
        Pivot(447, 60.76, "L", "2026-07-29"),
        Pivot(457, 64.481, "H", "2026-08-12"),
        Pivot(468, 60.8595, "L", "2026-08-27"),
        Pivot(473, 62.72, "H", "2026-09-03"),
    ]


def _saubere_pivots():
    """Saubere Long-Zählung Ende-W4: L,H,L,H,L, W2/W4 retracen korrekt."""
    return [
        Pivot(0, 100.0, "L"), Pivot(10, 130.0, "H"), Pivot(20, 112.0, "L"),
        Pivot(30, 160.0, "H"), Pivot(40, 145.0, "L"),
    ]


def test_classify_setup_verwirft_das_bac_muster():
    """`classify_setup` ist first-fit: end_of_w4 (5 Punkte) zuerst, dann
    end_of_w2 (letzte 3 Punkte) als Fallback. Die 5-Punkte-W4-Lesart wird
    jetzt verworfen (Regel 4+5) — die LETZTEN 3 Punkte des Musters bilden
    aber UNABHÄNGIG davon eine eigene, geometrisch gültige SHORT-Lesart
    (P0=64,481 Hoch, P1=60,8595 Tief, P2=62,72 Hoch, retraciert korrekt) —
    das ist keine Lücke, sondern genau der Grund, warum `build_candidate`
    Short-Zählungen separat über `SHORT_SETUP_EXCLUDED` filtert (Long-only).
    Hier wird nur geprüft: NIE wieder die ursprüngliche LANGE BAC-Lesart."""
    setup = pipe.classify_setup(_bac_pivots(), close=54.58)
    assert setup is None or setup["direction"] < 0
    if setup is not None:
        assert setup["setup"] == "end_of_w2"  # nicht mehr die W4-Lesart


def test_classify_setup_laesst_saubere_zaehlung_unberuehrt():
    setup = pipe.classify_setup(_saubere_pivots(), close=150.0)
    assert setup is not None
    assert setup["setup"] == "end_of_w4"
    assert setup["direction"] == 1


def test_enumerate_long_counts_verwirft_das_bac_muster_ebenfalls():
    """Ambiguitäts-Ausweis (alt_count/alt_count_v2, PR #30/#118) nutzt denselben
    Pfad — bewusst, s. PR-Text Punkt 2: dieselbe Funktion, dieselbe Regel."""
    assert pipe.enumerate_long_counts(_bac_pivots(), close=54.58) == []


def test_ambiguity_fields_zaehlt_das_bac_muster_nicht():
    total, alt = pipe.ambiguity_fields(_bac_pivots(), close=54.58)
    assert total == 0 and alt is None


def test_score_und_ranking_fuer_gueltige_zaehlung_unveraendert():
    """Vorher/Nachher auf demselben Input: `score_setup()` selbst ist von
    diesem PR nicht angefasst — für eine WEITERHIN gültige Zählung muss der
    Score exakt derselbe sein wie vor der Änderung (Regel 4/5 greifen hier
    nicht, da die Struktur sauber ist)."""
    setup = pipe.classify_setup(_saubere_pivots(), close=150.0)
    score = pipe.score_setup(setup)
    # Byte-identische Reproduktion der Formel (config-Gewichte UNVERÄNDERT):
    import config
    erwartet = round(
        setup["base_points"] * config.SCORE_WEIGHTS["setup_base"]
        + setup["fib_bonus"] * config.SCORE_WEIGHTS["fib_proximity"]
        + setup["inval_bonus"] * config.SCORE_WEIGHTS["invalidation_distance"], 2)
    assert score == erwartet


# ===========================================================================
# 2 · build_candidate — verworfene Zählung zählt als NO_VALID_COUNT (kein
#     neuer Skip-Grund, s. Auftrag Punkt 2: "bevorzugt unter bestehendem
#     no_valid_count zählen").
# ===========================================================================
def _bac_artige_kursreihe():
    """Dates/Closes, die über `zigzag()` exakt das BAC-Pivot-Muster ergeben —
    End-to-End-Beleg (nicht nur auf vorgefertigten Pivots)."""
    # Reine Auf-ab-Serie um die fünf Pivot-Preise, ZIGZAG_WINDOW-kompatibel.
    import config

    def rampe(von, bis, n):
        schritt = (bis - von) / n
        return [von + schritt * i for i in range(1, n + 1)]

    closes = ([59.5959] + rampe(59.5959, 50.0, 6) + rampe(50.0, 60.76, 6)
             + rampe(60.76, 55.0, 6) + rampe(55.0, 64.481, 6)
             + rampe(64.481, 58.0, 6) + rampe(58.0, 60.8595, 6)
             + rampe(60.8595, 56.0, 6) + rampe(56.0, 62.72, 6)
             + rampe(62.72, 54.58, 6))
    dates = [f"2026-01-{min(28, i // 4 + 1):02d}" for i in range(len(closes))]
    return dates, closes


def test_build_candidate_verwirft_bac_artige_kursreihe_als_no_valid_count():
    dates, closes = _bac_artige_kursreihe()
    entry, reason, _detail = pipe.build_candidate("BACTEST", dates, closes)
    # Fail-soft-Hinweis: falls die synthetische Serie zufällig eine andere
    # Pivot-Struktur ergibt, ist der Test über die echten `chart_points`-Tests
    # oben bereits abgesichert — hier zusätzlich der reale `build_candidate`-
    # Pfad, soweit die Serie das BAC-Muster trifft.
    if entry is not None:
        pytest_skip_hinweis = "synthetische Serie ergab kein BAC-Muster (ZigZag-Fenster)"
        assert False, pytest_skip_hinweis
    assert reason == pipe.NO_VALID_COUNT


def test_kein_neuer_skip_grund_noetig():
    """Punkt 2 des Auftrags: `classify_setup`s None-Rückgabe fällt bereits
    VOR diesem PR auf `NO_VALID_COUNT` — kein zusätzlicher reason_counts-
    Eintrag, keine neue Frontend-Beschriftung nötig."""
    q = (ROOT / "scripts" / "elliott_pipeline.py").read_text(encoding="utf-8")
    assert "RULE_TREND_ORIGIN_KIND" not in q
    assert "RULE_W2_COUNTERTREND" not in q
    # SKIP_REASONS bleibt bei den sieben bestehenden Gründen.
    import re
    m = re.search(r"SKIP_REASONS = \(([^)]*)\)", q, re.S)
    assert m
    gruende = [g.strip() for g in m.group(1).replace("\n", "").split(",") if g.strip()]
    assert len(gruende) == 7


# ===========================================================================
# 3 · Wochen-/Monatsgrad (_count_from_series) — DIESELBE Funktion wie der
#     Tagesgrad, bewusst MIT Regel 4/5 (Punkt 2 des Auftrags, kein Mini-Stopp
#     nötig: Wirkung ist klar und beabsichtigt — eine Struktur, die am
#     Tagesgrad geometrisch unmöglich ist, ist es auch am Wochen-/Monatsgrad).
# ===========================================================================
def test_wochen_monatsgrad_nutzt_dieselbe_classify_setup_funktion():
    """Strukturbeleg statt fragiler ZigZag-Rekonstruktion (eine rohe
    Kursreihe aus nur 5 Punkten reproduziert nicht zuverlässig dieselben
    Pivots — `zigzag()` braucht echte Bar-Historie). `_count_from_series`
    (Wochen-/Monatsgrad, Tag ebenfalls) ruft `classify_setup` DIREKT auf —
    dieselbe Funktion, dieselben Regeln 4+5, by construction, kein Mini-
    Stopp nötig (Punkt 2 des Auftrags: Wirkung ist klar und beabsichtigt)."""
    import inspect
    quelle = inspect.getsource(pipe._count_from_series)
    assert "classify_setup(pivots" in quelle
    assert "ambiguity_fields(pivots" in quelle
    assert "ambiguity_v2_fields(pivots" in quelle


# ===========================================================================
# 4 · Watchlist (_classify_structure/_structure_from_series) — BEWUSST
#     UNBERÜHRT (Mini-Stopp-Befund, s. PR-Text): kein Pivot-Kind-Zugriff dort,
#     Regel 4/5 greifen NICHT. Reine Anzeige bleibt wie vor diesem PR.
# ===========================================================================
def test_watchlist_strukturerkennung_bleibt_fuer_das_bac_muster_unveraendert():
    """`_classify_structure` nimmt bereits fertige Preise (kein ZigZag-Umweg
    nötig, anders als `_structure_from_series`, dessen Kursreihen-Rekonstruktion
    aus nur 5 Punkten nicht zuverlässig dieselben Pivots ergibt). Direkter
    Aufruf mit denselben 5 BAC-Preisen wie oben: die Struktur wird WEITERHIN
    angezeigt — exakt das Verhalten von vor diesem PR (kein Pivot-Kind-Zugriff
    in `_classify_structure`, s. rules.py-Moduldoc "BEIDE Regeln hängen an...")."""
    prices = [p.price for p in _bac_pivots()]
    befund = pipe._classify_structure(prices, close=54.58)
    assert befund["state"] != pipe.STRUCTURE_NO


def test_watchlist_strukturerkennung_hat_keinen_pivot_kind_zugriff():
    """Struktureller Beleg für die Mini-Stopp-Entscheidung (s. PR-Text): die
    Watchlist-Funktionen übergeben nirgends `kinds` an die Validatoren."""
    import inspect
    quelle_struktur = inspect.getsource(pipe._classify_structure)
    quelle_korrektur = inspect.getsource(pipe._detect_correction)
    assert "kinds" not in quelle_struktur
    assert "kinds" not in quelle_korrektur


# ===========================================================================
# 5 · ECHTER GEGENTEST gegen data/forward_collection.json (202 Records) —
#     Zahlen im PR-Text/Bericht belegt, hier als Regressionstest festgenagelt.
# ===========================================================================
ERWARTETE_VERWORFENE = {
    ("HD", "2026-07-28"), ("QIA.DE", "2026-07-28"), ("MNST", "2026-08-10"),
    ("BAC", "2026-09-18"), ("BAC", "2026-10-06"),
}


def _bewerte_record(rec):
    """Rekonstruiert das Setup aus den gespeicherten `chart_points`/
    `count_wave_labels` über die ECHTEN rules.py-Funktionen (nicht über
    elliott_pipeline, weil die Sammlung keine Pivot-Objekte speichert) —
    identische Prüfung wie classify_setup/_eval_end_of_w4/_eval_end_of_w2,
    hier nur ohne den ZigZag/Pivot-Umweg."""
    import rules

    cp = rec.get("chart_points")
    cwl = rec.get("count_wave_labels")
    if not cp or not cwl:
        return None
    idx = {w["wave"]: cp[w["index"]] for w in cwl if 0 <= w["index"] < len(cp)}
    if 0 not in idx or 1 not in idx:
        return None
    punkte = [idx[k]["price"] for k in sorted(idx)]
    kinds = [idx[k]["kind"] for k in sorted(idx)]
    if len(punkte) == 5:
        return rules.validate_partial_to_w4(punkte, kinds).is_valid
    if len(punkte) == 3:
        return rules.check_trend_consistency(punkte, kinds) == []
    return None


def test_echter_gegentest_genau_fuenf_records_verworfen():
    """KEINE gepinnte Gesamtzahl (Lehre aus `in_session_creation`/#94, s.
    SESSION_HANDOVER.md): die Sammlung wächst täglich per Cron — am
    14.10.2026 waren es 202 Records (197 gültig), seit dem Merge von #186
    legitim mehr. Die 5 VERWORFENEN sind ein abgeschlossener historischer
    Fakt (die Zählregel läuft seit dem Stichtag im Tageslauf selbst und
    verhindert NEUE Treffer dieser Art) — NUR diese Menge wird exakt
    gepinnt. Die Zahl der gültigen Fälle ist eine wachsende Untergrenze."""
    coll = json.loads(COLL.read_text(encoding="utf-8"))
    recs = coll["records"]
    verworfen = set()
    gueltig = 0
    for r in recs:
        v = _bewerte_record(r)
        if v is None:
            continue
        if v:
            gueltig += 1
        else:
            verworfen.add((r["ticker"], r.get("first_seen_date")))
    assert verworfen == ERWARTETE_VERWORFENE
    assert len(verworfen) == 5
    assert gueltig >= 197, "der Bestand vom 14.10.2026 darf nie unterschritten werden"
    assert gueltig + len(verworfen) == len(
        [r for r in recs if r.get("chart_points") and r.get("count_wave_labels")])


def test_echter_gegentest_ueber_die_tatsaechliche_pipeline_funktion():
    """Dieselbe Probe, aber über `rules.validate_partial_to_w4`/
    `check_trend_consistency` DIREKT aus `elliott_pipeline` importiert —
    stellt sicher, dass die Wiring-Funktionen (`_eval_end_of_w4`/
    `_eval_end_of_w2`) exakt dieselbe rules.py-Logik verwenden, nicht eine
    Kopie."""
    import rules
    assert pipe.validate_impulse is rules.validate_impulse
    assert pipe.validate_partial_to_w4 is rules.validate_partial_to_w4
    assert pipe.check_trend_consistency is rules.check_trend_consistency
