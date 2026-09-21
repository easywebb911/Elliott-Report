"""Proaktiver Fehler-Wächter (20.09.2026) — Wert-Tests je Fehlerklasse +
Mutationsprobe am Klassifizierungs-Mechanismus (rote Linie).

Reine Werttests gegen synthetische Fälle — bewusst KEIN Scan des echten
Repo-Codes in diesen Tests (der würde bei jeder Code-Änderung mit-driften,
genau das Muster, das dieser Wächter selbst bei ANDEREN Tests aufspüren
soll). ``scan_repo`` gegen den echten Baum wird separat, informativ, in
einem eigenen Test ohne Assertions gegen Zahlen abgedeckt.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import proactive_watcher as pw  # noqa: E402


# ---------------------------------------------------------------------------
# 1) Testdaten-Drift
# ---------------------------------------------------------------------------
def test_erkennt_hartkodierte_zahl_gegen_produktionsdaten():
    inhalt = (
        "coll = json.load(open('data/forward_collection.json'))\n"
        "assert len(coll['records']) == 140\n"
    )
    funde = pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py")
    assert len(funde) == 1
    assert funde[0].klasse == pw.KLASSE_TESTDATEN_DRIFT
    assert funde[0].zeile == 2


def test_keine_drift_bei_reiner_fixture():
    inhalt = "coll = {'records': [1, 2, 3]}\nassert len(coll['records']) == 3\n"
    assert pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py") == []


def test_keine_drift_bei_kommentarzeile():
    inhalt = (
        "coll = json.load(open('data/report.json'))\n"
        "# assert len(coll['x']) == 999  (alter Wert, absichtlich auskommentiert)\n"
    )
    assert pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py") == []


def test_keine_drift_wenn_produktionsdaten_kopiert_werden():
    """Deepcopy + anschließendes Zurechtschneiden macht aus Produktionsdaten
    eine feste Fixture — kein Drift-Risiko mehr (Kalibrierung 20.09.2026:
    das war die Hauptquelle falscher Treffer im ersten Entwurf)."""
    inhalt = (
        "coll = json.load(open('data/forward_collection.json'))\n"
        "c = copy.deepcopy(coll)\n"
        "c['records'] = c['records'][:3]\n"
        "assert len(c['records']) == 3\n"
    )
    assert pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py") == []


def test_keine_drift_bei_einzelwert_ohne_len():
    """Ein einzelner fixer Feldwert (Score/Datum/Preis) ist kein Anzahl-
    Drift-Muster — bewusst NICHT erfasst (siehe Modul-Docstring)."""
    inhalt = (
        "coll = json.load(open('data/report.json'))\n"
        "assert coll['records'][0]['score_heuristic'] == 88.2\n"
    )
    assert pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py") == []


# ---------------------------------------------------------------------------
# 2) Veraltete Feldreferenz (Kommentar/Code auseinandergelaufen)
# ---------------------------------------------------------------------------
def test_erkennt_veraltete_feldreferenz():
    inhalt = (
        "def stale_markets(report):\n"
        "    # Quelle ist diag.bar_lag_trading_days\n"
        "    lag = (market.get('diag') or {}).get('bar_lag_session_days')\n"
        "    return lag\n"
    )
    funde = pw.erkenne_veraltete_feldreferenz(inhalt, "scripts/forward_collection.py")
    assert len(funde) == 1
    assert "bar_lag_trading_days" in funde[0].beschreibung


def test_keine_veraltete_feldreferenz_wenn_konsistent():
    inhalt = (
        "def stale_markets(report):\n"
        "    # Quelle ist diag.bar_lag_session_days\n"
        "    lag = (market.get('diag') or {}).get('bar_lag_session_days')\n"
        "    return lag\n"
    )
    assert pw.erkenne_veraltete_feldreferenz(inhalt, "x.py") == []


# ---------------------------------------------------------------------------
# 3) Fehlende Registry-Einträge
# ---------------------------------------------------------------------------
def test_erkennt_fehlenden_registry_eintrag():
    config_inhalt = "NEW_GATE_CRIT = 3          # Kommentar\n"
    registry_inhalt = "# Nichts über NEW_GATE hier.\n"
    funde = pw.erkenne_fehlende_registry_eintraege(config_inhalt, registry_inhalt)
    assert len(funde) == 1
    assert funde[0].klasse == pw.KLASSE_FEHLENDE_REGISTRY


def test_kein_fund_wenn_registry_eintrag_vorhanden():
    config_inhalt = "NEW_GATE_CRIT = 3\n"
    registry_inhalt = "Siehe NEW_GATE_CRIT für Details.\n"
    assert pw.erkenne_fehlende_registry_eintraege(config_inhalt, registry_inhalt) == []


def test_ignoriert_parameter_ohne_pflicht_suffix():
    config_inhalt = "MARKETS = ['US', 'DE']\n"
    assert pw.erkenne_fehlende_registry_eintraege(config_inhalt, "") == []


# ---------------------------------------------------------------------------
# 4) Key-/Secret-Exposure
# ---------------------------------------------------------------------------
def test_erkennt_unredigierte_exception_bei_api_key_datei():
    inhalt = (
        "api_key = os.environ.get('TWELVE_DATA_API_KEY')\n"
        "def fetch(ticker):\n"
        "    try:\n"
        "        pass\n"
        "    except Exception as exc:\n"
        "        detail = f\"Fehler: {exc}\"\n"
    )
    funde = pw.erkenne_key_exposure(inhalt, "scripts/beispiel.py")
    assert len(funde) == 1
    assert funde[0].klasse == pw.KLASSE_KEY_EXPOSURE


def test_kein_fund_wenn_redact_verwendet():
    inhalt = (
        "api_key = os.environ.get('TWELVE_DATA_API_KEY')\n"
        "def fetch(ticker):\n"
        "    except Exception as exc:\n"
        "        detail = _redact(f\"Fehler: {exc}\", api_key)\n"
    )
    assert pw.erkenne_key_exposure(inhalt, "scripts/beispiel.py") == []


def test_kein_fund_ohne_api_key_in_datei():
    inhalt = "def f():\n    except Exception as exc:\n        detail = f'{exc}'\n"
    assert pw.erkenne_key_exposure(inhalt, "scripts/harmlos.py") == []


# ---------------------------------------------------------------------------
# 5) Struktur-Inkonsistenz zwischen parallelen Fallback-Pfaden
# ---------------------------------------------------------------------------
def test_erkennt_strukturelle_abweichung_zwischen_fallbacks():
    inhalt = '''
def _make_yfinance_with_td_fallback():
    calls = {"n": 0}
    def _fetch(ticker):
        calls["n"] += 1
        _log("x")
        detail = _redact(f"{exc}", key)
        return outcome
    return _fetch

def _make_yfinance_with_av_fallback():
    def _fetch(ticker):
        _log("x")
        detail = f"{exc}"
        return outcome
    return _fetch
'''
    funde = pw.erkenne_struktur_inkonsistenz(inhalt, "scripts/elliott_pipeline.py")
    assert len(funde) == 1
    assert funde[0].klasse == pw.KLASSE_STRUKTUR_INKONSISTENZ
    assert "_redact(" in funde[0].beschreibung


def test_kein_fund_wenn_fallbacks_strukturgleich():
    inhalt = '''
def _make_yfinance_with_td_fallback():
    def _fetch(ticker):
        calls["n"] += 1
        _log("x")
        detail = _redact(f"{exc}", key)
    return _fetch

def _make_yfinance_with_av_fallback():
    def _fetch(ticker):
        calls["n"] += 1
        _log("x")
        detail = _redact(f"{exc}", key)
    return _fetch
'''
    assert pw.erkenne_struktur_inkonsistenz(inhalt, "x.py") == []


# ---------------------------------------------------------------------------
# Rote Linie — Mutationsprobe: jede Zeile der Klassifikation einzeln
# durchgetestet, inkl. der beiden Default-Fälle (leer, unbekannt).
# ---------------------------------------------------------------------------
def test_rote_linie_bei_score_pipeline_datei():
    assert pw.beruehrt_rote_linie(["scripts/elliott_pipeline.py"]) is True


def test_rote_linie_bei_sammlungs_gate_datei():
    assert pw.beruehrt_rote_linie(["scripts/forward_collection.py"]) is True


def test_rote_linie_bei_evaluate():
    assert pw.beruehrt_rote_linie(["scripts/evaluate.py"]) is True


def test_rote_linie_bei_qualitaets_marker():
    for name in ("mark_episode_splits.py", "mark_in_session_creation.py",
                 "mark_stale_market_records.py"):
        assert pw.beruehrt_rote_linie([f"scripts/{name}"]) is True, name


def test_rote_linie_bei_config():
    assert pw.beruehrt_rote_linie(["config.py"]) is True


def test_keine_rote_linie_bei_reinem_test():
    assert pw.beruehrt_rote_linie(["tests/test_irgendwas.py"]) is False


def test_keine_rote_linie_bei_markdown_doku():
    assert pw.beruehrt_rote_linie(["docs/validation_registry.md"]) is False
    assert pw.beruehrt_rote_linie(["README.md"]) is False


def test_keine_rote_linie_bei_guardian_agent_doku():
    assert pw.beruehrt_rote_linie([".claude/agents/guardian.md"]) is False


def test_rote_linie_bei_unbekanntem_pfad_default_konservativ():
    """Kern der Auftrags-Vorgabe: 'bei Unklarheit: immer ja, nie raten'."""
    assert pw.beruehrt_rote_linie(["scripts/irgendein_neues_skript.py"]) is True
    assert pw.beruehrt_rote_linie(["docs/index.html"]) is True
    assert pw.beruehrt_rote_linie([".github/workflows/neu.yml"]) is True


def test_rote_linie_bei_leerer_liste_konservativ():
    assert pw.beruehrt_rote_linie([]) is True


def test_rote_linie_bei_gemischter_liste_eine_reicht():
    """EIN rote-Linie-Pfad in einer sonst sicheren Liste reicht, um den
    gesamten Diff als rote Linie zu klassifizieren (kein Mitteln)."""
    assert pw.beruehrt_rote_linie(
        ["tests/test_x.py", "README.md", "config.py"]) is True


def test_rote_linie_bei_ausschliesslich_sicheren_dateien_false():
    assert pw.beruehrt_rote_linie(
        ["tests/test_x.py", "tests/test_y.py", "SESSION_HANDOVER.md"]) is False


def test_fund_setzt_rote_linie_selbst_konsistent_zur_klassifikation():
    """Ein Fund kann rote_linie nicht widersprüchlich zur zentralen Prüfung
    setzen — __post_init__ berechnet es IMMER neu aus betroffene_dateien."""
    f_sicher = pw.Fund(klasse="x", datei="tests/test_a.py", zeile=1,
                        beschreibung="egal")
    assert f_sicher.rote_linie is False
    f_unsicher = pw.Fund(klasse="x", datei="scripts/evaluate.py", zeile=1,
                          beschreibung="egal")
    assert f_unsicher.rote_linie is True


# ---------------------------------------------------------------------------
# Key-Exposure ist NIE rote Linie (fest verdrahtete Ausnahme, 21.09.2026) —
# Mutationsprobe: JEDE rote-Linie-Datei muss trotzdem False liefern, wenn
# die Fund-Klasse key_exposure ist; JEDE andere Klasse bleibt unverändert
# dateibasiert (die Ausnahme gilt nach Klasse, nicht nach Datei).
# ---------------------------------------------------------------------------
def test_key_exposure_ist_nie_rote_linie_auch_in_rote_linie_dateien():
    for datei in ("scripts/elliott_pipeline.py", "scripts/forward_collection.py",
                  "scripts/evaluate.py", "config.py", "scripts/unbekannt.py"):
        f = pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei=datei, zeile=1,
                    beschreibung="egal")
        assert f.rote_linie is False, datei


def test_key_exposure_ausnahme_gilt_nach_klasse_nicht_nach_datei():
    """Dieselbe Datei, ANDERE Klasse -> die alte, konservative Datei-Prüfung
    greift unverändert. Beweist: die Ausnahme ist an die Klasse gebunden,
    nicht am Fund-Objekt vorbeigeschleust worden."""
    f_key_exposure = pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE,
                              datei="scripts/elliott_pipeline.py", zeile=1,
                              beschreibung="egal")
    f_andere_klasse = pw.Fund(klasse=pw.KLASSE_VERALTETE_DOKU,
                               datei="scripts/elliott_pipeline.py", zeile=1,
                               beschreibung="egal")
    assert f_key_exposure.rote_linie is False
    assert f_andere_klasse.rote_linie is True


def test_andere_vier_klassen_bleiben_dateibasiert_klassifiziert():
    """Regressionsschutz: die Ausnahme darf NUR key_exposure betreffen —
    keine der anderen vier Klassen darf durch diese Änderung plötzlich
    ebenfalls nie rote Linie sein."""
    for klasse in (pw.KLASSE_TESTDATEN_DRIFT, pw.KLASSE_VERALTETE_DOKU,
                   pw.KLASSE_FEHLENDE_REGISTRY, pw.KLASSE_STRUKTUR_INKONSISTENZ):
        f = pw.Fund(klasse=klasse, datei="config.py", zeile=1,
                    beschreibung="egal")
        assert f.rote_linie is True, klasse


def test_beruehrt_rote_linie_funktion_selbst_bleibt_dateibasiert_unveraendert():
    """Die zentrale, wiederverwendete Klassifikationsfunktion selbst kennt
    gar keine Fund-Klassen (nimmt nur Pfade) — die Ausnahme lebt bewusst
    ausschließlich in Fund.__post_init__, nicht hier (Auftrags-Grenze:
    beruehrt_rote_linie() bleibt die eine, wiederverwendete Wahrheit für
    alle anderen Aufrufer)."""
    assert pw.beruehrt_rote_linie(["scripts/elliott_pipeline.py"]) is True


# ---------------------------------------------------------------------------
# Tagesbericht — EIN Text für alle Funde eines Laufs (Auftrag Punkt 5)
# ---------------------------------------------------------------------------
def test_tagesbericht_ohne_funde():
    text = pw.tagesbericht([])
    assert "Keine Funde" in text


def test_tagesbericht_gruppiert_nach_roter_linie():
    gruen = pw.Fund(klasse="x", datei="tests/test_a.py", zeile=1, beschreibung="A")
    rot = pw.Fund(klasse="y", datei="scripts/evaluate.py", zeile=2, beschreibung="B")
    text = pw.tagesbericht([gruen, rot])
    assert "1 ohne rote Linie" in text
    assert "1 mit roter Linie" in text
    assert "[self-merge-kandidat]" in text
    assert "[draft/easy]" in text


# ---------------------------------------------------------------------------
# Integrations-Rauchtest gegen den echten Baum — rein informativ, KEINE
# Assertion gegen Zahlen (sonst wäre der Wächter-Test selbst Testdaten-
# Drift-anfällig — die Ironie wäre nicht witzig).
# ---------------------------------------------------------------------------
def test_scan_repo_laeuft_ohne_fehler_gegen_den_echten_baum():
    funde = pw.scan_repo(ROOT)
    assert isinstance(funde, list)
    for f in funde:
        assert isinstance(f, pw.Fund)
        assert f.rote_linie == pw.beruehrt_rote_linie(f.betroffene_dateien)
