"""Report-Only-Modus (Mittagslauf, additiv, 09.09.2026).

ABSOLUTE, NICHT VERHANDELBARE GRENZE dieses Auftrags: `REPORT_ONLY=1` darf
`data/forward_collection.json`/`docs/data/forward_collection.json` unter
KEINEN Umständen lesen, verändern oder schreiben. Jeder Test hier prüft das
per LAUFZEIT-Beweis (`pipe.main()` wirklich ausgeführt, Datei-Bytes vorher/
nachher verglichen), nicht nur per Quelltext-Nähe — dieselbe Lehre wie
`test_one_count_source.py::test_pipeline_ordnet_die_zahlen_zur_laufzeit_richtig_zu`
(Guardian-Mutationsprobe 29.07.2026: ein Quelltext-Test allein blieb grün,
obwohl das Verhalten kaputt war).

Sandbox-Muster 1:1 aus `test_one_count_source.py` übernommen (REPO_ROOT auf
`pipe`/`fc`/`hc` umgebogen, ELLIOTT_OFFLINE=1, kleines MARKETS-Universum,
`load_watchlist` gestubbt) — kein neues Muster erfunden.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import elliott_pipeline as pipe  # noqa: E402
import forward_collection as fc  # noqa: E402
import health_check as hc  # noqa: E402

SRC = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")


def _sandbox(tmp_path, monkeypatch, sammlung_records=None):
    """Isoliertes Repo-Abbild — exakt das Muster aus test_one_count_source.py."""
    (tmp_path / "data").mkdir()
    (tmp_path / "docs/data").mkdir(parents=True)
    coll = {"schema_version": 1, "records": sammlung_records or []}
    inhalt = json.dumps(coll, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (tmp_path / "data/forward_collection.json").write_text(inhalt, encoding="utf-8")
    (tmp_path / "docs/data/forward_collection.json").write_text(inhalt, encoding="utf-8")

    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
    monkeypatch.setattr(pipe, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipe.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE"]},
    })
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    return inhalt


def _lies(pfad: Path) -> str:
    return pfad.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) LAUFZEIT-Beweis: die Sammlung bleibt byte-identisch
# ---------------------------------------------------------------------------
def test_report_only_laesst_forward_collection_byte_identisch(tmp_path, monkeypatch):
    vorher = _sandbox(tmp_path, monkeypatch)
    monkeypatch.setenv("REPORT_ONLY", "1")

    assert pipe.main() == 0

    for rel in ("data/forward_collection.json", "docs/data/forward_collection.json"):
        nachher = _lies(tmp_path / rel)
        assert nachher == vorher, f"{rel} wurde im Report-Only-Modus veraendert!"

    # report.json MUSS trotzdem geschrieben worden sein — sonst waere der
    # Modus nutzlos, nicht nur "sicher".
    rep = json.loads(_lies(tmp_path / "data/report.json"))
    assert rep["markets"]["US"]["candidates_found"] >= 0
    assert json.loads(_lies(tmp_path / "docs/data/report.json"))


def test_kontrollgruppe_ohne_report_only_aendert_die_sammlung_wirklich(tmp_path, monkeypatch):
    """Kontrollgruppe (Guardian-Mutationsprobe-Muster): DERSELBE Sandbox-Aufbau
    OHNE REPORT_ONLY muss die Sammlung tatsaechlich veraendern — sonst waere
    der Test oben trivial gruen, weil in dieser Sandbox ohnehin nie etwas
    geschrieben wird."""
    vorher = _sandbox(tmp_path, monkeypatch)
    monkeypatch.delenv("REPORT_ONLY", raising=False)

    assert pipe.main() == 0

    nachher = _lies(tmp_path / "data/forward_collection.json")
    assert nachher != vorher, (
        "Kontrollgruppe: die Sammlung haette sich OHNE REPORT_ONLY aendern "
        "muessen (last_run_date/neue Episoden) — sonst beweist der "
        "Report-Only-Test oben gar nichts.")
    coll = json.loads(nachher)
    assert coll.get("last_run_date"), "last_run_date fehlt — update_forward_collection lief nicht"


# ---------------------------------------------------------------------------
# (a2) Modus-Marker (11.09.2026, Diagnose-Folgeauftrag): additiv, NUR im
# Report-Only-Modus gesetzt — LAUFZEIT-Beweis, dass er wirklich im
# persistierten report.json landet (nicht nur im Speicher gesetzt und dann
# vom NACHTRAG-Schreibvorgang wieder verloren).
# ---------------------------------------------------------------------------
def test_report_only_setzt_mode_marker_im_persistierten_report(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.setenv("REPORT_ONLY", "1")

    assert pipe.main() == 0

    for rel in ("data/report.json", "docs/data/report.json"):
        rep = json.loads(_lies(tmp_path / rel))
        assert rep.get("mode") == "report_only", (
            f"{rel}: 'mode: report_only' fehlt im Report-Only-Modus — "
            "das Frontend kann Fall (a) sonst nicht erkennen")


def test_standardmodus_setzt_keinen_mode_marker(tmp_path, monkeypatch):
    """Regression: dieselbe 'Abwesenheit = sauber'-Konvention wie bei
    in_session_creation — der Normalfall bekommt KEIN 'mode: full' o. Ä."""
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.delenv("REPORT_ONLY", raising=False)

    assert pipe.main() == 0

    rep = json.loads(_lies(tmp_path / "data/report.json"))
    assert "mode" not in rep, (
        "Standard-Modus schreibt ein 'mode'-Feld — das war nicht vorgesehen "
        "(Abwesenheit = Normalfall, wie bei in_session_creation)")


# ---------------------------------------------------------------------------
# (b) Health-Check Stufe 3 / Agent-Kommentar werden NICHT aufgerufen
# ---------------------------------------------------------------------------
def test_report_only_ruft_hc_run_nicht_auf(tmp_path, monkeypatch):
    """Laufzeit-Beweis fuer den beim Bauen gefundenen Herzschlag/Meilenstein-
    Seiteneffekt (s. Kommentar in elliott_pipeline.py): hc.run() darf im
    Report-Only-Modus gar nicht erst aufgerufen werden."""
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.setenv("REPORT_ONLY", "1")

    aufgerufen = []
    monkeypatch.setattr(hc, "run", lambda *a, **kw: aufgerufen.append(1) or {})

    assert pipe.main() == 0
    assert aufgerufen == [], "hc.run() wurde im Report-Only-Modus aufgerufen!"

    rep = json.loads(_lies(tmp_path / "data/report.json"))
    assert "health" not in rep, (
        "report['health'] gesetzt, obwohl hc.run() nie lief — "
        "wer setzt es dann?")


def test_report_only_ruft_agent_kommentar_nicht_auf(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.setenv("REPORT_ONLY", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")  # waere sonst eh ein No-op

    import agent_comment as ac
    aufgerufen = []
    monkeypatch.setattr(ac, "annotate_agent_comments",
                        lambda *a, **kw: aufgerufen.append(1))

    assert pipe.main() == 0
    assert aufgerufen == [], "agent_comment.annotate_agent_comments() wurde aufgerufen!"


def test_report_only_ruft_load_collection_nicht_auf(tmp_path, monkeypatch):
    """Laufzeit-Beweis fuer den Guardian-Fund vom 09.09.2026: fc.load_collection()
    lief unconditional VOR dem Report-Only-Ruecksprung (N×-Zaehler-Block) und
    widersprach damit der zugesicherten Garantie, die Sammlung werde in diesem
    Modus 'nicht einmal geladen'. Ein reiner Byte-Identitaets-Test (s. oben)
    kann einen reinen Lesezugriff nicht fangen — deshalb hier ein eigener Spion,
    genau wie bei hc.run()/agent_comment."""
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.setenv("REPORT_ONLY", "1")

    aufgerufen = []
    echt_laden = fc.load_collection

    def spion(*a, **kw):
        aufgerufen.append(1)
        return echt_laden(*a, **kw)
    monkeypatch.setattr(fc, "load_collection", spion)

    assert pipe.main() == 0
    assert aufgerufen == [], (
        "fc.load_collection() wurde im Report-Only-Modus aufgerufen — "
        "die Sammlung wurde entgegen der Zusicherung gelesen!")


def test_standardmodus_ruft_load_collection_weiterhin_auf(tmp_path, monkeypatch):
    """Regression: OHNE REPORT_ONLY bleibt der N×-Zaehler (und damit
    fc.load_collection()) Teil des Ablaufs."""
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.delenv("REPORT_ONLY", raising=False)

    aufgerufen = []
    echt_laden = fc.load_collection

    def spion(*a, **kw):
        aufgerufen.append(1)
        return echt_laden(*a, **kw)
    monkeypatch.setattr(fc, "load_collection", spion)

    assert pipe.main() == 0
    assert aufgerufen, "fc.load_collection() lief im Standard-Modus nicht (mehr)"


def test_standardmodus_ruft_hc_run_weiterhin_auf(tmp_path, monkeypatch):
    """Regression: OHNE REPORT_ONLY bleibt hc.run() Teil des Ablaufs — der
    neue Modus darf das bestehende Verhalten nicht mitentfernen."""
    _sandbox(tmp_path, monkeypatch)
    monkeypatch.delenv("REPORT_ONLY", raising=False)

    aufgerufen = []
    echt_run = hc.run

    def spion(*a, **kw):
        aufgerufen.append(1)
        return echt_run(*a, **kw)
    monkeypatch.setattr(hc, "run", spion)

    assert pipe.main() == 0
    assert aufgerufen == [1], "hc.run() lief im Standard-Modus nicht (mehr)"


# ---------------------------------------------------------------------------
# (c) Struktureller Anker — zusaetzliches Netz, kein Ersatz fuer (a)/(b)
# ---------------------------------------------------------------------------
def test_report_only_rueckkehr_steht_textuell_vor_jedem_sammlungs_aufruf():
    """Reine Lage-Pruefung im Quelltext — ergaenzt (a)/(b), ersetzt sie nicht
    (Lehre aus #29.07.: Quelltext-Naehe allein reicht nicht)."""
    fn_start = SRC.index("\ndef main() -> int:")
    fn_ende = SRC.index("\nif __name__ == \"__main__\":", fn_start)
    koerper = SRC[fn_start:fn_ende]

    # Verankert auf den EIGENTLICHEN Ausstiegs-Block, nicht auf die erste
    # beliebige `if REPORT_ONLY:`-Stelle — seit dem Guardian-Fund vom
    # 09.09.2026 (fc.load_collection() lief vor dem Rücksprung) gibt es eine
    # ZWEITE, frühere `if REPORT_ONLY:`-Weiche (N×-Zähler-Guard, s. eigener
    # Laufzeit-Test unten). Diese Positions-Prüfung gilt bewusst nur für die
    # Marken, die UNBEDINGT (ohne eigene Guard-Klausel) hinter dem
    # Rücksprung liegen müssen — fc.load_collection/fc.annotate_appearance_counts
    # haben eine eigene, separat getestete if/else-Weiche und gehören
    # deshalb NICHT in diese rein positionsbasierte Liste.
    ausstieg_marker = koerper.index("REPORT-ONLY-AUSSTIEG")
    gate_pos = koerper.index("if REPORT_ONLY:", ausstieg_marker)
    ruecksprung_pos = koerper.index("return 0", gate_pos)

    for marke in ("fc.update_forward_collection(", "fc.write_collection(",
                 "health = hc.run("):
        pos = koerper.index(marke)
        assert ruecksprung_pos < pos, (
            f"'{marke}' steht VOR dem Report-Only-Rücksprung — "
            "die Sicherheitsgrenze waere nicht mehr garantiert")


def test_report_only_env_var_exakter_vergleich_wie_elliott_offline():
    """Dieselbe Wahrheitswert-Konvention wie ELLIOTT_OFFLINE (== "1"),
    kein zweiter Parsing-Stil in diesem Skript."""
    assert 'REPORT_ONLY = os.environ.get("REPORT_ONLY") == "1"' in SRC


def test_report_only_ist_im_neutrale_umgebung_katalog():
    """Sonst haengt jeder Test, der REPORT_ONLY zufaellig in der Laeufer-
    Umgebung vorfindet, vom Laeufer ab (dieselbe Falle wie GITHUB_REF,
    06.08.2026) — tests/conftest.py muss die Variable kennen."""
    conftest = (ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    assert '"REPORT_ONLY"' in conftest
