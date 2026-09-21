"""Proaktiver Fehler-Wächter, Phase 2 (überarbeitet 21.09.2026) — autonomes
Fixen OHNE Self-Merge.

Wert-Tests je Fehlerklasse (fixbar vs. bewusst nicht fixbar), Mutationsprobe
am (jetzt dreiwertigen) Entscheidungs-Automaten `entscheide()`, und eine
Orchestrierungs-Probe mit gefakten Guardian-/PR-Aufrufen (kein Netz, kein
Git — dasselbe Dependency-Injection-Muster wie
`auto_retry_watcher.dispatch_retry(post=...)`).

KEIN SELF-MERGE (siehe Modul-Docstring von proactive_fixer.py): Phase 2
erstellt für jeden fixbaren, nicht-rote-Linie-Fund IMMER einen Draft-PR,
der auf Easys manuellen Review wartet — unabhängig vom Guardian-Urteil.
Es gibt deshalb kein Probe-Modus-Datum und keinen "auto_gemergt"-Zustand
mehr zu testen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import proactive_fixer as fx  # noqa: E402
import proactive_watcher as pw  # noqa: E402


# ---------------------------------------------------------------------------
# Fix-Generator: veraltete Feldreferenz (KLASSE_VERALTETE_DOKU) — fixbar
# ---------------------------------------------------------------------------
def test_fixt_veraltete_feldreferenz_bei_eindeutigem_feld():
    alt = (
        "def stale_markets(report):\n"
        "    # Quelle ist diag.bar_lag_trading_days\n"
        "    lag = (market.get('diag') or {}).get('bar_lag_session_days')\n"
        "    return lag\n"
    )
    funde = pw.erkenne_veraltete_feldreferenz(alt, "tests/x.py")
    assert len(funde) == 1
    neu = fx.fixe_veraltete_feldreferenz(funde[0], alt)
    assert neu is not None
    assert "diag.bar_lag_session_days" in neu
    assert "diag.bar_lag_trading_days" not in neu
    # Vorher/Nachher-Beweis: der Fund ist wirklich weg, kein neuer entstanden.
    assert pw.erkenne_veraltete_feldreferenz(neu, "tests/x.py") == []


def test_lehnt_feldreferenz_fix_bei_mehrdeutigkeit_ab():
    alt = (
        "def f(report):\n"
        "    # diag.alt_feld\n"
        "    a = d.get('feld_a')\n"
        "    b = d.get('feld_b')\n"
        "    return a, b\n"
    )
    funde = pw.erkenne_veraltete_feldreferenz(alt, "tests/x.py")
    assert len(funde) == 1
    assert fx.fixe_veraltete_feldreferenz(funde[0], alt) is None


def test_lehnt_feldreferenz_fix_ab_wenn_zeile_fehlt():
    fund = pw.Fund(klasse=pw.KLASSE_VERALTETE_DOKU, datei="tests/x.py",
                    zeile=None, beschreibung="egal")
    assert fx.fixe_veraltete_feldreferenz(fund, "irgendwas\n") is None


# ---------------------------------------------------------------------------
# Fix-Generator: Key-Exposure (KLASSE_KEY_EXPOSURE) — fixbar im engen Fall,
# bewusst NICHT fixbar bei mehrzeiligen/bereits redigierten Aufrufen.
# ---------------------------------------------------------------------------
def test_fixt_key_exposure_bei_einzeiligem_fstring_mit_bekanntem_key_var():
    alt = (
        "api_key = os.environ.get('TWELVE_DATA_API_KEY')\n"
        "def fetch(ticker):\n"
        "    try:\n"
        "        pass\n"
        "    except Exception as exc:\n"
        "        return FetchOutcome(\n"
        "            reason=FETCH_ERROR,\n"
        "            detail=_redact(f\"woanders: {exc}\", api_key),\n"
        "        )\n"
        "\n"
        "def andere_funktion(ticker):\n"
        "    try:\n"
        "        pass\n"
        "    except Exception as exc:\n"
        "        detail = (\n"
        "            f\"Fallback: {type(exc).__name__}: {exc}\"\n"
        "        )\n"
        "        return detail\n"
    )
    funde = pw.erkenne_key_exposure(alt, "tests/x.py")
    assert len(funde) == 1
    fund = funde[0]
    neu = fx.fixe_key_exposure(fund, alt)
    assert neu is not None
    assert "_redact(f\"Fallback: {type(exc).__name__}: {exc}\", api_key)" in neu
    assert pw.erkenne_key_exposure(neu, "tests/x.py") == []


def test_lehnt_key_exposure_fix_ab_wenn_schon_mehrzeilig_redigiert():
    """Der Kalibrierungsfund vom 20.09.2026: `_redact(` steht auf einer
    VORHERGEHENDEN Zeile eines mehrzeiligen Aufrufs — der Fix-Generator darf
    das NICHT nochmal wrappen (`_redact(_redact(...))` wäre kaputt)."""
    alt = (
        "api_key = os.environ.get('TWELVE_DATA_API_KEY')\n"
        "def fetch(ticker):\n"
        "    except Exception as exc:\n"
        "        return FetchOutcome(\n"
        "            reason=FETCH_ERROR,\n"
        "            detail=_redact(\n"
        "                f\"Twelve-Data-Fallback: {type(exc).__name__}: {exc}\",\n"
        "                api_key,\n"
        "            ),\n"
        "        )\n"
    )
    # Der (korrigierte) Detektor selbst findet hier schon keinen Fund mehr —
    # das ist der PRIMÄRE Schutz. Simuliert trotzdem den Fall, in dem der
    # Detektor (hypothetisch) einen Fund gemeldet hätte, um zu beweisen,
    # dass der FIX-Generator eine ZWEITE, unabhängige Bremse ist.
    fund = pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei="tests/x.py", zeile=7,
                    beschreibung="egal")
    assert fx.fixe_key_exposure(fund, alt) is None


def test_lehnt_key_exposure_fix_ohne_bekannte_key_variable_ab():
    alt = (
        "os.environ.get('ANTHROPIC_API_KEY', '')\n"
        "def f():\n"
        "    except Exception as exc:\n"
        "        detail = f\"{type(exc).__name__}: {exc}\"\n"
    )
    fund = pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei="tests/x.py", zeile=4,
                    beschreibung="egal")
    assert fx.fixe_key_exposure(fund, alt) is None


def test_lehnt_key_exposure_fix_bei_komplexer_zeile_ab():
    alt = (
        "api_key = os.environ.get('X_API_KEY')\n"
        "def f():\n"
        "    _redact(f'anderswo', api_key)\n"
        "    except Exception as exc:\n"
        "        _log(f\"Fehler: {exc}\" + zusatz)\n"
    )
    fund = pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei="tests/x.py", zeile=5,
                    beschreibung="egal")
    assert fx.fixe_key_exposure(fund, alt) is None


# ---------------------------------------------------------------------------
# Die drei NICHT fixbaren Klassen — versuche_fix() lehnt IMMER ab (Auftrags-
# Grenze: kein inhaltliches Urteil raten).
# ---------------------------------------------------------------------------
def test_versuche_fix_lehnt_testdaten_drift_immer_ab():
    fund = pw.Fund(klasse=pw.KLASSE_TESTDATEN_DRIFT, datei="tests/x.py",
                    zeile=1, beschreibung="egal")
    assert fx.versuche_fix(fund, "beliebiger inhalt") is None


def test_versuche_fix_lehnt_fehlende_registry_immer_ab():
    fund = pw.Fund(klasse=pw.KLASSE_FEHLENDE_REGISTRY, datei="config.py",
                    zeile=1, beschreibung="egal")
    assert fx.versuche_fix(fund, "beliebiger inhalt") is None


def test_versuche_fix_lehnt_struktur_inkonsistenz_immer_ab():
    fund = pw.Fund(klasse=pw.KLASSE_STRUKTUR_INKONSISTENZ, datei="tests/x.py",
                    zeile=None, beschreibung="egal")
    assert fx.versuche_fix(fund, "beliebiger inhalt") is None


# ---------------------------------------------------------------------------
# pruefe_fix_wirkung — Vorher/Nachher-Beweis
# ---------------------------------------------------------------------------
def test_pruefe_fix_wirkung_positiv():
    alt = "# diag.alt\nlag = d.get('neu')\n"
    fund = pw.erkenne_veraltete_feldreferenz(alt, "tests/x.py")[0]
    neu = fx.fixe_veraltete_feldreferenz(fund, alt)
    assert fx.pruefe_fix_wirkung(fund, alt, neu) is True


def test_pruefe_fix_wirkung_negativ_wenn_fund_bestehen_bleibt():
    alt = "# diag.alt\nlag = d.get('neu')\n"
    fund = pw.erkenne_veraltete_feldreferenz(alt, "tests/x.py")[0]
    # "Fix", der nichts ändert -> der Fund besteht weiter.
    assert fx.pruefe_fix_wirkung(fund, alt, alt) is False


def test_pruefe_fix_wirkung_ohne_detektor_fuer_die_klasse_false():
    fund = pw.Fund(klasse=pw.KLASSE_TESTDATEN_DRIFT, datei="tests/x.py",
                    zeile=1, beschreibung="egal")
    assert fx.pruefe_fix_wirkung(fund, "a", "b") is False


# ---------------------------------------------------------------------------
# entscheide() — vollständige Mutationsprobe am (dreiwertigen) Automaten.
# Kein Probe-Modus, kein Self-Merge-Zweig mehr — jede verbleibende Kombi-
# nation einzeln, damit eine vertauschte Bedingung sofort auffällt.
# ---------------------------------------------------------------------------
def _fund(rote_linie_pfad: bool) -> pw.Fund:
    datei = "config.py" if rote_linie_pfad else "tests/x.py"
    return pw.Fund(klasse=pw.KLASSE_VERALTETE_DOKU, datei=datei, zeile=1,
                    beschreibung="egal")


def test_entscheide_rote_linie_geht_vor_allem_anderen():
    fund = _fund(rote_linie_pfad=True)
    e = fx.entscheide(fund, fix_inhalt="x", fix_verifiziert=True,
                       guardian_urteil="ok")
    assert e.status == fx.STATUS_ROTE_LINIE


def test_entscheide_rote_linie_auch_bei_fehlendem_fix():
    fund = _fund(rote_linie_pfad=True)
    e = fx.entscheide(fund, fix_inhalt=None, fix_verifiziert=False)
    assert e.status == fx.STATUS_ROTE_LINIE


def test_entscheide_kein_fix_inhalt():
    fund = _fund(rote_linie_pfad=False)
    e = fx.entscheide(fund, fix_inhalt=None, fix_verifiziert=False)
    assert e.status == fx.STATUS_KEIN_FIX_MOEGLICH


def test_entscheide_fix_vorhanden_aber_nicht_verifiziert():
    fund = _fund(rote_linie_pfad=False)
    e = fx.entscheide(fund, fix_inhalt="x", fix_verifiziert=False,
                       guardian_urteil="ok")
    assert e.status == fx.STATUS_KEIN_FIX_MOEGLICH


def test_entscheide_verifizierter_fix_wartet_immer_auf_easy_bei_guardian_ok():
    fund = _fund(rote_linie_pfad=False)
    e = fx.entscheide(fund, fix_inhalt="x", fix_verifiziert=True,
                       guardian_urteil="ok", guardian_begruendung="passt")
    assert e.status == fx.STATUS_WARTET_AUF_EASY
    assert e.neuer_inhalt == "x"
    assert e.guardian_urteil == "ok"


def test_entscheide_verifizierter_fix_wartet_auch_bei_guardian_blocker():
    """Kernpunkt der Überarbeitung: Guardians Urteil ändert NICHTS mehr am
    Status — es gibt keinen Self-Merge, den 'blocker' verhindern müsste.
    Ein 'blocker' landet trotzdem als Draft-PR, nur mit der Guardian-
    Begründung sichtbar im PR-Text für Easys Review."""
    fund = _fund(rote_linie_pfad=False)
    e = fx.entscheide(fund, fix_inhalt="x", fix_verifiziert=True,
                       guardian_urteil="blocker", guardian_begruendung="riskant")
    assert e.status == fx.STATUS_WARTET_AUF_EASY
    assert e.guardian_urteil == "blocker"
    assert e.guardian_begruendung == "riskant"


def test_entscheide_verifizierter_fix_wartet_auch_ohne_guardian_urteil():
    """API-/Parse-Fehler (None) darf NICHT dazu führen, dass der Fund
    verschwindet oder übersprungen wird — er landet trotzdem als Draft-PR,
    nur ohne Guardian-Text (im PR-Body als 'nicht verfügbar' markiert)."""
    fund = _fund(rote_linie_pfad=False)
    e = fx.entscheide(fund, fix_inhalt="x", fix_verifiziert=True,
                       guardian_urteil=None)
    assert e.status == fx.STATUS_WARTET_AUF_EASY
    assert e.guardian_urteil is None


def test_entscheide_es_gibt_keinen_auto_gemergt_zustand_mehr():
    """Regressionstest gegen die alte API: die Konstante darf nicht mehr
    existieren (Auftrags-Grenze: Self-Merge-Ausführung vollständig
    entfernt, nicht nur unerreichbar gemacht)."""
    assert not hasattr(fx, "STATUS_AUTO_GEMERGT")
    assert not hasattr(fx, "STATUS_PROBE_MODUS")
    assert not hasattr(fx, "STATUS_GUARDIAN_BLOCKIERT")
    assert not hasattr(fx, "SELF_MERGE_PROBE_ENDS")
    assert not hasattr(fx, "probe_modus_aktiv")


# ---------------------------------------------------------------------------
# Guardian-API-Aufruf — Fake statt Netz (Muster: agent_comment/notify)
# ---------------------------------------------------------------------------
def test_guardian_aufruf_ok():
    def fake_post(url, payload, headers, timeout):
        return {"content": [{"type": "text",
                              "text": '{"urteil": "ok", "begruendung": "passt"}'}]}
    ergebnis = fx.rufe_guardian_via_api("diff", "beschreibung", "key",
                                         post=fake_post)
    assert ergebnis == {"urteil": "ok", "begruendung": "passt"}


def test_guardian_aufruf_ohne_key_gibt_none():
    assert fx.rufe_guardian_via_api("diff", "b", "", post=lambda *a: {}) is None


def test_guardian_aufruf_bei_api_fehler_none():
    def fake_post(*a):
        raise RuntimeError("netz kaputt")
    assert fx.rufe_guardian_via_api("diff", "b", "key", post=fake_post) is None


def test_guardian_aufruf_bei_unparsebarer_antwort_none():
    def fake_post(*a):
        return {"content": [{"type": "text", "text": "kein json"}]}
    assert fx.rufe_guardian_via_api("diff", "b", "key", post=fake_post) is None


def test_guardian_aufruf_lehnt_unbekanntes_urteil_ab():
    def fake_post(*a):
        return {"content": [{"type": "text",
                              "text": '{"urteil": "vielleicht", "begruendung": "x"}'}]}
    assert fx.rufe_guardian_via_api("diff", "b", "key", post=fake_post) is None


# ---------------------------------------------------------------------------
# Orchestrierung — verarbeite_funde() mit gefakten Guardian-/PR-Aufrufen.
# ---------------------------------------------------------------------------
def test_verarbeite_funde_rote_linie_ohne_fix_versuch():
    fund = pw.Fund(klasse=pw.KLASSE_VERALTETE_DOKU, datei="config.py",
                    zeile=1, beschreibung="egal")
    aufgerufen = []

    def lies_datei(pfad):
        aufgerufen.append(pfad)
        return "inhalt"

    ergebnisse = fx.verarbeite_funde([fund], lies_datei, "key")
    assert ergebnisse[0].status == fx.STATUS_ROTE_LINIE
    assert aufgerufen == []  # Datei wird für rote-Linie-Funde nie gelesen


def test_verarbeite_funde_erfolgreicher_fix_erstellt_draft_pr():
    inhalt = "# diag.alt\nlag = d.get('neu')\n"
    fund = pw.erkenne_veraltete_feldreferenz(inhalt, "tests/x.py")[0]
    pr_aufrufe = []

    ergebnisse = fx.verarbeite_funde(
        [fund], lambda pfad: inhalt, "key",
        guardian_aufruf=lambda *a: {"urteil": "ok", "begruendung": "ok"},
        pr_aufruf=pr_aufrufe.append,
    )
    assert ergebnisse[0].status == fx.STATUS_WARTET_AUF_EASY
    assert len(pr_aufrufe) == 1
    assert pr_aufrufe[0].neuer_inhalt is not None


def test_verarbeite_funde_erstellt_draft_pr_auch_bei_guardian_blocker():
    inhalt = "# diag.alt\nlag = d.get('neu')\n"
    fund = pw.erkenne_veraltete_feldreferenz(inhalt, "tests/x.py")[0]
    pr_aufrufe = []

    ergebnisse = fx.verarbeite_funde(
        [fund], lambda pfad: inhalt, "key",
        guardian_aufruf=lambda *a: {"urteil": "blocker", "begruendung": "nein"},
        pr_aufruf=pr_aufrufe.append,
    )
    assert ergebnisse[0].status == fx.STATUS_WARTET_AUF_EASY
    assert len(pr_aufrufe) == 1


def test_verarbeite_funde_respektiert_max_fixes_limit():
    inhalt = "# diag.alt\nlag = d.get('neu')\n"
    funde = [pw.erkenne_veraltete_feldreferenz(inhalt, f"tests/x{i}.py")[0]
             for i in range(5)]
    pr_aufrufe = []

    ergebnisse = fx.verarbeite_funde(
        funde, lambda pfad: inhalt, "key",
        guardian_aufruf=lambda *a: {"urteil": "ok", "begruendung": "ok"},
        pr_aufruf=pr_aufrufe.append, max_fixes=2,
    )
    assert len(pr_aufrufe) == 2
    # Die übrigen 3 wurden in diesem Lauf nicht bearbeitet -> nicht in
    # ergebnisse, bleiben für den nächsten Lauf liegen (kein Fund verloren,
    # nur verschoben — siehe verarbeite_funde-Docstring).
    assert len(ergebnisse) == 2


def test_verarbeite_funde_kein_fix_moeglich_ruft_pr_nicht_auf():
    fund = pw.Fund(klasse=pw.KLASSE_TESTDATEN_DRIFT, datei="tests/x.py",
                    zeile=1, beschreibung="egal")
    pr_aufrufe = []
    ergebnisse = fx.verarbeite_funde(
        [fund], lambda pfad: "irgendwas\n", "key",
        pr_aufruf=pr_aufrufe.append,
    )
    assert ergebnisse[0].status == fx.STATUS_KEIN_FIX_MOEGLICH
    assert pr_aufrufe == []


def test_verarbeite_funde_unlesbare_datei_wird_wie_kein_fix_behandelt():
    fund = pw.Fund(klasse=pw.KLASSE_VERALTETE_DOKU, datei="tests/weg.py",
                    zeile=1, beschreibung="egal")

    def lies_datei(pfad):
        raise FileNotFoundError(pfad)

    ergebnisse = fx.verarbeite_funde([fund], lies_datei, "key")
    assert ergebnisse[0].status == fx.STATUS_KEIN_FIX_MOEGLICH


# ---------------------------------------------------------------------------
# Berichte
# ---------------------------------------------------------------------------
def test_phase2_bericht_leer_ohne_ergebnisse():
    assert fx.phase2_bericht([]) == ""


def test_phase2_bericht_zaehlt_kategorien():
    fund = pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei="tests/x.py", zeile=1,
                    beschreibung="B")
    ergebnisse = [
        fx.FixEntscheidung(fund, fx.STATUS_WARTET_AUF_EASY, "x",
                            neuer_inhalt="y", guardian_urteil="ok"),
        fx.FixEntscheidung(fund, fx.STATUS_KEIN_FIX_MOEGLICH, "x"),
    ]
    text = fx.phase2_bericht(ergebnisse)
    assert "1 Fix-Draft-PR(s) erstellt" in text
    assert "KEIN Self-Merge" in text
    assert "1 ohne sauber beweisbaren" in text
    assert "[wartet-auf-easy]" in text
    assert "[kein-fix]" in text
    assert "gemergt" not in text.lower()


def test_phase2_bericht_zeigt_guardian_urteil_wenn_vorhanden():
    fund = pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei="tests/x.py", zeile=1,
                    beschreibung="B")
    e = fx.FixEntscheidung(fund, fx.STATUS_WARTET_AUF_EASY, "x",
                            neuer_inhalt="y", guardian_urteil="nits")
    text = fx.phase2_bericht([e])
    assert "[Guardian: nits]" in text


def test_gesamtbericht_kombiniert_phase1_und_phase2():
    funde = [pw.Fund(klasse=pw.KLASSE_KEY_EXPOSURE, datei="tests/x.py",
                      zeile=1, beschreibung="B")]
    ergebnisse = [fx.FixEntscheidung(funde[0], fx.STATUS_ROTE_LINIE, "x")]
    text = fx.gesamtbericht(funde, ergebnisse)
    assert "proactive-watcher" in text
    assert "proactive-fixer" in text


# ---------------------------------------------------------------------------
# Integrations-Rauchtest gegen den echten Baum — informativ, keine Zahlen-
# Assertion (dieselbe Ironie-Vermeidung wie in test_proactive_watcher.py).
# ---------------------------------------------------------------------------
def test_verarbeite_funde_laeuft_ohne_fehler_gegen_den_echten_baum():
    funde = pw.scan_repo(ROOT)

    def lies_datei(pfad):
        return (ROOT / pfad).read_text(encoding="utf-8")

    ergebnisse = fx.verarbeite_funde(
        funde, lies_datei, "",
        guardian_aufruf=lambda *a: None,  # kein Netz im Test
    )
    for e in ergebnisse:
        assert e.status in (fx.STATUS_ROTE_LINIE, fx.STATUS_KEIN_FIX_MOEGLICH,
                             fx.STATUS_WARTET_AUF_EASY)
