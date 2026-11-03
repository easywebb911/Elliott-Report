"""``mark_prevclose_entry_records.py`` — GETRENNTER, sitzungsbewusster Marker
``prevclose_entry_suspect`` neben dem bestehenden ``stale_market_suspect``.

Siehe das Modul-Docstring für den Hintergrund. Kurz: ``mark_stale_market_
records.py``/``rueckstaende_je_lauf()`` bleiben eine HARTE GRENZE (``tests/
test_sammlungs_schutz.py``, Abschnitte 9 und 12b) — dieses Skript rührt sie
nicht an, importiert `finde_stale_records()` UNVERÄNDERT und liefert nur eine
ANDERE Eingabe (sitzungsbewusster statt kalendertag-basierter Rückstand).

Dieser Test-Datei-Ansatz spiegelt bewusst die Muster aus ``test_sammlungs_
schutz.py`` (synthetische Fixtures + ein Replay gegen die volle committete
Historie mit Stichtag-Einfrierung), ändert aber KEINE bestehende Datei und
KEINE bestehende gepinnte Liste.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import mark_prevclose_entry_records as mpc  # noqa: E402
import mark_stale_market_records as msr  # noqa: E402
import market_calendar as cal  # noqa: E402


# ---------------------------------------------------------------------------
# 1) Die Regel ist WIRKLICH dieselbe wie bei health_check/stale_markets —
#    kein eigener Nachbau, nur der eine Aufruf.
# ---------------------------------------------------------------------------
def test_rueckstaende_je_lauf_sitzung_ruft_nur_die_sitzungsbewusste_funktion_auf():
    quelle = Path(mpc.__file__).read_text(encoding="utf-8")
    body = quelle.split("def rueckstaende_je_lauf_sitzung(", 1)[1].split(
        "\ndef ", 1)[0]
    assert "cal.handelstage_rueckstand_sitzung(" in body
    assert "cal.handelstage_rueckstand(" not in body, (
        "das waere der ALTE, kalendertag-basierte Anker — verboten hier")


def test_finde_stale_records_wird_unveraendert_importiert_nicht_kopiert():
    assert mpc.finde_stale_records is msr.finde_stale_records


def test_eigener_marker_name_nicht_der_alte():
    assert mpc.MARKER == "prevclose_entry_suspect"
    assert mpc.MARKER != msr.MARKER


# ---------------------------------------------------------------------------
# 2) rueckstaende_je_lauf_sitzung() auf synthetischen Report-Zuständen.
# ---------------------------------------------------------------------------
def _report(ts, de_bar=None, us_bar=None):
    markets = {}
    if de_bar is not None:
        markets["DE"] = {"diag": {"last_bar_date": de_bar}}
    if us_bar is not None:
        markets["US"] = {"diag": {"last_bar_date": us_bar}}
    return {"run_timestamp_utc": ts, "markets": markets}


def test_sitzungsbewusster_rueckstand_nach_sitzungsende_dienstag():
    # Dienstag 23:00 UTC: beide Sitzungen (US 21:00 UTC, DE 16:30 CET/15:30
    # UTC im Winter) sind laengst zu -> erwarteter Tag ist der Dienstag
    # selbst. DE-Bar vom Montag -> 1 Handelstag zurueck; US-Bar vom
    # Dienstag selbst -> frisch (0). Die Schwelle (ab_lag) filtert erst in
    # finde_stale_records() — hier steht noch der rohe Rueckstand je Markt.
    rep = _report("2026-01-06T23:00:00Z", de_bar="2026-01-05", us_bar="2026-01-06")
    lags = mpc.rueckstaende_je_lauf_sitzung([rep])
    assert lags["2026-01-06T23:00:00Z"] == {"DE": 1, "US": 0}


def test_sitzungsbewusster_rueckstand_ohne_zeitstempel_wird_uebersprungen():
    rep = {"run_timestamp_utc": None, "markets": {}}
    assert mpc.rueckstaende_je_lauf_sitzung([rep]) == {}


def test_sitzungsbewusster_rueckstand_leere_eingabe():
    assert mpc.rueckstaende_je_lauf_sitzung([]) == {}


# ---------------------------------------------------------------------------
# 3) Marker setzen/entfernen — AUSSCHLIESSLICH das eigene Feld, niemals den
#    alten Marker oder sonst etwas am Record.
# ---------------------------------------------------------------------------
def _rec(ticker, market, created_utc, **extra):
    r = {"episode_id": f"{ticker}@{created_utc}", "ticker": ticker,
         "market": market, "created_utc": created_utc,
         "entry_close": 100.0, "score_heuristic": 80.0}
    r.update(extra)
    return r


def test_setze_marker_aendert_nur_das_eigene_feld():
    rec = _rec("TEST.DE", "DE", "2026-01-06T23:00:00Z")
    vorher = copy.deepcopy(rec)
    coll = {"records": [rec]}
    treffer = [{"key": msr.record_key(rec), "ticker": "TEST.DE", "market": "DE",
                "episode_id": rec["episode_id"], "run_utc": "2026-01-06T23:00:00Z",
                "lag_trading_days": 1}]
    n = mpc.setze_marker(coll, treffer, "2026-01-07", {treffer[0]["key"]: "2026-01-05"})
    assert n == 1
    assert mpc.MARKER in rec
    assert msr.MARKER not in rec, "der ALTE Marker darf nie gesetzt werden"
    rec_ohne_marker = {k: v for k, v in rec.items() if k != mpc.MARKER}
    assert rec_ohne_marker == vorher, "sonst darf sich am Record NICHTS aendern"
    assert rec[mpc.MARKER] == {
        "marked_date": "2026-01-07", "run_utc": "2026-01-06T23:00:00Z",
        "last_bar_date": "2026-01-05", "lag_trading_days": 1,
    }


def test_setze_marker_ist_idempotent():
    rec = _rec("TEST.DE", "DE", "2026-01-06T23:00:00Z")
    coll = {"records": [rec]}
    treffer = [{"key": msr.record_key(rec), "ticker": "TEST.DE", "market": "DE",
                "episode_id": rec["episode_id"], "run_utc": "2026-01-06T23:00:00Z",
                "lag_trading_days": 1}]
    last_bars = {treffer[0]["key"]: "2026-01-05"}
    assert mpc.setze_marker(coll, treffer, "2026-01-07", last_bars) == 1
    assert mpc.setze_marker(coll, treffer, "2026-01-07", last_bars) == 0, (
        "zweiter Lauf mit denselben Angaben darf nichts mehr aendern")


def test_entferne_marker_nur_das_eigene_feld():
    rec = _rec("TEST.DE", "DE", "2026-01-06T23:00:00Z")
    rec[mpc.MARKER] = {"marked_date": "2026-01-07"}
    rec[msr.MARKER] = {"marked_date": "2026-01-07"}  # simuliert: trug schon den Altmarker
    coll = {"records": [rec]}
    n = mpc.entferne_marker(coll)
    assert n == 1
    assert mpc.MARKER not in rec
    assert msr.MARKER in rec, "der ALTE Marker darf von diesem Skript nie entfernt werden"


# ---------------------------------------------------------------------------
# 4) Replay gegen die volle committete Historie — EIGENE, gepinnte Liste.
#    Stichtag-Muster wie beim Altmarker (03.10.2026): neue Treffer danach
#    lassen diesen Test NICHT rot werden, sondern werden per warnings.warn
#    gemeldet (derselbe Grund: jeder neue echte Vorfall waechst sonst in main
#    rot, strukturell garantiert durch ab_lag=1).
# ---------------------------------------------------------------------------
# Eingetragen am 03.11.2026, gegen die committete Historie bis einschliesslich
# des Laufs 2026-11-03T03:42:05Z nachgerechnet (nicht geraten) — EXAKT
# dieselben 23 Treffer/10 Tage wie im Design-Bericht vom selben Tag.
ERWARTETE_PREVCLOSE_TREFFER_SEIT_2026_10_20 = [
    ("IT", "US", "2026-10-20T01:16:14Z", 1),
    ("TMO", "US", "2026-10-21T00:56:40Z", 1),
    ("PH", "US", "2026-10-22T00:53:46Z", 1),
    ("APTV", "US", "2026-10-22T00:53:46Z", 1),
    ("KWS.DE", "DE", "2026-10-22T00:53:46Z", 1),
    ("PGR", "US", "2026-10-23T00:56:13Z", 1),
    ("DHL.DE", "DE", "2026-10-23T00:56:13Z", 1),
    ("UTDI.DE", "DE", "2026-10-23T00:56:13Z", 1),
    ("SLB", "US", "2026-10-24T01:03:54Z", 1),
    ("PSM.DE", "DE", "2026-10-24T01:03:54Z", 1),
    ("COK.DE", "DE", "2026-10-24T01:03:54Z", 1),
    ("UTDI.DE", "DE", "2026-10-27T01:37:06Z", 1),
    ("BAYN.DE", "DE", "2026-10-28T01:42:33Z", 1),
    ("SIE.DE", "DE", "2026-10-28T01:42:33Z", 1),
    ("BEI.DE", "DE", "2026-10-29T01:56:48Z", 1),
    ("SGL.DE", "DE", "2026-10-31T01:47:42Z", 1),
    ("BNR.DE", "DE", "2026-10-31T01:47:42Z", 1),
    ("G1A.DE", "DE", "2026-10-31T01:47:42Z", 1),
    ("EVK.DE", "DE", "2026-10-31T01:47:42Z", 1),
    ("JUN3.DE", "DE", "2026-10-31T01:47:42Z", 1),
    ("NDX1.DE", "DE", "2026-11-03T03:42:05Z", 1),
    ("DEQ.DE", "DE", "2026-11-03T03:42:05Z", 1),
    ("AOF.DE", "DE", "2026-11-03T03:42:05Z", 1),
]
AB_DATUM_UTC = "2026-10-20T00:00:00Z"
REPLAY_STICHTAG_UTC = "2026-11-03T04:00:00Z"


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
    assert len(reports) >= 40 and len(coll_st) >= 40, "Historie unvollstaendig"
    return mpc.finde_stale_records(coll_st, mpc.rueckstaende_je_lauf_sitzung(reports))


@braucht_historie
def test_der_replay_findet_die_23_treffer_seit_20_10(replay):
    gefunden = [(t["ticker"], t["market"], t["run_utc"], t["lag_trading_days"])
                for t in replay
                if AB_DATUM_UTC <= t["run_utc"] < REPLAY_STICHTAG_UTC]
    assert gefunden == ERWARTETE_PREVCLOSE_TREFFER_SEIT_2026_10_20


@braucht_historie
def test_replay_treffer_nach_stichtag_nur_gemeldet_nicht_rot(replay):
    gefunden = [(t["ticker"], t["market"], t["run_utc"], t["lag_trading_days"])
                for t in replay if t["run_utc"] >= REPLAY_STICHTAG_UTC]
    if gefunden:
        warnings.warn(
            f"{len(gefunden)} neue(r) prevclose_entry-Treffer nach Stichtag "
            f"{REPLAY_STICHTAG_UTC}, NICHT in ERWARTETE_PREVCLOSE_TREFFER_"
            f"SEIT_2026_10_20 (CI bleibt grün): {gefunden}")


@braucht_historie
def test_der_neue_marker_rechnet_mit_eigenem_lag_nicht_dem_alten(replay):
    """Gegenprobe: derselbe Lauf/Ticker kann beim ALTEN (kalendertag-) und
    NEUEN (sitzungsbewussten) Marker einen ANDEREN Rueckstand tragen — z. B.
    NDX1.DE/DEQ.DE/AOF.DE am 03.11.: alter Anker 2, neuer Anker 1 (Beleg aus
    dem Design-Bericht vom 03.11.2026)."""
    alt_treffer = msr.finde_stale_records(
        msr.committete_sammlungen(ROOT), msr.rueckstaende_je_lauf(
            msr.committete_reports(ROOT)))
    alt_am_lauf = {(t["ticker"], t["market"]): t["lag_trading_days"]
                   for t in alt_treffer if t["run_utc"] == "2026-11-03T03:42:05Z"}
    neu_am_lauf = {(t["ticker"], t["market"]): t["lag_trading_days"]
                   for t in replay if t["run_utc"] == "2026-11-03T03:42:05Z"}
    for key in (("NDX1.DE", "DE"), ("DEQ.DE", "DE"), ("AOF.DE", "DE")):
        assert alt_am_lauf[key] == 2
        assert neu_am_lauf[key] == 1
        assert alt_am_lauf[key] != neu_am_lauf[key]


# ---------------------------------------------------------------------------
# 5) Ende-zu-Ende CLI (--live/--purge) auf synthetischen, injizierten
#    Report-/Sammlungs-Zustaenden — KEIN echtes Git, KEIN echter Repo-Zugriff,
#    KEINE Beruehrung von data/forward_collection.json. Spiegelt den
#    Produktionsablauf 1:1 (main() ruft dieselben Funktionen, nur die beiden
#    Historien-Leser sind hier durch Monkeypatch ersetzt).
# ---------------------------------------------------------------------------
_SYNTH_REPORT_R0 = {
    "run_timestamp_utc": "2026-01-05T23:00:00Z",
    "markets": {"DE": {"diag": {"last_bar_date": "2026-01-05"}},
                "US": {"diag": {"last_bar_date": "2026-01-05"}}},
}
_SYNTH_REPORT_R1 = {
    "run_timestamp_utc": "2026-01-06T23:00:00Z",
    "markets": {"DE": {"diag": {"last_bar_date": "2026-01-05"}},   # 1 zurueck
                "US": {"diag": {"last_bar_date": "2026-01-06"}}},  # frisch
}


def _synth_record():
    return {"episode_id": "TEST.DE@2026-01-06", "ticker": "TEST.DE",
            "market": "DE", "created_utc": "2026-01-06T23:00:00Z",
            "entry_close": 100.0, "score_heuristic": 80.0,
            "target_zone": {"low": 110.0, "high": 120.0}}


def _synth_coll(updated_utc, records):
    return {"schema_version": 1, "updated_utc": updated_utc,
            "records": [copy.deepcopy(r) for r in records]}


def _schreibe_sammlung(base: Path, coll: dict) -> None:
    for rel in mpc.REL_PATHS:
        pfad = base / rel
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(coll, ensure_ascii=False, indent=2,
                                    sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def synth_repo(tmp_path, monkeypatch):
    """Legt die LIVE-Dateien (Dateisystem) an UND monkeypatcht die beiden
    Git-Historien-Leser im Modul `mark_prevclose_entry_records`, damit
    `main()` ohne echtes Git funktioniert."""
    coll_nachher = _synth_coll(_SYNTH_REPORT_R1["run_timestamp_utc"],
                               [_synth_record()])
    _schreibe_sammlung(tmp_path, coll_nachher)

    coll_vorher = _synth_coll(_SYNTH_REPORT_R0["run_timestamp_utc"], [])
    monkeypatch.setattr(mpc, "committete_reports",
                        lambda git_root: [_SYNTH_REPORT_R0, _SYNTH_REPORT_R1])
    monkeypatch.setattr(mpc, "committete_sammlungen",
                        lambda git_root: [coll_vorher, coll_nachher])
    return tmp_path


def _lies_sammlung(base: Path) -> dict:
    return json.loads((base / "data/forward_collection.json").read_text(
        encoding="utf-8"))


def test_dry_run_schreibt_nichts(synth_repo):
    vor = (synth_repo / "data/forward_collection.json").read_text(encoding="utf-8")
    rc = mpc.main(["--date", "2026-01-07", "--path", str(synth_repo),
                  "--git-root", str(synth_repo)])
    assert rc == 0
    nach = (synth_repo / "data/forward_collection.json").read_text(encoding="utf-8")
    assert vor == nach, "Dry-Run darf die Datei nicht anfassen"


def test_live_markiert_nur_das_feld_sonst_byte_identisch(synth_repo):
    vorher = _lies_sammlung(synth_repo)
    vorher_rec = copy.deepcopy(vorher["records"][0])

    rc = mpc.main(["--live", "--date", "2026-01-07", "--path", str(synth_repo),
                  "--git-root", str(synth_repo)])
    assert rc == 0

    nachher = _lies_sammlung(synth_repo)
    rec = nachher["records"][0]
    assert mpc.MARKER in rec
    assert rec[mpc.MARKER] == {
        "marked_date": "2026-01-07", "run_utc": "2026-01-06T23:00:00Z",
        "last_bar_date": "2026-01-05", "lag_trading_days": 1,
    }
    # US-Record gibt es hier nicht (nur ein synthetischer Record) — die
    # Markt-Trennung ist bereits in Abschnitt 2 oben (DE markiert, US nicht
    # einmal im Lag-Dict) belegt.
    rec_ohne_marker = {k: v for k, v in rec.items() if k != mpc.MARKER}
    assert rec_ohne_marker == vorher_rec, (
        "ausser dem neuen Markerfeld darf sich am Record NICHTS aendern")
    assert msr.MARKER not in rec, "der ALTE Marker darf hier nie entstehen"
    # Metadaten der Sammlung (schema_version, updated_utc) unveraendert.
    for feld in ("schema_version", "updated_utc"):
        assert nachher[feld] == vorher[feld]


def test_zweiter_live_lauf_ist_wiederholbar_und_aendert_nichts(synth_repo):
    mpc.main(["--live", "--date", "2026-01-07", "--path", str(synth_repo),
             "--git-root", str(synth_repo)])
    nach_erstem = (synth_repo / "data/forward_collection.json").read_text(
        encoding="utf-8")

    rc = mpc.main(["--live", "--date", "2026-01-07", "--path", str(synth_repo),
                  "--git-root", str(synth_repo)])
    assert rc == 0
    nach_zweitem = (synth_repo / "data/forward_collection.json").read_text(
        encoding="utf-8")
    assert nach_erstem == nach_zweitem, "zweiter --live-Lauf muss ein No-op sein"


def test_purge_stellt_den_ausgangszustand_wieder_her(synth_repo):
    vorher = (synth_repo / "data/forward_collection.json").read_text(encoding="utf-8")

    mpc.main(["--live", "--date", "2026-01-07", "--path", str(synth_repo),
             "--git-root", str(synth_repo)])
    waehrend = (synth_repo / "data/forward_collection.json").read_text(encoding="utf-8")
    assert waehrend != vorher, "Vorbedingung: der Marker wurde wirklich gesetzt"

    rc = mpc.main(["--purge", "--live", "--path", str(synth_repo),
                  "--git-root", str(synth_repo)])
    assert rc == 0
    nachher = _lies_sammlung(synth_repo)
    assert mpc.MARKER not in nachher["records"][0]
    vorher_geparst = json.loads(vorher)
    assert nachher == vorher_geparst, "Rueckweg muss byte-identisch zum Ausgangszustand sein"


def test_purge_dry_run_schreibt_nichts(synth_repo):
    mpc.main(["--live", "--date", "2026-01-07", "--path", str(synth_repo),
             "--git-root", str(synth_repo)])
    vor_purge = (synth_repo / "data/forward_collection.json").read_text(encoding="utf-8")

    rc = mpc.main(["--purge", "--path", str(synth_repo),
                  "--git-root", str(synth_repo)])
    assert rc == 0
    nach_purge = (synth_repo / "data/forward_collection.json").read_text(encoding="utf-8")
    assert vor_purge == nach_purge


def test_ohne_date_ohne_purge_ist_ein_fehler(synth_repo):
    rc = mpc.main(["--live", "--path", str(synth_repo), "--git-root", str(synth_repo)])
    assert rc == 2
    # Datei wurde nicht angefasst.
    coll = _lies_sammlung(synth_repo)
    assert mpc.MARKER not in coll["records"][0]
