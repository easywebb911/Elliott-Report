"""Proaktiver Fehler-Wächter (20.09.2026) — Wert-Tests je Fehlerklasse +
Mutationsprobe am Klassifizierungs-Mechanismus (rote Linie).

Reine Werttests gegen synthetische Fälle — bewusst KEIN Scan des echten
Repo-Codes in diesen Tests (der würde bei jeder Code-Änderung mit-driften,
genau das Muster, das dieser Wächter selbst bei ANDEREN Tests aufspüren
soll). ``scan_repo`` gegen den echten Baum wird separat, informativ, in
einem eigenen Test ohne Assertions gegen Zahlen abgedeckt.
"""
from __future__ import annotations

import json
import subprocess
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
# 1b) Listen-/Mengen-Gleichheitsvergleich gegen eine hartkodierte Liste
# (AOF.DE-Diagnose 22.09.2026) — zweites Testdaten-Drift-Muster, unabhängig
# vom Längen-Vergleich oben.
# ---------------------------------------------------------------------------
def test_erkennt_listen_vergleich_gegen_erwartete_konstante():
    inhalt = (
        "ERWARTETE_FAELLE = [\n"
        "    ('A', 'DE', '2026-01-01T00:00:00Z', 1),\n"
        "]\n"
        "\n"
        "def test_x(replay):\n"
        "    gefunden = [t for t in replay]\n"
        "    assert gefunden == ERWARTETE_FAELLE\n"
    )
    funde = pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py")
    assert len(funde) == 1
    assert "ERWARTETE_FAELLE" in funde[0].beschreibung
    assert funde[0].zeile == 7


def test_erkennt_listen_vergleich_mit_sorted_wrapper():
    inhalt = (
        "ERWARTETE_MARKIERUNGEN = [('A', 'DE', 'x', 1)]\n"
        "\n"
        "def test_x():\n"
        "    markiert = []\n"
        "    assert sorted(markiert) == sorted(ERWARTETE_MARKIERUNGEN)\n"
    )
    funde = pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py")
    assert len(funde) == 1
    assert funde[0].zeile == 5


def test_kein_listen_fund_ohne_konstanten_definition():
    """Der Name `ERWARTETE_X` taucht in einem assert auf, ist aber NIRGENDS
    im File als Liste/Tupel definiert (z. B. Import aus einem anderen
    Modul) — kein Fund, das Muster kann nicht bestätigt werden."""
    inhalt = "def test_x():\n    assert ergebnis == ERWARTETE_X\n"
    assert pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py") == []


def test_kein_listen_fund_bei_skalarer_erwartet_konstante():
    """`ERWARTET_SCHWELLE = 5` ist ein einzelner Schwellwert, keine Liste —
    `_ERWARTET_LISTE_DEF` verlangt `= [` oder `= (`, matcht hier nicht."""
    inhalt = (
        "ERWARTET_SCHWELLE = 5\n"
        "def test_x():\n"
        "    assert ergebnis == ERWARTET_SCHWELLE\n"
    )
    assert pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py") == []


def test_kein_listen_fund_bei_nicht_erwartet_praefix():
    """Namenskonvention ist das Signal — eine Konstante ohne `ERWARTET`-
    Präfix wird bewusst nicht erfasst (sonst zu viel Rauschen, siehe
    Kalibrierungslauf 20.09.2026)."""
    inhalt = (
        "SONSTIGE_LISTE = [1, 2, 3]\n"
        "def test_x():\n"
        "    assert ergebnis == SONSTIGE_LISTE\n"
    )
    assert pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py") == []


