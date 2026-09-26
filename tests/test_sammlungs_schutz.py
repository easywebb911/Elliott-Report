"""Sammlungs-Schutz: kein neuer Record aus veraltetem Kurs-Stand.

ANLASS (04.08.2026): die Quelle lieferte für beide Märkte eine nicht-finite
Tageszeile, die Härtung verwarf sie zu Recht, und der Report rechnete auf
Kursen vom 31.07. In diesem Zustand legte die Sammlung eine Episode an (KKR),
die es bei aktuellen Kursen nicht gäbe.

DIE HARTE INVARIANTE, die dabei nicht brechen darf: ein Lauf auf veraltetem
Markt-Stand darf bestehende Episoden **nicht beschädigen**. Naiv umgesetzt tut
er genau das — der übersprungene Lauf schreibt ``last_run_date`` fort, und der
nächste saubere Lauf findet die Records von vorgestern nicht mehr unter seinen
Ankern. Deshalb ankert jeder Markt auf seinen letzten **frischen** Lauf
(``last_fresh_run_date[markt]``), und ein gegateter Markt wird **komplett**
übersprungen — weder Anlage noch Verlängerung.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import forward_collection as fc  # noqa: E402
import mark_stale_market_records as msr  # noqa: E402
import market_calendar as cal  # noqa: E402

W4 = "Impuls 1–5 · Long-Setup am Ende W4 (W5 erwartet)"


def kand(ticker):
    return {"ticker": ticker, "close": 100.0, "score_heuristic": 80.0,
            "count_label": W4, "target_zone": {"low": 110.0, "high": 120.0},
            "target_zone_extended": {"low": 115.0, "high": 130.0},
            "invalidation_price": 90.0, "direction": "long",
            "chart_points": [], "count_wave_labels": [],
            "confluence": {"target": [], "invalidation": []}}


def rep(de=(), us=(), lag_de=0, lag_us=0):
    # Feld seit 17.09.2026: bar_lag_session_days (sitzungsbewusst) — das ist,
    # was fc.stale_markets() jetzt liest, nicht mehr bar_lag_trading_days.
    return {"markets": {
        "DE": {"candidates": [kand(t) for t in de],
               "diag": {"bar_lag_session_days": lag_de}},
        "US": {"candidates": [kand(t) for t in us],
               "diag": {"bar_lag_session_days": lag_us}}}}


def leer():
    return {"schema_version": 1, "last_run_date": None,
            "prev_distinct_run_date": None, "last_fresh_run_date": {},
            "updated_utc": None, "records": []}


def lauf(coll, report, run_date, now_iso=None):
    fc.update_forward_collection(coll, report, {}, {"DE": "risk_on", "US": "risk_on"},
                                 run_date, now_iso or f"{run_date}T22:45:00Z")
    return coll


def recs(coll, ticker):
    return [r for r in coll["records"] if r["ticker"] == ticker]


# ---------------------------------------------------------------------------
# 1) Welche Märkte gelten als veraltet?
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("lag, gegated", [
    (0, False), (1, False), (2, True), (7, True),
    (None, False), ("2", False), (True, False),   # unbrauchbar -> frisch
])
def test_stale_markets_schwelle_und_fail_soft(lag, gegated):
    """Schwelle ist unverändert >= config.HEALTH_BAR_LAG_CRIT (= 2, „crit").
    Feld seit 17.09.2026: `bar_lag_session_days` (sitzungsbewusst) statt
    `bar_lag_trading_days` (Kalendertag) — siehe Docstring von
    `stale_markets`. Fehlt oder taugt das Feld nicht, gilt der Markt als
    FRISCH — ein Gate, das aus Unwissen sperrt, hielte die Sammlung
    stillschweigend an, und das wäre schlimmer als der Schaden."""
    r = {"markets": {"DE": {"diag": {"bar_lag_session_days": lag}}}}
    assert ("DE" in fc.stale_markets(r)) is gegated


def test_stale_markets_schwelle_ist_dieselbe_zahl_wie_crit():
    """Keine zweite Definition von „veraltet genug, um zu sperren": dieselbe
    Konstante, ab der health_check.check_bar_freshness auf `crit` hochstuft."""
    import config as cfg
    import health_check as hc

    assert hc.BAR_LAG_CRIT == cfg.HEALTH_BAR_LAG_CRIT
    r = {"markets": {"DE": {"diag": {
        "bar_lag_session_days": cfg.HEALTH_BAR_LAG_CRIT - 1}}}}
    assert fc.stale_markets(r) == {}
    r2 = {"markets": {"DE": {"diag": {
        "bar_lag_session_days": cfg.HEALTH_BAR_LAG_CRIT}}}}
    assert "DE" in fc.stale_markets(r2)


def test_stale_markets_ohne_diag_und_ohne_feld():
    assert fc.stale_markets({"markets": {"DE": {}}}) == {}
    assert fc.stale_markets({"markets": {"DE": "kaputt"}}) == {}
    assert fc.stale_markets({}) == {}


def test_stale_markets_liest_jetzt_das_sitzungsbewusste_feld():
    """UMGESTELLT 17.09.2026 (vorher `bar_lag_trading_days`, der reine
    Kalendertag-Anker — diese Umstellung IST der Auftrag dieses PRs, keine
    Regression). Quelle ist jetzt `diag.bar_lag_session_days`, additiv seit
    05.09.2026 aus derselben Kalenderfunktion wie der Karten-Hinweis
    berechnet — keine zweite Definition."""
    quelle = (ROOT / "scripts/forward_collection.py").read_text(encoding="utf-8")
    assert 'lag = (market.get("diag") or {}).get("bar_lag_session_days")' in quelle
    assert 'lag = (market.get("diag") or {}).get("bar_lag_trading_days")' not in quelle
    # und die Zahl selbst kommt wirklich aus der sitzungsbewussten Funktion,
    # nicht mehr aus dem reinen Kalendertag-Rückstand — Gegenprobe an einem
    # Fall, an dem beide Werte nachweislich auseinanderlaufen (echter
    # KKR-Lauf, 04.08.2026 04:46 UTC, vor Börsenöffnung):
    ts = cal.parse_ts("2026-08-04T04:46:23Z")
    assert cal.handelstage_rueckstand("2026-07-31", "2026-08-04") == 2
    assert cal.handelstage_rueckstand_sitzung("2026-07-31", "US", ts) == 1


# ---------------------------------------------------------------------------
# 2) DIE HARTE INVARIANTE
# ---------------------------------------------------------------------------
def test_sauber_stale_sauber_ergibt_EINE_durchgehende_episode():
    """Der Kernbeweis. Ohne markt-bewusste Anker entstünden hier ZWEI Records —
    der Schutz würde genau die Episode zerschneiden, die er schützen soll."""
    c = leer()
    lauf(c, rep(de=["X"]), "2026-08-03")
    lauf(c, rep(de=["X"], lag_de=2), "2026-08-04")      # DE veraltet
    lauf(c, rep(de=["X"]), "2026-08-05")
    assert len(recs(c, "X")) == 1, "künstlicher Episoden-Abriss"
    assert recs(c, "X")[0]["last_seen_top5_date"] == "2026-08-05"
    assert recs(c, "X")[0]["episode_id"] == "X@2026-08-03"


def test_die_invariante_gilt_AUCH_wenn_der_ticker_am_stale_tag_fehlt():
    """Der Fall, an dem die einfachere Lösung („verlängern, nie anlegen")
    scheiterte: ob ein Ticker in den VERALTETEN Top 5 steht, ist genau die
    Information, die der Quellen-Aussetzer zerstört hat."""
    c = leer()
    lauf(c, rep(de=["X"]), "2026-08-03")
    lauf(c, rep(de=["Y"], lag_de=2), "2026-08-04")      # X fehlt, DE veraltet
    lauf(c, rep(de=["X"]), "2026-08-05")
    assert len(recs(c, "X")) == 1
    assert recs(c, "Y") == [], "am veralteten Tag darf nichts entstehen"


def test_mehrere_stale_tage_hintereinander_ueberbruecken_ebenfalls():
    c = leer()
    lauf(c, rep(de=["X"]), "2026-08-03")
    for tag in ("2026-08-04", "2026-08-05", "2026-08-06"):
        lauf(c, rep(de=["X"], lag_de=2), tag)
    lauf(c, rep(de=["X"]), "2026-08-07")
    assert len(recs(c, "X")) == 1
    assert c["last_fresh_run_date"]["DE"] == "2026-08-07"


def test_eine_ECHTE_unterbrechung_an_frischen_tagen_bleibt_eine_unterbrechung():
    """Das Gate darf echte Lücken nicht wegbügeln."""
    c = leer()
    lauf(c, rep(de=["X"]), "2026-08-03")
    lauf(c, rep(de=["Y"]), "2026-08-04")               # frisch, X fehlt
    lauf(c, rep(de=["X"]), "2026-08-05")
    assert len(recs(c, "X")) == 2
    assert [r["last_seen_top5_date"] for r in recs(c, "X")] == \
        ["2026-08-03", "2026-08-05"]


# ---------------------------------------------------------------------------
# 3) Je Markt, nicht global
# ---------------------------------------------------------------------------
def test_US_frisch_und_DE_veraltet_sammelt_US_normal_weiter():
    c = leer()
    lauf(c, rep(de=["D1"], us=["U1"]), "2026-08-03")
    lauf(c, rep(de=["D2"], us=["U2"], lag_de=2), "2026-08-04")
    assert sorted(r["ticker"] for r in c["records"]) == ["D1", "U1", "U2"]
    assert c["last_fresh_run_date"] == {"DE": "2026-08-03", "US": "2026-08-04"}


def test_der_gegatete_markt_haelt_seinen_frischen_lauf_fest():
    c = leer()
    lauf(c, rep(de=["X"], us=["A"]), "2026-08-03")
    lauf(c, rep(de=["X"], us=["A"], lag_de=2), "2026-08-04")
    assert c["last_fresh_run_date"]["DE"] == "2026-08-03"   # steht still
    assert c["last_fresh_run_date"]["US"] == "2026-08-04"   # wandert mit
    assert sorted(fc.episode_anchor_dates(c, "2026-08-05", "DE")) == \
        ["2026-08-03", "2026-08-05"]
    assert sorted(fc.episode_anchor_dates(c, "2026-08-05", "US")) == \
        ["2026-08-04", "2026-08-05"]


# ---------------------------------------------------------------------------
# 4) Anker ohne Markt = exakt #68
# ---------------------------------------------------------------------------
def test_ohne_markt_gilt_unveraendert_das_verhalten_von_68():
    c = {"last_run_date": "2026-08-04", "prev_distinct_run_date": "2026-08-03",
         "last_fresh_run_date": {"DE": "2026-08-03"}}
    assert fc.episode_anchor_dates(c, "2026-08-05") == {"2026-08-05", "2026-08-04"}
    assert fc.episode_anchor_dates(c, "2026-08-05", "XX") == {"2026-08-05", "2026-08-04"}
    assert fc.episode_anchor_dates(c, "2026-08-05", "DE") == {"2026-08-05", "2026-08-03"}


def test_ohne_das_feld_gilt_ebenfalls_68():
    """Migration: Sammlungs-Stände von vor dem 05.08. haben kein
    `last_fresh_run_date` — dann zählt `last_run_date` wie bisher."""
    c = {"last_run_date": "2026-08-04", "prev_distinct_run_date": "2026-08-03"}
    assert fc.episode_anchor_dates(c, "2026-08-05", "DE") == {"2026-08-05", "2026-08-04"}


@pytest.mark.parametrize("kaputt", ["kaputt", 7, [], None])
def test_ein_unbrauchbares_last_fresh_run_date_bricht_den_LAUF_nicht(kaputt):
    """Guardian-Nit: der Nicht-Dict-Fall war nur an `episode_anchor_dates`
    geprüft, nicht am vollen Lauf. Ein fremd beschriebenes oder von Hand
    kaputtgemachtes Feld darf die Sammlung weder abstürzen lassen noch die
    Episode zerschneiden — sie fällt auf #68 zurück und heilt das Feld beim
    nächsten Schreiben selbst."""
    c = leer()
    lauf(c, rep(de=["X"]), "2026-08-03")
    c["last_fresh_run_date"] = kaputt
    lauf(c, rep(de=["X"]), "2026-08-04")
    assert len(recs(c, "X")) == 1
    assert recs(c, "X")[0]["last_seen_top5_date"] == "2026-08-04"
    # danach steht wieder ein brauchbares Feld da
    assert c["last_fresh_run_date"] == {"DE": "2026-08-04", "US": "2026-08-04"}


# ---------------------------------------------------------------------------
# 5) Der echte 04.08.-Fall: KKR wäre nicht entstanden
# ---------------------------------------------------------------------------
def test_der_echte_KKR_lauf_sitzungsbewusst_nachgerechnet_zeigt_nur_lag_1():
    """WICHTIGE NUANCE (17.09.2026, Umstellungs-Diagnose): der reale
    KKR-auslösende Lauf (04.08.2026 04:46 UTC) zeigt sitzungsbewusst
    nachgerechnet für US nur Rückstand 1, nicht 2 — unter der Schwelle
    (>= 2). Das Sammlungs-Gate ALLEIN hätte diesen Lauf mit dem neuen Feld
    also NICHT mehr gesperrt. Das ist ehrlich benannt, nicht verschwiegen —
    siehe `test_das_sammlungs_gate_allein_haette_KKR_nicht_mehr_gestoppt`
    und die Gegenprobe direkt danach (#130 blockiert den Dispatch selbst)."""
    ts = cal.parse_ts("2026-08-04T04:46:23Z")
    assert cal.handelstage_rueckstand("2026-07-31", "2026-08-04") == 2, (
        "Kalendertag-Anker (alt, bis #129/#130): 2 — daher wurde KKR historisch "
        "verhindert, das ist unverändert wahr für den DAMALIGEN Code-Stand")
    assert cal.handelstage_rueckstand_sitzung("2026-07-31", "US", ts) == 1, (
        "sitzungsbewusst (neu, dieser PR): nur 1 — unter der Schwelle 2")


def test_das_sammlungs_gate_allein_haette_KKR_nicht_mehr_gestoppt():
    """Direkte Konsequenz der Nuance oben, am echten `stale_markets()`
    nachgewiesen: mit dem sitzungsbewussten Rückstand (1) legt der Lauf KKR
    an — das Sammlungs-Gate für sich genommen reicht hier nicht mehr."""
    c = leer()
    lauf(c, rep(us=["AJG"]), "2026-08-03")
    lauf(c, rep(us=["AJG", "KKR"], lag_us=1), "2026-08-04",
         "2026-08-04T04:46:23Z")
    assert sorted(r["ticker"] for r in c["records"]) == ["AJG", "KKR"], (
        "mit dem echten sitzungsbewussten Rückstand (1) sperrt das "
        "Sammlungs-Gate diesen Lauf nicht mehr — erwartetes, dokumentiertes "
        "Verhalten dieses PRs, keine übersehene Regression")


def test_aber_130_haette_den_vormittags_dispatch_gar_nicht_erst_durchgelassen():
    """Kein Widerspruch zu den beiden Tests oben: KKRs Lauf war selbst ein
    Vormittags-Dispatch (04:46 UTC, vor beiden Börsenöffnungen) — GENAU die
    Klasse, die das Sitzungs-Gate aus #130 (17.09.2026) seit seiner
    Einführung bereits vor Erreichen der Pipeline vollständig blockiert.
    Verteidigung in der Tiefe: zwei unabhängige Ebenen statt einer."""
    import in_session as ins

    ts_iso, ts = "2026-08-04T04:46:23Z", cal.parse_ts("2026-08-04T04:46:23Z")
    for markt in ("US", "DE"):
        assert ins.im_sitzungsfenster(markt, ts_iso) is False, (
            f"{markt}: waere von der urspruenglichen (#125) Fassung des "
            "Sitzungs-Gates NICHT erfasst worden")
        assert cal.sitzung_beendet(markt, ts) is False, (
            f"{markt}: die ERWEITERTE Fassung (#130) haette diesen "
            "Vormittags-Dispatch trotzdem blockiert")


def test_ohne_gate_waere_KKR_entstanden():
    """Gegenprobe: dieselbe Sequenz mit lag 0 legt KKR an — der Unterschied
    kommt wirklich vom Gate und nicht von der Testkonstruktion."""
    c = leer()
    lauf(c, rep(us=["AJG"]), "2026-08-03")
    lauf(c, rep(us=["AJG", "KKR"], lag_us=0), "2026-08-04")
    assert sorted(r["ticker"] for r in c["records"]) == ["AJG", "KKR"]


# ---------------------------------------------------------------------------
# 6) Reifung läuft weiter — bewusst, weil idempotent
# ---------------------------------------------------------------------------
def _rec_fuer_reifung():
    return {"ticker": "X", "first_seen_date": "2026-07-27", "entry_close": 100.0,
            "invalidation_price": 90.0, "target_zone": {"low": 130.0, "high": 140.0},
            "target_zone_extended": {"low": 150.0, "high": 160.0},
            "direction": "long", "matured": False, "bars_elapsed": 0,
            "target_hit": None, "ext_hit": None, "invalidated": None,
            "price_path": [], "pre_reached_target": False, "pre_reached_ext": False}


def test_ein_stale_tag_verschiebt_die_reifung_NICHT():
    """Nachweis für die Registry-Aussage „läuft bewusst weiter, weil idempotent
    aus der Kursreihe neu gerechnet": der Endzustand ist mit und ohne stale
    Zwischenlauf in JEDEM gemessenen Feld identisch."""
    nan = float("nan")
    daten = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]
    kurse = [100.0, 101.0, 102.0, 103.0, 104.0]

    mit = _rec_fuer_reifung()
    fc.mature_record(mit, daten[:3], kurse[:3], "t1")
    fc.mature_record(mit, daten[:4], kurse[:3] + [nan], "t2")     # stale
    fc.mature_record(mit, daten, kurse, "t3")                     # nachgeliefert

    ohne = _rec_fuer_reifung()
    fc.mature_record(ohne, daten[:3], kurse[:3], "t1")
    fc.mature_record(ohne, daten, kurse, "t3")

    for feld in ("bars_elapsed", "price_path", "matured", "target_hit",
                 "invalidated", "ext_hit", "skipped_bars"):
        assert mit.get(feld) == ohne.get(feld), feld
    assert len({p["date"] for p in mit["price_path"]}) == len(mit["price_path"])


def test_skipped_bars_klebt_nicht_mehr():
    """Variante (b): setzen wenn > 0, sonst ENTFERNEN. Vorher behauptete ein
    Record nach der Nachlieferung dauerhaft einen übersprungenen Bar."""
    nan = float("nan")
    d = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30"]
    k = [100.0, 101.0, 102.0, 103.0]
    r = _rec_fuer_reifung()
    fc.mature_record(r, d[:3], k[:2] + [nan], "t1")
    assert r["skipped_bars"] == 1
    fc.mature_record(r, d, k, "t2")
    assert "skipped_bars" not in r, "das Feld klebt"


def test_der_bestand_traegt_heute_kein_skipped_bars():
    """Beleg für „Daten-Diff leer": Variante (a) hätte allen Records ein
    `skipped_bars: 0` angehängt."""
    coll = json.loads((ROOT / "data/forward_collection.json").read_text("utf-8"))
    assert [r["ticker"] for r in coll["records"] if "skipped_bars" in r] == []


# ---------------------------------------------------------------------------
# 7) N×-Zähler zieht mit
# ---------------------------------------------------------------------------
def test_appearance_count_benutzt_die_markt_anker():
    c = leer()
    lauf(c, rep(de=["X"]), "2026-08-03")
    lauf(c, rep(de=["Y"], lag_de=2), "2026-08-04")     # DE gegated
    # Am 05.08. verlängert X seine Episode -> weiterhin EINE Erscheinung.
    assert fc.appearance_count(c, "X", "2026-08-05", "DE") == 1
    # Ohne Markt-Angabe greift der alte Anker -> zählt als neue Erscheinung.
    assert fc.appearance_count(c, "X", "2026-08-05") == 2


def test_annotate_appearance_counts_reicht_den_markt_durch():
    c = leer()
    lauf(c, rep(de=["X"]), "2026-08-03")
    lauf(c, rep(de=["Y"], lag_de=2), "2026-08-04")
    r = rep(de=["X"])
    fc.annotate_appearance_counts(c, r, "2026-08-05")
    assert r["markets"]["DE"]["candidates"][0]["appearance_count"] == 1


# ---------------------------------------------------------------------------
# 8) LAUT statt still
# ---------------------------------------------------------------------------
def test_die_pipeline_schreibt_die_gate_notiz_in_den_report():
    quelle = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    assert '_gated = fc.stale_markets({"markets": markets})' in quelle
    assert '_m["diag"]["new_episodes_gated"] = _mk in _gated' in quelle
    assert "keine neuen Episoden — Kurs-Stand veraltet" in quelle


def test_das_frontend_zeigt_die_notiz_nur_wenn_sie_gilt():
    html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert "function gatedRow(d)" in html
    assert "if (d.new_episodes_gated !== true) return '';" in html
    assert "${gatedRow(d)}" in html


def test_das_gate_erzeugt_KEINEN_eigenen_push():
    """Der Kurs-Stand-Wächter meldet dieselbe Lage bereits — ein zweiter Alarm
    wäre ein Doppel-Alarm. Es darf also keine Health-Regel dafür geben."""
    hc_quelle = (ROOT / "scripts/health_check.py").read_text(encoding="utf-8")
    assert "new_episodes_gated" not in hc_quelle
    assert "stale_market" not in hc_quelle


# ---------------------------------------------------------------------------
# 9) Marker über die echte Historie
#
# ZWEI GETRENNTE LISTEN, BEWUSST NICHT DIESELBE (Diagnose 22.09.2026, siehe
# docs/validation_registry.md):
# - ERWARTETE_MARKIERUNGEN: was TATSÄCHLICH im committeten `forward_
#   collection.json` markiert ist (`mark_stale_market_records.py --live`,
#   ein manueller, bewusster Schritt — läuft NICHT automatisch mit jedem
#   Tageslauf). Ändert sich nur, wenn Easy das Skript live laufen lässt.
# - ERWARTETE_REPLAY_TREFFER: was `finde_stale_records()` HEUTE beim
#   Nachrechnen über die committete Rohhistorie findet — wächst mit jedem
#   neuen echten Stale-Market-Vorfall, UNABHÄNGIG davon, ob er schon markiert
#   wurde. Die beiden laufen bewusst auseinander, bis der nächste `--live`-
#   Lauf sie wieder deckungsgleich macht.
#
# AOF.DE (DE, Lauf 2026-09-22T01:09:47Z, Rückstand 2) kam in der Nacht vom
# 21./22.09.2026 hinzu — ein echter, neuer Kalendertag-Rückstand ≥2, per
# `finde_stale_records()` gegen die volle committete Historie nachgerechnet
# (nicht geraten). Gehört in ERWARTETE_REPLAY_TREFFER, NICHT in
# ERWARTETE_MARKIERUNGEN — dafür fehlt der `--live`-Marker-Lauf noch.
#
# NEM (US, Lauf 2026-09-23T00:55:39Z, Rückstand 2) kam in der Nacht vom
# 22./23.09.2026 ebenso hinzu — wieder per `finde_stale_records()` gegen die
# volle committete Historie nachgerechnet (nicht geraten; per
# `git fetch --unshallow` verifiziert, 135 Reports/116 Sammlungs-Stände).
# Gleiches Muster wie AOF.DE: gehört in ERWARTETE_REPLAY_TREFFER, NICHT in
# ERWARTETE_MARKIERUNGEN.
#
# STM.DE/AMZN/DELL/ADM/GILD/TXN/VNA.DE kamen in den Nächten vom 23.–26.09.2026
# hinzu — wieder per `finde_stale_records()` gegen die volle committete
# Historie nachgerechnet (nicht geraten; verifiziert: Repo nicht flach,
# 141 Reports/119 Sammlungs-Stände). Gleiches Muster: gehören in
# ERWARTETE_REPLAY_TREFFER, NICHT in ERWARTETE_MARKIERUNGEN.
# ---------------------------------------------------------------------------
ERWARTETE_MARKIERUNGEN = [
    ("ADS.DE", "DE", "2026-07-30T22:45:00Z", 1),
    ("MTX.DE", "DE", "2026-07-31T22:40:44Z", 1),
    ("G1A.DE", "DE", "2026-07-31T22:40:44Z", 1),
    ("KKR", "US", "2026-08-04T04:46:23Z", 2),
]

ERWARTETE_REPLAY_TREFFER = ERWARTETE_MARKIERUNGEN + [
    ("AOF.DE", "DE", "2026-09-22T01:09:47Z", 2),
    ("NEM", "US", "2026-09-23T00:55:39Z", 2),
    ("STM.DE", "DE", "2026-09-24T00:52:41Z", 2),
    ("AMZN", "US", "2026-09-25T00:49:09Z", 2),
    ("DELL", "US", "2026-09-25T00:49:09Z", 2),
    ("ADM", "US", "2026-09-25T00:49:09Z", 2),
    ("GILD", "US", "2026-09-26T00:52:46Z", 1),
    ("TXN", "US", "2026-09-26T00:52:46Z", 1),
    ("VNA.DE", "DE", "2026-09-26T00:52:46Z", 1),
]


def _flach() -> bool:
    out = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                         cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() == "true"


braucht_historie = pytest.mark.skipif(
    _flach(), reason="flacher Klon — der Replay braucht die volle Historie")


@pytest.fixture(scope="module")
def replay():
    reports = msr.committete_reports(ROOT)
    coll_st = msr.committete_sammlungen(ROOT)
    assert len(reports) >= 40 and len(coll_st) >= 40, "Historie unvollständig"
    return msr.finde_stale_records(coll_st, msr.rueckstaende_je_lauf(reports))


@braucht_historie
def test_der_replay_findet_die_bekannten_faelle(replay):
    """Hieß bis 22.09.2026 '...findet_genau_die_vier_faelle' — der Name
    behauptete eine feste Zahl, die per Konstruktion wächst (jeder neue
    echte Stale-Market-Vorfall kommt automatisch dazu). Bewusst umbenannt,
    nicht nur die Zahl im Namen erhöht — sonst wiederholt sich genau das
    Muster, das AOF.DE hier ausgelöst hat, beim nächsten echten Vorfall."""
    gefunden = [(t["ticker"], t["market"], t["run_utc"], t["lag_trading_days"])
                for t in replay]
    assert gefunden == ERWARTETE_REPLAY_TREFFER


@braucht_historie
def test_KKR_ist_dabei_und_traegt_den_lauf_vom_04_08(replay):
    kkr = [t for t in replay if t["ticker"] == "KKR"]
    assert len(kkr) == 1
    assert kkr[0]["run_utc"] == "2026-08-04T04:46:23Z"
    assert kkr[0]["lag_trading_days"] == 2


def test_der_ausgelieferte_bestand_traegt_die_vier_marker():
    coll = json.loads((ROOT / "data/forward_collection.json").read_text("utf-8"))
    markiert = [(r["ticker"], r["market"], r[msr.MARKER]["run_utc"],
                 r[msr.MARKER]["lag_trading_days"])
                for r in coll["records"] if msr.MARKER in r]
    assert sorted(markiert) == sorted(ERWARTETE_MARKIERUNGEN)
    spiegel = (ROOT / "docs/data/forward_collection.json").read_bytes()
    assert spiegel == (ROOT / "data/forward_collection.json").read_bytes()


def test_drei_records_tragen_BEIDE_marker():
    """Ausdrücklich festgehalten: die Marker überlappen. Die Entscheidung vor
    der ersten Auswertung muss beide zusammen behandeln, sonst würde ein Record
    je nach Reihenfolge zweimal oder gar nicht ausgeschlossen."""
    coll = json.loads((ROOT / "data/forward_collection.json").read_text("utf-8"))
    beide = sorted(r["ticker"] for r in coll["records"]
                   if msr.MARKER in r and "episode_split_suspect" in r)
    assert beide == ["ADS.DE", "G1A.DE", "MTX.DE"]


# ---------------------------------------------------------------------------
# 10) Marker-Mechanik + Rückweg
# ---------------------------------------------------------------------------
def _treffer_aus_erwartung():
    coll = json.loads((ROOT / "data/forward_collection.json").read_text("utf-8"))
    out = []
    for r in coll["records"]:
        m = r.get(msr.MARKER)
        if m:
            out.append({"key": msr.record_key(r), "ticker": r["ticker"],
                        "market": r["market"], "episode_id": r["episode_id"],
                        "run_utc": m["run_utc"],
                        "lag_trading_days": m["lag_trading_days"]})
    return out


def _unmarkiert():
    coll = json.loads((ROOT / "data/forward_collection.json").read_text("utf-8"))
    msr.entferne_marker(coll)
    return coll


def test_der_marker_aendert_NUR_das_marker_feld():
    coll = _unmarkiert()
    vorher = copy.deepcopy(coll)
    treffer = _treffer_aus_erwartung()
    last_bars = {t["key"]: "2026-07-31" for t in treffer}
    assert msr.setze_marker(coll, treffer, "2026-08-05", last_bars) == 4
    assert set(coll) == set(vorher)
    for neu, alt in zip(coll["records"], vorher["records"]):
        diff = {k for k in set(neu) | set(alt) if neu.get(k) != alt.get(k)}
        assert diff <= {msr.MARKER}, (neu["ticker"], diff)


def test_markieren_ist_idempotent():
    coll = _unmarkiert()
    treffer = _treffer_aus_erwartung()
    lb = {t["key"]: "2026-07-31" for t in treffer}
    assert msr.setze_marker(coll, treffer, "2026-08-05", lb) == 4
    zwischen = copy.deepcopy(coll)
    assert msr.setze_marker(coll, treffer, "2026-08-05", lb) == 0
    assert coll == zwischen


def test_purge_stellt_byte_identitaet_her(tmp_path):
    for rel in msr.REL_PATHS:
        ziel = tmp_path / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes((ROOT / rel).read_bytes())
    assert msr.main(["--path", str(tmp_path), "--purge", "--live"]) == 0
    basis = {rel: (tmp_path / rel).read_bytes() for rel in msr.REL_PATHS}
    for rel, roh in basis.items():
        assert msr.MARKER.encode() not in roh

    treffer = _treffer_aus_erwartung()
    lb = {t["key"]: "2026-07-31" for t in treffer}
    for rel in msr.REL_PATHS:
        coll = json.loads((tmp_path / rel).read_text(encoding="utf-8"))
        assert msr.setze_marker(coll, treffer, "2026-08-05", lb) == 4
        msr._schreibe(tmp_path / rel, coll)
        assert (tmp_path / rel).read_bytes() != basis[rel]

    assert msr.main(["--path", str(tmp_path), "--purge", "--live"]) == 0
    for rel in msr.REL_PATHS:
        assert (tmp_path / rel).read_bytes() == basis[rel]


def test_ohne_datum_verweigert_das_programm(tmp_path):
    for rel in msr.REL_PATHS:
        ziel = tmp_path / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes((ROOT / rel).read_bytes())
    assert msr.main(["--path", str(tmp_path), "--live"]) == 2


def test_der_erste_bestand_gilt_nicht_als_neu_angelegt():
    """Sonst würde der gesamte Anfangsbestand markiert, sobald sein erster
    Stand zufällig auf einem veralteten Lauf lag."""
    staende = [{"updated_utc": "2026-08-03T22:45:00Z",
                "records": [{"ticker": "A", "market": "DE",
                             "created_utc": "2026-08-03T22:45:00Z"}]}]
    lags = {"2026-08-03T22:45:00Z": {"DE": 2}}
    assert msr.finde_stale_records(staende, lags) == []


def test_ein_record_auf_frischem_markt_wird_NICHT_markiert():
    staende = [
        {"updated_utc": "2026-08-03T22:45:00Z", "records": []},
        {"updated_utc": "2026-08-04T22:45:00Z",
         "records": [{"ticker": "A", "market": "US",
                      "created_utc": "2026-08-04T22:45:00Z"},
                     {"ticker": "B", "market": "DE",
                      "created_utc": "2026-08-04T22:45:00Z"}]},
    ]
    lags = {"2026-08-04T22:45:00Z": {"US": 0, "DE": 2}}
    treffer = msr.finde_stale_records(staende, lags)
    assert [t["ticker"] for t in treffer] == ["B"]


# ---------------------------------------------------------------------------
# 11) Auswertung v1 bleibt eingefroren
# ---------------------------------------------------------------------------
def test_evaluate_v1_ist_byte_identisch():
    import hashlib
    ist = hashlib.sha256((ROOT / "scripts/evaluate.py").read_bytes()).hexdigest()
    assert ist == ("bc697df91235732c6c386abe38c79a98248488b9f30a239d9c26c3cbb"
                   "3b513fc"), "evaluate.py wurde verändert — v1 ist eingefroren"


def test_die_auswertung_sieht_den_neuen_marker_NICHT():
    ev = pytest.importorskip("evaluate")
    coll = _unmarkiert()
    ohne = ev.build_population(coll)
    treffer = _treffer_aus_erwartung()
    msr.setze_marker(coll, treffer, "2026-08-05",
                     {t["key"]: "2026-07-31" for t in treffer})
    mit = ev.build_population(coll)
    assert ohne[1] == mit[1]
    assert [tuple(f) for f in ohne[0]] == [tuple(f) for f in mit[0]]


def test_der_marker_steht_nicht_in_FROZEN_FIELDS():
    ev = pytest.importorskip("evaluate")
    assert msr.MARKER not in ev.FROZEN_FIELDS
    assert "episode_split_suspect" not in ev.FROZEN_FIELDS


# ---------------------------------------------------------------------------
# 12) Äquivalenz über die echte Historie
#
# Die eigentliche Rückwärts-Frage: ändert der markt-bewusste Anker an FRISCHEN
# Tagen irgendetwas? Er darf nicht. Population: jeder committete Sammlungs-Stand
# x die Märkte seines Laufs; frisch = Rückstand 0 ODER nicht messbar (fail-soft,
# genau wie im Gate). Der Test rechnet die Zahlen JEDES MAL neu — er pinnt keine
# Momentaufnahme, sondern die Invariante.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def markt_laeufe():
    """(sammlungs_stand, lauf_datum, markt, rueckstand) über die Historie."""
    reports = msr.committete_reports(ROOT)
    lags = msr.rueckstaende_je_lauf(reports)
    maerkte = {r["run_timestamp_utc"]: sorted(r.get("markets") or {})
               for r in reports}
    out = []
    for coll in msr.committete_sammlungen(ROOT):
        ts = str(coll.get("updated_utc"))
        for mk in maerkte.get(ts, []):
            out.append((coll, ts, mk, lags.get(ts, {}).get(mk)))
    return out


@braucht_historie
def test_an_frischen_tagen_ankert_der_markt_wie_bisher(markt_laeufe):
    frisch = [z for z in markt_laeufe
              if not (isinstance(z[3], int) and z[3] >= 1)]
    assert len(frisch) >= 97, "Historie unerwartet klein — Beweis wertlos"
    abweichungen = []
    for coll, ts, mk, _lag in frisch:
        run_date = ts[:10]
        alt = set(fc.episode_anchor_dates(coll, run_date))
        neu = set(fc.episode_anchor_dates(coll, run_date, mk))
        if alt != neu:
            abweichungen.append((ts, mk, sorted(alt), sorted(neu)))
    assert abweichungen == []


# ---------------------------------------------------------------------------
# 12b) Historischer Abgleich UMGESTELLT auf das sitzungsbewusste Feld
# (17.09.2026). Die bis #129 hier stehenden `BEKANNT_GEGATET`-Mengen und die
# vier Tests darauf prüften „sperrt der ECHTE Gate-Code dieselben Läufe wie
# der reine Kalendertag-Rückstand" — eine Frage, die sich nach der Umstellung
# nicht mehr sinnvoll stellt, weil das Gate diesen Rückstand gar nicht mehr
# liest. `mark_stale_market_records.py`/`rueckstaende_je_lauf` bleiben
# BEWUSST beim Kalendertag-Anker (GRENZEN: das ist die historische
# Markierung, sie beschreibt, was der DAMALIGE Gate-Code wirklich tat — das
# darf sich nicht rückwirkend ändern). Ersetzt durch einen eigenen,
# sitzungsbewussten Nachbau unten, der `cal.handelstage_rueckstand_sitzung`
# direkt auf dieselbe committete Historie anwendet — keine neue Berechnung,
# nur derselbe (unveränderte) Aufruf, den `_annotiere_bar_rueckstand` auch
# in der Pipeline macht.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def markt_laeufe_sitzung():
    """(coll, ts, markt, sitzungsbewusster_rueckstand) — Gegenstück zu
    `markt_laeufe`, aber mit `cal.handelstage_rueckstand_sitzung` statt
    `cal.handelstage_rueckstand`."""
    reports = msr.committete_reports(ROOT)
    by_ts = {r.get("run_timestamp_utc"): r for r in reports}
    maerkte = {ts: sorted(r.get("markets") or {}) for ts, r in by_ts.items()}
    out = []
    for coll in msr.committete_sammlungen(ROOT):
        ts = str(coll.get("updated_utc"))
        r = by_ts.get(ts)
        if r is None:
            continue
        jetzt = cal.parse_ts(ts)
        for mk in maerkte.get(ts, []):
            bar = ((r.get("markets") or {}).get(mk) or {}).get("diag", {}).get("last_bar_date")
            lag = cal.handelstage_rueckstand_sitzung(bar, mk, jetzt) if jetzt else None
            out.append((coll, ts, mk, lag))
    return out


def _gesperrt_sitzung(markt_laeufe_sitzung):
    """Die gegateten Markt-Läufe — durch den ECHTEN Gate-Code, mit dem
    sitzungsbewussten Rückstand."""
    out = set()
    for _c, ts, mk, lag in markt_laeufe_sitzung:
        report = {"markets": {mk: {"diag": {"bar_lag_session_days": lag}}}}
        if mk in fc.stale_markets(report):
            out.add((ts, mk, lag))
    return out


@braucht_historie
def test_der_einzige_echte_crit_fall_bleibt_gegatet(markt_laeufe_sitzung):
    """Über die gesamte committete Historie: welche Markt-Läufe sperrt das
    UMGESTELLTE Gate wirklich? Sitzungsbewusst ist das erheblich seltener als
    der alte Kalendertag-Anker — genau der Punkt dieses PRs. Kein Zähler-Pin
    (die Historie wächst), sondern eine Mindestanforderung: der bekannte
    09.09.-Vorfall (US, `last_bar_date` vier Handelstage alt) MUSS darunter
    sein."""
    gesperrt = _gesperrt_sitzung(markt_laeufe_sitzung)
    treffer = [(ts, mk, lag) for ts, mk, lag in gesperrt if ts.startswith("2026-09-09")]
    assert any(mk == "US" for _ts, mk, _lag in treffer), (
        "der echte mehrtaegige US-Ausfall vom 09.09. muss weiterhin gesperrt sein")


@braucht_historie
def test_die_KKR_ausloesenden_laeufe_sind_sitzungsbewusst_nicht_mehr_gegatet(markt_laeufe_sitzung):
    """Direkte Fortsetzung von `test_der_echte_KKR_lauf_sitzungsbewusst_
    nachgerechnet_zeigt_nur_lag_1` — hier über den ECHTEN historischen
    Nachbau statt einer Handrechnung bestätigt: der 04.08.-Lauf (04:46 UTC)
    ist mit dem neuen Feld NICHT mehr in der gesperrten Menge."""
    gesperrt = {(ts, mk) for ts, mk, _lag in _gesperrt_sitzung(markt_laeufe_sitzung)}
    assert ("2026-08-04T04:46:23Z", "US") not in gesperrt
    assert ("2026-08-04T04:46:23Z", "DE") not in gesperrt


@braucht_historie
def test_alle_vier_alt_records_waeren_beim_heutigen_gate_allein_nicht_mehr_gesperrt(markt_laeufe_sitzung):
    """Kehrseite: ALLE VIER markierten Alt-Records (nicht mehr nur drei von
    vier wie unter dem Kalendertag-Anker bei Schwelle >= 2) hängen an Läufen,
    die das heutige, sitzungsbewusste Gate allein nicht mehr sperren würde.
    Sie bleiben trotzdem MARKIERT (MET/D/PRU-Prinzip: markiert, niemals
    geheilt) — dieser Test dokumentiert nur den heutigen Gate-Befund, ändert
    keinen Marker. Für KKR greift zusätzlich #130 (siehe oben) — für die
    anderen drei war das ohnehin schon seit #129 so."""
    gesperrt = {(ts, mk) for ts, mk, _lag in _gesperrt_sitzung(markt_laeufe_sitzung)}
    for _ticker, markt, run_utc, _lag in ERWARTETE_MARKIERUNGEN:
        assert (run_utc, markt) not in gesperrt, (
            f"{run_utc}/{markt} sollte mit dem sitzungsbewussten Feld nicht mehr sperren")


# ---------------------------------------------------------------------------
# 13) Wert-Test mit den echten Diagnose-Fällen (10.–16.09.2026) + Regression
# ---------------------------------------------------------------------------
# Reale Top-5-Ausschnitte aus den committeten Nacht-Cron-Reports (per
# `git show <Commit>:data/report.json`, s. Diagnose 16./17.09.) —
# SITZUNGSBEWUSST lagen US/DE an allen sechs Nächten tatsächlich bei genau
# Rückstand 1 (bestätigt gegen `diag.bar_lag_session_days` in den echten
# Reports, nicht nur behauptet) — anders als der fehlerhafte Kalendertag-
# Anker, der an 5 dieser 6 Nächte 2 zeigte. NEM/BAC/CVX/MDT/SFQ.DE/FRE.DE
# trugen an ihrem jeweiligen Tag KEINE offene Episode (per Abgleich gegen
# data/forward_collection.json), wären bei Schwelle >= 1 also weiterhin nie
# angelegt worden — nur die Kombination aus KORREKTEM Feld UND Schwelle >= 2
# (dieser PR) löst den 7-Tage-Stillstand tatsächlich auf.
DIAGNOSE_FAELLE_LAG1 = [
    ("2026-09-12", "US", "NEM"),
    ("2026-09-15", "US", "BAC"),
    ("2026-09-15", "US", "CVX"),
    ("2026-09-15", "US", "MDT"),
    ("2026-09-15", "DE", "SFQ.DE"),
    ("2026-09-16", "US", "NEM"),
    ("2026-09-16", "US", "BAC"),
    ("2026-09-16", "US", "CVX"),
    ("2026-09-16", "DE", "FRE.DE"),
]


@pytest.mark.parametrize("run_date, markt, ticker", DIAGNOSE_FAELLE_LAG1)
def test_echte_lag1_faelle_aus_der_diagnose_wuerden_jetzt_angelegt(run_date, markt, ticker):
    """Wert-Test: dieselbe Konstellation wie in der Diagnose (sitzungsbewusst
    Rückstand 1 in beiden Märkten, echter neuer Kandidat ohne offene
    Episode) — mit dem korrekten Feld (Schwelle unverändert >= 2) entsteht
    der Record; mit der Schwelle allein auf dem alten Kalendertag-Feld wäre
    er wie in der Realität ausgeblieben (siehe nächster Test)."""
    c = leer()
    kw = {"de": [ticker], "lag_de": 1} if markt == "DE" else {"us": [ticker], "lag_us": 1}
    lauf(c, rep(**kw), run_date)
    assert recs(c, ticker) != [], (
        f"{ticker} ({markt}, sitzungsbewusster Rückstand 1) hätte jetzt angelegt werden müssen")


@pytest.mark.parametrize("run_date, markt, ticker", DIAGNOSE_FAELLE_LAG1)
def test_altes_feld_und_schwelle_1_haetten_dieselben_faelle_weiterhin_blockiert(
        run_date, markt, ticker):
    """Gegenprobe — belegt, dass der Unterschied wirklich vom Feld+Schwelle
    kommt: mit der Schwelle 1 (egal welches Feld) bliebe NEM & Co. weiterhin
    ungesammelt — exakt der 7-Tage-Stillstand aus der Diagnose. Direkt am
    Fixture-Wert nachgebildet, nicht über das inzwischen geänderte
    `stale_markets`."""
    kw = {"de": [ticker], "lag_de": 1} if markt == "DE" else {"us": [ticker], "lag_us": 1}
    report = rep(**kw)
    ALTE_SCHWELLE = 1
    stale_alt = {mk for mk, m in report["markets"].items()
                 if (m.get("diag") or {}).get("bar_lag_session_days", 0) >= ALTE_SCHWELLE}
    assert markt in stale_alt, "Testkonstruktion: der Fall muss bei Schwelle 1 gegatet sein"


def test_echter_lag2_fall_aus_der_diagnose_blockiert_weiterhin():
    """Regressionstest mit echten Diagnose-Daten: der Nacht-Cron-Lauf vom
    09.09.2026 (Commit 8436bb0) meldete für US tatsächlich sitzungsbewusst
    Rückstand 2 (`bar_lag_session_days`, direkt aus dem committeten Report
    bestätigt — nicht der noch höhere, fehlerhafte Kalendertag-Wert) — dieser
    Fall MUSS auch mit dem umgestellten Feld weiterhin sperren; nur der
    chronische Rückstand-1-Zustand sollte durchgelassen werden."""
    c = leer()
    lauf(c, rep(us=["OXY"], lag_us=2), "2026-09-09")
    assert recs(c, "OXY") == [], "ein echter Rückstand-2-Fall muss weiterhin sperren"


def test_gemischter_tag_lag1_de_lag2_us_nur_us_bleibt_gesperrt():
    """Je Markt, nicht global — bleibt auch nach der Umstellung gültig (Punkt 3
    der ursprünglichen #72-Registry-Notiz, unverändert)."""
    c = leer()
    lauf(c, rep(de=["FRE.DE"], us=["OXY"], lag_de=1, lag_us=2), "2026-09-16")
    assert recs(c, "FRE.DE") != [], "DE bei Rückstand 1 darf jetzt sammeln"
    assert recs(c, "OXY") == [], "US bei Rückstand 2 muss weiterhin sperren"
