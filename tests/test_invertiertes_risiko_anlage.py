"""Marker „invertiertes Risiko bei Anlage" — Kriterium, Backfill, Grenzen.

ANLASS (14.10.2026, Diagnose-Folgeauftrag, Easy-Entscheid Variante A): 11 von
202 Records hatten bei Anlage `entry_close <= invalidation_price`. Dieses
Modul (`scripts/invertiertes_risiko_anlage.py`) markiert das additiv — EIN
Marker, kein Ausschluss, nichts heilen (dasselbe Prinzip wie
`in_session_creation`, s. `tests/test_in_session_creation.py`).

OPERATOR: `<=`, identisch zur bestehenden `forward_collection._r_kennzahlen`-
Bedingung (`risiko_raw > 0` im Positiv-Zweig, sonst der Marker — also `<= 0`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import invertiertes_risiko_anlage as ira  # noqa: E402
import mark_invertiertes_risiko_anlage as mark  # noqa: E402

COLL = ROOT / "data" / "forward_collection.json"


def _coll():
    return json.loads(COLL.read_text(encoding="utf-8"))


# ===========================================================================
# 1 · DAS KRITERIUM — synthetische Fixtures (unter/gleich/über der Marke)
# ===========================================================================
@pytest.mark.parametrize("entry_close,invalidation_price,soll", [
    (90.0, 100.0, True),     # unter der Marke — invertiertes Risiko
    (100.0, 100.0, True),    # GENAU auf der Marke — Operator-Entscheidung: <=
    (100.0001, 100.0, False),  # hauchdünn über der Marke — kein Treffer
    (110.0, 100.0, False),   # klar über der Marke — normales Risiko
])
def test_kriterium_unter_gleich_ueber_der_marke(entry_close, invalidation_price, soll):
    assert ira.ist_invertiertes_risiko_bei_anlage(entry_close, invalidation_price) is soll


@pytest.mark.parametrize("entry_close,invalidation_price", [
    (None, 100.0), (100.0, None), (float("nan"), 100.0), (100.0, float("inf")),
])
def test_kriterium_nicht_berechenbar_liefert_none(entry_close, invalidation_price):
    assert ira.ist_invertiertes_risiko_bei_anlage(entry_close, invalidation_price) is None


def test_mutationsprobe_operator_vertauscht():
    """Mutationsprobe (Teil 0b der Diagnose): `<=` durch `<` ersetzt ändert auf
    dem AKTUELLEN Bestand (0 Fälle exakt auf der Marke) nichts — aber am
    synthetischen Gleichheits-Fixture oben unterscheiden sich echt und
    kaputt, und genau DAS hält dieser Test fest."""
    def kaputt(entry_close, invalidation_price):
        return entry_close < invalidation_price

    echt = ira.ist_invertiertes_risiko_bei_anlage(100.0, 100.0)
    assert echt is True
    assert kaputt(100.0, 100.0) is False
    assert echt != kaputt(100.0, 100.0)


# ===========================================================================
# 2 · MARKIEREN / ENTFERNEN — Werte-Tests auf Funktionsebene
# ===========================================================================
def test_betroffene_records_auf_mini_liste():
    records = [
        {"ticker": "A", "created_utc": "T1", "entry_close": 90.0, "invalidation_price": 100.0},
        {"ticker": "B", "created_utc": "T2", "entry_close": 110.0, "invalidation_price": 100.0},
        {"ticker": "C", "created_utc": "T3", "entry_close": None, "invalidation_price": 100.0},
    ]
    treffer, unklar = ira.betroffene_records(records)
    assert [r["ticker"] for r in treffer] == ["A"]
    assert [r["ticker"] for r in unklar] == ["C"]


def test_markiere_haengt_nicht_getroffenen_records_kein_feld_an():
    records = [
        {"ticker": "A", "created_utc": "T1", "entry_close": 90.0, "invalidation_price": 100.0},
        {"ticker": "B", "created_utc": "T2", "entry_close": 110.0, "invalidation_price": 100.0},
    ]
    gesetzt, unklar = ira.markiere(records, "2026-10-14T00:00:00Z")
    assert (gesetzt, unklar) == (1, [])
    assert records[0][ira.MARKER] is True
    assert records[0][ira.MARKER_UTC] == "2026-10-14T00:00:00Z"
    assert ira.MARKER not in records[1] and ira.MARKER_UTC not in records[1]


def test_markiere_ist_idempotent_und_datiert_nicht_um():
    records = [
        {"ticker": "A", "created_utc": "T1", "entry_close": 90.0, "invalidation_price": 100.0},
    ]
    ira.markiere(records, "2026-10-14T00:00:00Z")
    gesetzt, unklar = ira.markiere(records, "2099-01-01T00:00:00Z")
    assert (gesetzt, unklar) == (0, [])
    assert records[0][ira.MARKER_UTC] == "2026-10-14T00:00:00Z"


def test_entferne_marker_restlos():
    records = [
        {"ticker": "A", "created_utc": "T1", "entry_close": 90.0, "invalidation_price": 100.0},
    ]
    ira.markiere(records, "2026-10-14T00:00:00Z")
    entfernt = ira.entferne_marker(records)
    assert entfernt == 1
    assert ira.MARKER not in records[0] and ira.MARKER_UTC not in records[0]


def test_false_wird_nie_geschrieben():
    records = [
        {"ticker": "A", "created_utc": "T1", "entry_close": 110.0, "invalidation_price": 100.0},
    ]
    ira.markiere(records, "2026-10-14T00:00:00Z")
    assert ira.MARKER not in records[0]


# ===========================================================================
# 3 · DER BESTAND — die 11 namentlich (abgeschlossener historischer Fakt,
#     Beleg: Dry-Run-Log von mark_invertiertes_risiko_anlage.py vor dem
#     --live-Lauf, identisch zur Diagnose-Liste vom 14.10.2026)
# ===========================================================================
BACKFILL_11 = [
    ("ADS.DE", "2026-07-24T14:36:19Z"), ("ADS.DE", "2026-07-25T13:35:26Z"),
    ("HUM", "2026-07-29T18:14:26Z"), ("KCO.DE", "2026-08-12T16:47:59Z"),
    ("LEG.DE", "2026-08-21T21:57:38Z"), ("VNA.DE", "2026-09-08T18:54:35Z"),
    ("BAC", "2026-09-20T21:35:22Z"), ("YUM", "2026-09-22T20:56:14Z"),
    ("VNA.DE", "2026-09-26T00:52:46Z"), ("VNA.DE", "2026-10-01T01:34:32Z"),
    ("BAC", "2026-10-07T01:48:18Z"),
]
BACKFILL_MARKED_UTC = "2026-10-14T00:00:00Z"


def test_die_ausgelieferte_sammlung_traegt_genau_diese_11_marker():
    markiert = [(r["ticker"], r["created_utc"]) for r in _coll()["records"]
                if r.get(ira.MARKER) is True]
    assert sorted(markiert) == sorted(BACKFILL_11)


def test_alle_gesetzten_marker_tragen_denselben_backfill_stempel():
    alle = [r for r in _coll()["records"] if r.get(ira.MARKER)]
    assert all(r.get(ira.MARKER_UTC) == BACKFILL_MARKED_UTC for r in alle)


def test_alle_gesetzten_marker_stimmen_mit_dem_kriterium_ueberein():
    """Dieselbe Vollbestand-Probe wie bei `in_session_creation` (PR #94-Nit):
    MENGE gegen MENGE, kein gepinntes `== 11` — wächst der Bestand, wächst die
    Erwartung automatisch mit."""
    records = _coll()["records"]
    treffer, unklar = ira.betroffene_records(records)
    assert unklar == [], "kein Record darf unberechenbar sein"
    assert {ira.record_key(r) for r in records if r.get(ira.MARKER) is True} == \
           {ira.record_key(r) for r in treffer}


def test_marker_stimmt_mit_r_nicht_ermittelbar_grund_ueberein():
    """0b/Modul-Doku: der neue Marker ist UNABHÄNGIG berechnet, muss aber auf
    dem aktuellen Bestand exakt mit der seit 06.09.2026 bestehenden
    `r_nicht_ermittelbar_grund == "invertiertes_risiko"`-Markierung
    übereinstimmen — ein künftiges Auseinanderlaufen wäre hier sichtbar."""
    for r in _coll()["records"]:
        hat_marker = bool(r.get(ira.MARKER))
        hat_grund = r.get("r_nicht_ermittelbar_grund") == "invertiertes_risiko"
        assert hat_marker == hat_grund, r.get("ticker")


# ===========================================================================
# 4 · GRENZEN — additiv, zählungsneutral, wie in_session_creation
# ===========================================================================
def test_marker_steht_nicht_in_frozen_fields():
    import evaluate

    assert ira.MARKER not in evaluate.FROZEN_FIELDS
    assert ira.MARKER_UTC not in evaluate.FROZEN_FIELDS


def test_population_und_zaehlwerk_sind_unbeeindruckt():
    """Mit und ohne Marker dieselbe Population, dieselben Zähler — EXZELLENZ-
    Anforderung 'Population/Zählungen vor und nach identisch'."""
    import forward_collection as fc
    import evaluate

    coll_mit = _coll()
    coll_ohne = _coll()
    ira.entferne_marker(coll_ohne["records"])
    assert fc.eval_counts(coll_mit) == fc.eval_counts(coll_ohne)
    pop_mit, diag_mit = evaluate.build_population(coll_mit)
    pop_ohne, diag_ohne = evaluate.build_population(coll_ohne)
    assert len(pop_mit) == len(pop_ohne)
    assert diag_mit == diag_ohne
    assert [r.get("is_excluded") for r in coll_mit["records"]] == \
           [r.get("is_excluded") for r in coll_ohne["records"]]


def test_evaluate_py_sha256_unveraendert():
    """HARTE GRENZE laut Auftrag: `scripts/evaluate.py` (SHA256-Pin) bleibt
    unangetastet — derselbe Pin (Literal) wie
    `tests/test_sammlungs_schutz.py::test_evaluate_v1_ist_byte_identisch`,
    hier NICHT dupliziert erfunden, sondern derselbe bestehende Test wird
    einfach mitlaufen gelassen (s. `test_volle_suite_bleibt_gruen` unten) —
    dieser Test prüft nur zusätzlich, dass GENAU DIESE Datei von diesem
    Auftrag aus nicht angefasst wurde (kein Diff gegen HEAD vor diesem PR)."""
    import hashlib

    ist = hashlib.sha256((ROOT / "scripts/evaluate.py").read_bytes()).hexdigest()
    assert ist == ("bc697df91235732c6c386abe38c79a98248488b9f30a239d9c26c3cbb"
                   "3b513fc"), "evaluate.py wurde verändert — v1 ist eingefroren"


def test_marker_aendert_kein_bestehendes_feld():
    """Markieren + Entmarkieren -> wieder GENAU der Ausgangszustand (Rückweg)."""
    records = _coll()["records"]
    ira.entferne_marker(records)
    basis = json.dumps(records, sort_keys=True)
    ira.markiere(records, "2026-10-14T00:00:00Z")
    ira.entferne_marker(records)
    assert json.dumps(records, sort_keys=True) == basis


def test_bestehende_marker_sind_unberuehrt():
    """`in_session_creation`/`episode_split_suspect`/`stale_market_suspect`
    unverändert durch diesen Backfill."""
    recs = _coll()["records"]
    assert sum(1 for r in recs if r.get("episode_split_suspect")) == 10
    assert sum(1 for r in recs if r.get("stale_market_suspect")) == 4


def test_konsumenten_vertragen_das_neue_feld():
    import forward_collection as fc
    import health_check as hc

    coll = _coll()
    assert hc.check_finite(coll, "collection") == []
    sig = hc.collection_signature(coll)
    coll_ohne = _coll()
    ira.entferne_marker(coll_ohne["records"])
    assert sig == hc.collection_signature(coll_ohne)
    assert fc.stale_markets({"markets": {}}) == {}


def test_der_waechter_der_filter_sensitivity_sammlung_kennt_den_marker_nicht():
    """0d der Diagnose: `filter_sensitivity_sammlung.MARKERS` ist hart
    codiert — der neue Marker fällt NICHT automatisch unter die
    Sensitivitätsregel 08.08.2026, solange er dort nicht eingetragen wird.
    Dieser Test hält den IST-Zustand fest (bewusst nicht geändert, s.
    Registry-Eintrag 14.10.2026) — kein Vorwurf, nur Beleg."""
    import filter_sensitivity_sammlung as fss

    assert ira.MARKER not in fss.MARKERS


def test_tageslauf_markiert_keine_neuen_records():
    """Mini-Stopp statt Bauen (s. Moduldoc): `elliott_pipeline.py` ruft dieses
    Modul nirgends auf — anders als `in_session.markiere_neue_records`."""
    q = (ROOT / "scripts" / "elliott_pipeline.py").read_text(encoding="utf-8")
    assert "invertiertes_risiko_anlage" not in q


# ===========================================================================
# 5 · BACKFILL-SKRIPT (CLI) — Dry-Run/Live/Purge auf einer Kopie
# ===========================================================================
def _schreibe_mini_sammlung(tmp_path: Path) -> Path:
    coll = {"schema_version": 1, "records": [
        {"ticker": "A", "market": "US", "created_utc": "T1", "first_seen_date": "2026-01-01",
         "entry_close": 90.0, "invalidation_price": 100.0},
        {"ticker": "B", "market": "US", "created_utc": "T2", "first_seen_date": "2026-01-01",
         "entry_close": 110.0, "invalidation_price": 100.0},
    ]}
    (tmp_path / "data").mkdir()
    pfad = tmp_path / "data" / "forward_collection.json"
    pfad.write_text(json.dumps(coll), encoding="utf-8")
    return pfad


def test_cli_dry_run_schreibt_nichts(tmp_path):
    pfad = _schreibe_mini_sammlung(tmp_path)
    vorher = pfad.read_text(encoding="utf-8")
    rc = mark.main(["--root", str(tmp_path), "--marked-utc", "2026-10-14T00:00:00Z"])
    assert rc == 0
    assert pfad.read_text(encoding="utf-8") == vorher


def test_cli_live_markiert_genau_den_einen_treffer(tmp_path):
    pfad = _schreibe_mini_sammlung(tmp_path)
    rc = mark.main(["--root", str(tmp_path), "--live",
                    "--marked-utc", "2026-10-14T00:00:00Z"])
    assert rc == 0
    coll = json.loads(pfad.read_text(encoding="utf-8"))
    a, b = coll["records"]
    assert a[ira.MARKER] is True and a[ira.MARKER_UTC] == "2026-10-14T00:00:00Z"
    assert ira.MARKER not in b


def test_cli_ohne_marked_utc_scheitert(tmp_path):
    _schreibe_mini_sammlung(tmp_path)
    rc = mark.main(["--root", str(tmp_path)])
    assert rc == 2


def test_cli_purge_stellt_byte_identischen_vorzustand_wieder_her(tmp_path):
    pfad = _schreibe_mini_sammlung(tmp_path)
    vorher = pfad.read_text(encoding="utf-8")
    mark.main(["--root", str(tmp_path), "--live", "--marked-utc", "2026-10-14T00:00:00Z"])
    assert pfad.read_text(encoding="utf-8") != vorher
    rc = mark.main(["--root", str(tmp_path), "--purge", "--live"])
    assert rc == 0
    coll = json.loads(pfad.read_text(encoding="utf-8"))
    for r in coll["records"]:
        assert ira.MARKER not in r and ira.MARKER_UTC not in r
    # inhaltlich (nicht byte-identisch wegen json.dump-Formatierung) wieder
    # der Ausgangszustand:
    assert json.loads(vorher)["records"] == coll["records"]


def test_cli_als_subprozess_laeuft_fehlerfrei(tmp_path):
    """Smoke-Test über den echten Entry-Point, nicht nur `main()` im Prozess."""
    _schreibe_mini_sammlung(tmp_path)
    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mark_invertiertes_risiko_anlage.py"),
         "--root", str(tmp_path), "--marked-utc", "2026-10-14T00:00:00Z"],
        capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert "Invertiertes-Risiko-Records: 1 von 2" in res.stderr