def test_listen_vergleich_erkennung_aendert_bestehende_laengen_funde_nicht():
    """Regression: die beiden Muster laufen unabhängig nebeneinander — ein
    Fund vom Längen-Muster darf durch die Erweiterung nicht verschwinden
    oder sich verdoppeln."""
    inhalt = (
        "coll = json.load(open('data/forward_collection.json'))\n"
        "assert len(coll['records']) == 140\n"
    )
    funde = pw.erkenne_testdaten_drift(inhalt, "tests/test_beispiel.py")
    assert len(funde) == 1
    assert "Länge/Anzahl" in funde[0].beschreibung


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
# 6) Fremde Datenquelle in einem tatsächlichen Kandidaten (26.09.2026,
# Wächter-Zusatz zur Diagnose "Twelve-Data/Alpha-Vantage-Fallback"). Reine
# Beobachtungs-Meldung — KEIN Fehler, KEIN Block, keine neue Konsistenz-
# prüfung. Der zentrale Test simuliert genau den in der Diagnose als
# "bisher nie beobachtet" beschriebenen Fall (synthetischer Kandidat mit
# data_source="alphavantage_fallback") und prüft, dass der Wächter darauf
# TATSÄCHLICH anschlägt (nicht nur, dass die Funktion aufgerufen wird).
# ---------------------------------------------------------------------------
def _report_mit_kandidat(data_source):
    eintrag = {"ticker": "KCO.DE"}
    if data_source is not None:
        eintrag["data_source"] = data_source
    return {"markets": {"DE": {"candidates": [eintrag]},
                        "US": {"candidates": [{"ticker": "AAPL",
                                                "data_source": "yfinance"}]}}}


def test_erkennt_alphavantage_fallback_bei_tatsaechlichem_kandidaten():
    """Der zentrale Auftrags-Test: ein synthetischer Kandidat mit
    data_source="alphavantage_fallback" MUSS einen Fund auslösen — genau
    der Fall, der laut Diagnose vom 26.09.2026 bisher in keinem committeten
    report.json-Stand je aufgetreten ist."""
    report = _report_mit_kandidat("alphavantage_fallback")
    funde = pw.erkenne_nicht_yfinance_datenquelle(report, "data/report.json")
    assert len(funde) == 1
    assert funde[0].klasse == pw.KLASSE_FREMDE_DATENQUELLE
    assert funde[0].rote_linie is True  # keine Ausnahme wie bei key_exposure
    assert "KCO.DE" in funde[0].beschreibung
    assert "alphavantage_fallback" in funde[0].beschreibung
    # Der Yfinance-Kandidat im selben Report darf KEINEN zweiten Fund
    # auslösen — sonst wäre die Prüfung nicht auf den einen Ticker verengt.
    assert "AAPL" not in funde[0].beschreibung


def test_erkennt_twelvedata_fallback_ebenso_generisch():
    """Prüft != "yfinance" statt einer festen Quellen-Liste (Auftrags-
    Kriterium 4): Twelve-Data ist NICHT eigens im Code genannt, muss aber
    trotzdem als Fund auffallen."""
    report = _report_mit_kandidat("twelvedata_fallback")
    funde = pw.erkenne_nicht_yfinance_datenquelle(report, "data/report.json")
    assert len(funde) == 1
    assert "twelvedata_fallback" in funde[0].beschreibung


def test_erkennt_eine_hypothetische_dritte_quelle_ungeraten():
    """Auftrags-Kriterium 4, wörtlich geprüft: eine völlig neue, im Code nie
    erwähnte Quelle ("polygon_fallback") muss GENAUSO anschlagen — die
    Prüfung ist gegen != "yfinance" gebaut, nicht gegen eine Aufzählung."""
    report = _report_mit_kandidat("polygon_fallback")
    funde = pw.erkenne_nicht_yfinance_datenquelle(report, "data/report.json")
    assert len(funde) == 1
    assert "polygon_fallback" in funde[0].beschreibung


def test_kein_fund_bei_yfinance_datenquelle():
    report = _report_mit_kandidat("yfinance")
    assert pw.erkenne_nicht_yfinance_datenquelle(report, "data/report.json") == []


def test_kein_fund_wenn_data_source_feld_fehlt():
    """Alt-Records/Watchlist-Randfälle ohne das Feld sind kein Fund —
    fehlend heißt nicht "fremd"."""
    report = _report_mit_kandidat(None)
    assert pw.erkenne_nicht_yfinance_datenquelle(report, "data/report.json") == []


