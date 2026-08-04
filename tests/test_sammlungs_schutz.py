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
    return {"markets": {
        "DE": {"candidates": [kand(t) for t in de],
               "diag": {"bar_lag_trading_days": lag_de}},
        "US": {"candidates": [kand(t) for t in us],
               "diag": {"bar_lag_trading_days": lag_us}}}}


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
    (0, False), (1, True), (2, True), (7, True),
    (None, False), ("2", False), (True, False),   # unbrauchbar -> frisch
])
def test_stale_markets_schwelle_und_fail_soft(lag, gegated):
    """Schwelle ist >= 1 Handelstag. Fehlt oder taugt das Feld nicht, gilt der
    Markt als FRISCH — ein Gate, das aus Unwissen sperrt, hielte die Sammlung
    stillschweigend an, und das wäre schlimmer als der Schaden."""
    r = {"markets": {"DE": {"diag": {"bar_lag_trading_days": lag}}}}
    assert ("DE" in fc.stale_markets(r)) is gegated


def test_stale_markets_ohne_diag_und_ohne_feld():
    assert fc.stale_markets({"markets": {"DE": {}}}) == {}
    assert fc.stale_markets({"markets": {"DE": "kaputt"}}) == {}
    assert fc.stale_markets({}) == {}


def test_stale_markets_liest_dieselbe_zahl_wie_der_waechter():
    """Keine zweite Definition: die Quelle ist `diag.bar_lag_trading_days`,
    das aus `market_calendar.handelstage_rueckstand` stammt."""
    quelle = (ROOT / "scripts/forward_collection.py").read_text(encoding="utf-8")
    assert 'lag = (market.get("diag") or {}).get("bar_lag_trading_days")' in quelle
    # und die Zahl selbst kommt wirklich aus dem Kalender:
    assert cal.handelstage_rueckstand("2026-07-31", "2026-08-04") == 2


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
    lauf(c, rep(de=["X"], us=["A"], lag_de=1), "2026-08-04")
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


# ---------------------------------------------------------------------------
# 5) Der echte 04.08.-Fall: KKR wäre nicht entstanden
# ---------------------------------------------------------------------------
def test_der_echte_KKR_fall_waere_mit_gate_NICHT_entstanden():
    c = leer()
    lauf(c, rep(us=["AJG"]), "2026-08-03")
    lauf(c, rep(us=["AJG", "KKR"], lag_us=2), "2026-08-04",
         "2026-08-04T04:46:23Z")
    assert [r["ticker"] for r in c["records"]] == ["AJG"]
    assert recs(c, "KKR") == []


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
# ---------------------------------------------------------------------------
ERWARTETE_MARKIERUNGEN = [
    ("ADS.DE", "DE", "2026-07-30T22:45:00Z", 1),
    ("MTX.DE", "DE", "2026-07-31T22:40:44Z", 1),
    ("G1A.DE", "DE", "2026-07-31T22:40:44Z", 1),
    ("KKR", "US", "2026-08-04T04:46:23Z", 2),
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
def test_der_replay_findet_genau_die_vier_faelle(replay):
    gefunden = [(t["ticker"], t["market"], t["run_utc"], t["lag_trading_days"])
                for t in replay]
    assert gefunden == ERWARTETE_MARKIERUNGEN


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