def test_kein_fund_bei_leerem_oder_kaputtem_markets_block():
    """Fail-soft (Auftrags-Kriterium 6): eine unerwartete/fehlende Struktur
    liefert keine Funde, keinen Absturz."""
    assert pw.erkenne_nicht_yfinance_datenquelle({}, "data/report.json") == []
    assert pw.erkenne_nicht_yfinance_datenquelle(
        {"markets": "kaputt"}, "data/report.json") == []
    assert pw.erkenne_nicht_yfinance_datenquelle(
        {"markets": {"DE": "kaputt"}}, "data/report.json") == []
    assert pw.erkenne_nicht_yfinance_datenquelle(
        {"markets": {"DE": {"candidates": ["kaputt"]}}}, "data/report.json") == []


def test_beide_maerkte_werden_geprueft():
    report = {"markets": {
        "US": {"candidates": [{"ticker": "EA", "data_source": "twelvedata_fallback"}]},
        "DE": {"candidates": [{"ticker": "KCO.DE", "data_source": "alphavantage_fallback"}]},
    }}
    funde = pw.erkenne_nicht_yfinance_datenquelle(report, "data/report.json")
    assert len(funde) == 2
    getroffene_ticker = {f.beschreibung.split(" ")[0].split("/")[1] for f in funde}
    assert getroffene_ticker == {"EA", "KCO.DE"}


def test_scan_repo_bindet_klasse_6_gegen_das_echte_report_json_ein(tmp_path):
    """Integrations-Mutationsprobe (Auftrags-Kriterium 1: der Fund muss beim
    ERSTEN echten Auftreten sichtbar werden, nicht erst rückwirkend) —
    simuliert genau das über eine isolierte Kopie von data/report.json,
    NICHT über den echten Baum (der hat laut Diagnose aktuell keinen
    solchen Kandidaten, s. test_scan_repo_laeuft_ohne_fehler_gegen_den_
    echten_baum unten)."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "report.json").write_text(
        json.dumps(_report_mit_kandidat("alphavantage_fallback")),
        encoding="utf-8",
    )
    funde = pw.scan_repo(tmp_path)
    treffer = [f for f in funde if f.klasse == pw.KLASSE_FREMDE_DATENQUELLE]
    assert len(treffer) == 1
    assert treffer[0].datei == "data/report.json"

    # Mutationsprobe: derselbe Report OHNE die fremde Quelle -> der Fund
    # verschwindet wieder (beweist, dass scan_repo() den Fund tatsächlich
    # AN DIESER STELLE erzeugt, nicht zufällig aus einer anderen Quelle).
    (tmp_path / "data" / "report.json").write_text(
        json.dumps(_report_mit_kandidat("yfinance")), encoding="utf-8",
    )
    funde_ohne = pw.scan_repo(tmp_path)
    assert not [f for f in funde_ohne if f.klasse == pw.KLASSE_FREMDE_DATENQUELLE]


def test_scan_repo_uebersteht_fehlendes_oder_kaputtes_report_json(tmp_path):
    """Fail-soft am Orchestrator selbst: fehlende Datei UND kaputtes JSON
    dürfen den gesamten Lauf nie brechen."""
    funde = pw.scan_repo(tmp_path)  # gar kein data/report.json vorhanden
    assert isinstance(funde, list)

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "report.json").write_text("{ nicht valides json",
                                                    encoding="utf-8")
    funde = pw.scan_repo(tmp_path)  # kaputtes JSON
    assert isinstance(funde, list)


# ---------------------------------------------------------------------------
# 7) SESSION_HANDOVER.md fällt hinter main zurück (Diagnose-Auftrag
# 27.09.2026). Zentraler Test: eine synthetische Commit-Historie mit BEIDEN
# PR-tragenden Formaten (echter Merge-Commit, Squash-Suffix), einem
# Bot-Datencommit OHNE PR-Bezug und einer echten Lücke — der Wächter muss
# GENAU die Lücke finden, den Bot-Commit nicht fälschlich meden.
# ---------------------------------------------------------------------------
def _git_repo_mit_commits(repo_pfad, commit_subjects):
    """Baut ein Mini-Git-Repo mit leeren Commits — nur die Subject-Zeile
    zählt für den Detektor (der liest ausschließlich `git log --format=%s`),
    echte Dateiänderungen sind für diesen Test irrelevant."""
    subprocess.run(["git", "init", "-q"], cwd=repo_pfad, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"],
                    cwd=repo_pfad, check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                    cwd=repo_pfad, check=True)
    for subject in commit_subjects:
        subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", subject],
                        cwd=repo_pfad, check=True)


_SYNTHETISCHE_HISTORIE = (
    "Initial commit",
    "Merge pull request #10 from x/feature-a",       # echter Merge-Commit
    "chore(data): täglicher Elliott-Report + Sammlung [skip ci]",  # Bot, kein PR
    "feat(x): irgendein Fix (#11)",                   # Squash-Suffix
    "Merge pull request #12 from x/feature-b",        # DIE LÜCKE — fehlt unten
)


def test_erkennt_fehlende_pr_ueber_beide_commit_formate(tmp_path):
    """Zentraler Auftrags-Test: das Handover erwähnt NUR #10 (Merge-Commit) —
    #11 (Squash-Suffix) UND #12 (Merge-Commit) fehlen und müssen BEIDE
    gefunden werden. Bewusst so aufgebaut (statt #11 im Handover mit
    aufzuführen): nur so fällt eine kaputte Squash-Suffix-Erkennung
    überhaupt auf — wäre #11 bereits im Handover erwähnt, würde ihr
    Verschwinden aus der Extraktion unsichtbar bleiben (Mutationsprobe
    27.09.2026 hat genau diese Schwäche in einer Vorfassung aufgedeckt)."""
    _git_repo_mit_commits(tmp_path, _SYNTHETISCHE_HISTORIE)
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        "Stand nach PR #10 — im PR-Index erwähnt.\n",
        encoding="utf-8",
    )
    funde = pw.erkenne_handover_luecke(tmp_path)
    assert len(funde) == 1
    assert funde[0].klasse == pw.KLASSE_HANDOVER_LUECKE
    assert "#11" in funde[0].beschreibung
    assert "#12" in funde[0].beschreibung
    assert "#10" not in funde[0].beschreibung


def test_kein_fund_wenn_handover_alle_main_prs_erwaehnt(tmp_path):
    _git_repo_mit_commits(tmp_path, _SYNTHETISCHE_HISTORIE)
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        "Stand nach PR #10, #11 und #12 — vollständig nachgezogen.\n",
        encoding="utf-8",
    )
    assert pw.erkenne_handover_luecke(tmp_path) == []


def test_kein_fund_ohne_git_repo(tmp_path):
    """Fail-soft: kein .git-Verzeichnis (z. B. ein reines Datenverzeichnis)
    darf den Lauf nie brechen."""
    (tmp_path / "SESSION_HANDOVER.md").write_text("Stand nach PR #1.\n",
                                                    encoding="utf-8")
    assert pw.erkenne_handover_luecke(tmp_path) == []


def test_kein_fund_ohne_handover_datei(tmp_path):
    _git_repo_mit_commits(tmp_path, _SYNTHETISCHE_HISTORIE)
    assert pw.erkenne_handover_luecke(tmp_path) == []  # SESSION_HANDOVER.md fehlt


def test_kein_fund_bei_leerer_pr_extraktion(tmp_path):
    """Regressionsschutz (nicht mehr durch expliziten Guard erzwungen, siehe
    Mutationsprobe 27.09.2026 im Modul-Kommentar zu Klasse 7): eine Historie
    ganz ohne PR-tragenden Commit (z. B. Shallow-Checkout mit fetch-depth:1,
    hier simuliert durch reine Bot-/Init-Commits) ergibt korrekt KEINEN
    Fund — mathematisch zwingend (main_prs - erwaehnte_prs bei leerer
    main_prs), nicht durch eine Sonderbedingung."""
    _git_repo_mit_commits(tmp_path, (
        "Initial commit",
        "chore(data): täglicher Elliott-Report + Sammlung [skip ci]",
    ))
    (tmp_path / "SESSION_HANDOVER.md").write_text("Stand: leer.\n",
                                                    encoding="utf-8")
    assert pw.erkenne_handover_luecke(tmp_path) == []


def test_handover_luecke_determinismus(tmp_path):
    """Gleicher main-Stand -> gleicher Fund, kein Zufallselement (Auftrags-
    Kriterium 6)."""
    _git_repo_mit_commits(tmp_path, _SYNTHETISCHE_HISTORIE)
    (tmp_path / "SESSION_HANDOVER.md").write_text("Stand nach PR #10 und #11.\n",
                                                    encoding="utf-8")
    erster_lauf = [f.beschreibung for f in pw.erkenne_handover_luecke(tmp_path)]
    zweiter_lauf = [f.beschreibung for f in pw.erkenne_handover_luecke(tmp_path)]
    assert erster_lauf == zweiter_lauf


def test_handover_luecke_ist_keine_rote_linie():
    """SESSION_HANDOVER.md endet auf .md -> SICHERE_DATEIEN_SUFFIXE greift,
    genau wie bei den bisherigen reinen Doku-Fixes (#149/#152): ein echter
    Fund dieser Klasse ist ein Self-Merge-Kandidat, kein Draft-PR-Fall."""
    f = pw.Fund(klasse=pw.KLASSE_HANDOVER_LUECKE, datei="SESSION_HANDOVER.md",
                zeile=None, beschreibung="egal",
                betroffene_dateien=["SESSION_HANDOVER.md"])
    assert f.rote_linie is False


def test_scan_repo_bindet_klasse_7_ein(tmp_path):
    """Integrations-Test: scan_repo() muss den Fund über den Orchestrator
    finden, nicht nur bei direktem Funktionsaufruf."""
    _git_repo_mit_commits(tmp_path, _SYNTHETISCHE_HISTORIE)
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        "Stand nach PR #10 und #11.\n", encoding="utf-8",
    )
    funde = pw.scan_repo(tmp_path)
    treffer = [f for f in funde if f.klasse == pw.KLASSE_HANDOVER_LUECKE]
    assert len(treffer) == 1
    assert "#12" in treffer[0].beschreibung


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


def test_andere_sechs_klassen_bleiben_dateibasiert_klassifiziert():
    """Regressionsschutz: die Ausnahme darf NUR key_exposure betreffen —
    keine der anderen sechs Klassen darf durch diese Änderung plötzlich
    ebenfalls nie rote Linie sein."""
    for klasse in (pw.KLASSE_TESTDATEN_DRIFT, pw.KLASSE_VERALTETE_DOKU,
                   pw.KLASSE_FEHLENDE_REGISTRY, pw.KLASSE_STRUKTUR_INKONSISTENZ,
                   pw.KLASSE_FREMDE_DATENQUELLE, pw.KLASSE_HANDOVER_LUECKE):
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
# Push-Kurzform (Auftrag 26.09.2026) — Alltagssprache statt Rohdaten
# ---------------------------------------------------------------------------
# WERT-TEST mit der Form der 7 echten Funde vom 26.09.2026 (7×
# testdaten_drift, alle ohne rote Linie) — bewusst als KONSTRUIERTE Liste,
# nicht als Live-Scan: ein Assert gegen scan_repo(ROOT)s tatsächliche Zahl
# wäre selbst genau die Testdaten-Drift-Anfälligkeit, die dieser Wächter bei
# ANDEREN Tests aufspürt (s. Kommentar bei test_scan_repo_laeuft_ohne_
# fehler_gegen_den_echten_baum unten). Nachgerechnet von Hand:
# python3 -c "... pw.scan_repo(Path('.')) ..." -> 7 Fund(e), alle
# testdaten_drift, alle rote_linie=False.
def _sieben_echte_funde() -> list:
    return [
        pw.Fund(klasse=pw.KLASSE_TESTDATEN_DRIFT, datei="tests/test_a.py",
                zeile=i + 1, beschreibung=f"tests/test_a.py:{i + 1} ...",
                betroffene_dateien=["tests/test_a.py"])
        for i in range(7)
    ]


def test_push_kurzform_mit_den_sieben_echten_funden_vom_26_09():
    text = pw.push_kurzform(_sieben_echte_funde())
    assert text == (
        "🔍 Wächter: 7 Fund(e) — 7 Kosmetik-Kandidat(en), 0 wichtig — "
        "7× Testdaten veraltet"
    )


def test_push_kurzform_ohne_funde():
    assert pw.push_kurzform([]) == "🔍 Wächter: keine Funde"


def test_push_kurzform_enthaelt_nie_dateipfade_zeilen_oder_code():
    """Der eigentliche Auftrags-Kern (Punkt 1): OHNE Dateipfade/
    Zeilennummern/Code im Push-Text selbst — Fund.beschreibung (die genau
    das enthält) darf im Ergebnis nirgends auftauchen."""
    funde = [
        pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei="scripts/notify.py",
                zeile=42, beschreibung="scripts/notify.py:42 API_KEY = 'geheim'",
                betroffene_dateien=["scripts/notify.py"]),
        pw.Fund(klasse=pw.KLASSE_STRUKTUR_INKONSISTENZ, datei="scripts/evaluate.py",
                zeile=None, beschreibung="scripts/evaluate.py widerspricht x.py",
                betroffene_dateien=["scripts/evaluate.py"]),
    ]
    text = pw.push_kurzform(funde)
    for f in funde:
        assert f.datei not in text
        assert f.beschreibung not in text
    assert ":42" not in text
    assert "Sicherheits-Hinweis" in text
    assert "Unstimmigkeit im Code" in text


def test_push_kurzform_kategorien_absteigend_sortiert_deterministisch():
    """Mutationsprobe fürs Sortierkriterium: die häufigste Kategorie zuerst,
    bei Gleichstand alphabetisch — nicht dict-Einfüge-/Zufallsreihenfolge."""
    funde = (
        [pw.Fund(klasse=pw.KLASSE_VERALTETE_DOKU, datei="a.py", zeile=1,
                 beschreibung="x", betroffene_dateien=["tests/a.py"])]
        + [pw.Fund(klasse=pw.KLASSE_TESTDATEN_DRIFT, datei="a.py", zeile=1,
                   beschreibung="x", betroffene_dateien=["tests/a.py"])
           for _ in range(3)]
    )
    text = pw.push_kurzform(funde)
    assert text.index("Testdaten veraltet") < text.index("Text veraltet")


def test_kategorie_alltagssprache_deckt_alle_sieben_klassen_ab():
    for klasse in (pw.KLASSE_TESTDATEN_DRIFT, pw.KLASSE_VERALTETE_DOKU,
                   pw.KLASSE_FEHLENDE_REGISTRY, pw.KLASSE_KEY_EXPOSURE,
                   pw.KLASSE_STRUKTUR_INKONSISTENZ, pw.KLASSE_FREMDE_DATENQUELLE,
                   pw.KLASSE_HANDOVER_LUECKE):
        assert klasse in pw.KATEGORIE_ALLTAGSSPRACHE
        # kein technischer Jargon: kein Unterstrich, keine Klassen-Kurznamen
        assert "_" not in pw.KATEGORIE_ALLTAGSSPRACHE[klasse]


def test_schreibe_job_summary_schreibt_bei_gesetzter_umgebungsvariable(
        tmp_path, monkeypatch):
    ziel = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(ziel))
    pw.schreibe_job_summary("voller technischer Bericht mit tests/a.py:12")
    assert "tests/a.py:12" in ziel.read_text(encoding="utf-8")


def test_schreibe_job_summary_ohne_umgebungsvariable_ist_fail_soft(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    pw.schreibe_job_summary("irrelevant")  # darf nicht werfen


def test_tagesbericht_bleibt_unveraendert_die_volle_technische_quelle():
    """GRENZEN: tagesbericht() selbst (Job-Summary-Inhalt) ändert sich
    NICHT — nur der Push nutzt jetzt push_kurzform() statt dieses Texts."""
    gruen = pw.Fund(klasse="x", datei="tests/test_a.py", zeile=1,
                    beschreibung="tests/test_a.py:1 A")
    text = pw.tagesbericht([gruen])
    assert "tests/test_a.py:1" in text
    assert "[self-merge-kandidat]" in text


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


def test_push_kurzform_gegen_den_echten_baum_bleibt_dateifrei():
    """Rein informativ, keine Zahlen-Assertion (s. o.) — aber die
    STRUKTURELLE Garantie (keine Dateipfade im Push-Text) muss auch gegen
    den echten, sich wandelnden Fund-Bestand halten."""
    funde = pw.scan_repo(ROOT)
    text = pw.push_kurzform(funde)
    for f in funde:
        assert f.datei not in text
