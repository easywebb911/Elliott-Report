"""``notify.py`` muss auch dann funktionieren, wenn es SELBST das Skript ist.

Warum es diese Datei gibt (Befund 01.08.2026): ``config.py`` liegt im
Repo-ROOT, ``notify.py`` legte aber nur ``REPO_ROOT/"scripts"`` auf
``sys.path``. Beim Start als Skript (``python scripts/notify.py --mode daily``)
setzt Python ``sys.path[0]`` auf das SKRIPT-Verzeichnis, nicht auf das
Arbeitsverzeichnis — der Repo-Root stand also nirgends auf dem Pfad.
``import config`` scheiterte, und weil ``forward_collection`` seinerseits
``config`` importiert, scheiterte auch der. Beide Fehler sind in ``try/except``
gekapselt: es war STILL. ``_evaluable_count`` lieferte dauerhaft 0, der
Meilenstein-Push bei n>=EVAL_MIN_N konnte NIE feuern — dieselbe Klasse wie der
tote Score-Alarm vor #66.

Die Tests hier starten ``notify.py`` deshalb als ECHTEN SUBPROZESS. Ein
``import notify`` in pytest würde den Fehler garantiert verfehlen: pytest hat
den Repo-Root längst auf dem Pfad, und genau diese Bequemlichkeit hat den
Defekt acht Tage lang verdeckt.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import forward_collection as fc  # noqa: E402
import notify  # noqa: E402

NOTIFY = ROOT / "scripts/notify.py"
FEHLZEILE = "forward_collection nicht verfügbar"


def _starte(*args: str) -> subprocess.CompletedProcess:
    """``notify.py`` als Skript — ohne NTFY_TOPIC, also garantiert stumm.

    Ohne Topic ist jeder Sendepfad ein no-op (``send_ntfy`` steigt vorher aus).
    Der Lauf ist damit nebenwirkungsfrei; die einzige Datei, die notify je
    schreibt, ist der Meilenstein-Marker — und der bleibt aus, solange die
    Schwelle nicht erreicht ist (eigener Test weiter unten).
    """
    env = dict(os.environ)
    env.pop("NTFY_TOPIC", None)
    env.pop("PYTHONPATH", None)      # nichts von außen unterschieben
    return subprocess.run([sys.executable, str(NOTIFY), *args],
                          cwd=tempdir_neutral(), env=env,
                          capture_output=True, text=True, timeout=60)


def tempdir_neutral() -> str:
    """Bewusst NICHT das Repo-Root als Arbeitsverzeichnis.

    Sonst läge der Repo-Root über ``''``/cwd ohnehin auf dem Pfad und der Test
    wäre blind für genau den Fehler, den er sucht. notify löst alle Pfade über
    ``REPO_ROOT`` auf, ist also nicht auf das Arbeitsverzeichnis angewiesen.
    """
    return str(Path(sys.prefix))


# ---------------------------------------------------------------------------
# 1) Der Skript-Start selbst
# ---------------------------------------------------------------------------
def test_notify_als_skript_findet_forward_collection():
    """Der Kernbeweis: als Skript gestartet, zählt notify ECHT statt still 0."""
    p = _starte("--mode", "daily")
    assert p.returncode == 0, p.stderr
    ausgabe = p.stdout + p.stderr
    assert FEHLZEILE not in ausgabe, (
        f"forward_collection ist beim Skript-Start immer noch unerreichbar:\n"
        f"{ausgabe}")
    # ... und die Zählung nennt die ECHTE Zahl, nicht den Rückfall.
    assert f"Meilenstein: 0/{fc.EVAL_MIN_N} auswertbar" in ausgabe, ausgabe


@pytest.mark.parametrize("modus", ["daily", "selftest", "staleness"])
def test_alle_drei_skript_modi_starten_ohne_stille_fehlstelle(modus):
    """Alle drei Einstiege aus den Workflows (daily.yml, staleness_check.yml)."""
    p = _starte("--mode", modus)
    assert p.returncode == 0, p.stderr
    assert FEHLZEILE not in (p.stdout + p.stderr)


def test_der_ALTE_pfad_aufbau_wuerde_wirklich_scheitern():
    """Negativ-Kontrolle: ohne den Repo-Root auf dem Pfad ist der Import tot.

    Ohne diesen Test bewiese der obige nur, dass es GERADE geht — nicht, dass
    er den Defekt bemerkt hätte. Hier wird die alte Lage exakt nachgestellt:
    ``sys.path[0]`` ist das Skript-Verzeichnis, sonst nichts Projektbezogenes.
    """
    code = (
        "import sys, os, json\n"
        "sys.path.pop(0)\n"                                  # '' (cwd) weg
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r})\n"    # nur scripts/
        "ergebnis = {}\n"
        "for name in ('config', 'forward_collection', 'market_calendar'):\n"
        "    try:\n"
        "        __import__(name); ergebnis[name] = 'ok'\n"
        "    except Exception as e:\n"
        "        ergebnis[name] = type(e).__name__\n"
        "print(json.dumps(ergebnis))\n"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    p = subprocess.run([sys.executable, "-c", code], cwd=tempdir_neutral(),
                       env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    ergebnis = json.loads(p.stdout)
    assert ergebnis["config"] == "ModuleNotFoundError"
    assert ergebnis["forward_collection"] == "ModuleNotFoundError"
    # market_calendar liegt in scripts/ und gelang schon immer — das ist der
    # Grund, warum der Staleness-Modus nie auffiel.
    assert ergebnis["market_calendar"] == "ok"


def test_config_liegt_im_repo_root_nicht_in_scripts():
    """Die strukturelle Tatsache hinter dem Defekt. Zieht config.py je um,
    wird dieser Test rot und der Kommentar in notify.py ist fällig."""
    assert (ROOT / "config.py").is_file()
    assert not (ROOT / "scripts/config.py").exists()


def test_notify_legt_BEIDE_verzeichnisse_auf_den_pfad():
    quelle = (ROOT / "scripts/notify.py").read_text(encoding="utf-8")
    assert 'str(REPO_ROOT), str(REPO_ROOT / "scripts")' in quelle, \
        "der Repo-Root ist wieder aus dem sys.path-Aufbau verschwunden"


# ---------------------------------------------------------------------------
# 2) Die stille Fehlstelle ist nicht mehr still
# ---------------------------------------------------------------------------
def test_die_fehlzeile_nennt_jetzt_den_grund(monkeypatch, capsys):
    monkeypatch.setattr(notify, "_fc", None)
    monkeypatch.setattr(notify, "_IMPORT_FEHLER",
                        {"forward_collection": "ModuleNotFoundError: no config"})
    assert notify._evaluable_count({"records": [{"matured": True}]}) == 0
    text = capsys.readouterr().out
    assert FEHLZEILE in text
    assert "ModuleNotFoundError: no config" in text, \
        "der Grund fehlt — genau das machte den Defekt unsichtbar"


def test_die_fehlzeile_bleibt_lesbar_wenn_kein_grund_festgehalten_ist():
    """Fail-soft heißt auch: der Logger darf nie am fehlenden Grund scheitern."""
    import io
    import contextlib
    puffer = io.StringIO()
    alt_fc, alt_err = notify._fc, notify._IMPORT_FEHLER
    try:
        notify._fc, notify._IMPORT_FEHLER = None, {}
        with contextlib.redirect_stdout(puffer):
            assert notify._evaluable_count({"records": []}) == 0
    finally:
        notify._fc, notify._IMPORT_FEHLER = alt_fc, alt_err
    # Leere records -> frueher Ausstieg, keine Zeile. Jetzt mit Inhalt:
    puffer = io.StringIO()
    try:
        notify._fc, notify._IMPORT_FEHLER = None, {}
        with contextlib.redirect_stdout(puffer):
            notify._evaluable_count({"records": [{"matured": True}]})
    finally:
        notify._fc, notify._IMPORT_FEHLER = alt_fc, alt_err
    assert "Grund nicht festgehalten" in puffer.getvalue()


# ---------------------------------------------------------------------------
# 3) SICHERHEITS-PRÜFUNG: der Fix löst den Meilenstein-Push NICHT aus
# ---------------------------------------------------------------------------
def test_der_meilenstein_push_geht_durch_den_fix_NICHT_los():
    """Nach dem Fix zählt notify echte Werte statt fehlergetriebener 0.

    Genau deshalb muss belegt sein, dass die echte Zahl die Schwelle NICHT
    erreicht — sonst hätte der Fix beim nächsten Lauf einen einmaligen,
    unumkehrbaren Push ausgelöst. Am Stand vom 01.08.2026: 50 gesammelt,
    0 gereift, 0 auswertbar; Schwelle 100.
    """
    coll = json.loads(
        (ROOT / "data/forward_collection.json").read_text(encoding="utf-8"))
    gesammelt, gereift, auswertbar = fc.eval_counts(coll)
    assert gesammelt > 0, "Testvoraussetzung: die Sammlung ist nicht leer"
    assert auswertbar == notify._evaluable_count(coll), \
        "notify zählt anders als forward_collection — genau das soll nicht sein"
    assert auswertbar < fc.EVAL_MIN_N, (
        f"auswertbar={auswertbar} >= {fc.EVAL_MIN_N}: der Meilenstein WÜRDE "
        f"feuern — das ist eine Entscheidung, keine Nebenwirkung eines Fixes")
    assert notify.milestone_reached(auswertbar, marker_exists=False) is False


def test_der_einmal_marker_bleibt_unberuehrt():
    """Weder Fix noch Testlauf legen die Marker-Datei an. Sie ist einmalig und
    damit endgültig — ein versehentliches Anlegen wäre nicht rückholbar."""
    assert not (ROOT / notify.MILESTONE_MARKER).exists(), \
        "der Meilenstein-Marker existiert plötzlich — Meilenstein verbucht?"
    p = _starte("--mode", "daily")
    assert p.returncode == 0
    assert not (ROOT / notify.MILESTONE_MARKER).exists(), \
        "ein Skript-Lauf hat den Einmal-Marker angelegt"


def test_die_schwelle_kommt_aus_forward_collection_nicht_aus_dem_rueckfall():
    """Vorher fiel EVAL_MIN_N auf das Literal 100 zurück, weil `_fc` None war.
    Dass die Zahl zufällig stimmte, war Glück — jetzt ist es die Quelle."""
    assert notify._fc is not None
    assert notify.EVAL_MIN_N == fc.EVAL_MIN_N


# ---------------------------------------------------------------------------
# 4) Der Review-Wecker war MITBETROFFEN — zweiter toter Push im selben Defekt
# ---------------------------------------------------------------------------
def test_der_review_wecker_kennt_sein_datum_wieder():
    """Beim Skript-Start fiel auch ``SCORE_REVIEW_BY`` auf None zurück, weil es
    aus ``config`` kommt — und ``review_due(None, …)`` ist immer False.

    Im Actions-Log vom 31.07.2026 steht deshalb wörtlich
    ``Review-Wecker: review_by=None``, obwohl in config.py ein Datum steht.
    Der Wecker war also genauso tot wie der Meilenstein-Push; das war beim
    ersten Befund noch nicht quantifiziert.
    """
    import config
    assert notify.SCORE_REVIEW_BY == config.SCORE_REVIEW_BY == "2026-12-07"
    assert notify.STATUS_REVIEW_WEEKDAY == config.STATUS_REVIEW_WEEKDAY == 0
    p = _starte("--mode", "daily")
    assert "review_by=None" not in (p.stdout + p.stderr), \
        "der Wecker kennt sein Datum immer noch nicht"
    assert f"review_by={config.SCORE_REVIEW_BY}" in (p.stdout + p.stderr)


def test_der_review_wecker_geht_durch_den_fix_NICHT_sofort_los():
    """Dieselbe Sicherheitsfrage wie beim Meilenstein: der Fix erweckt einen
    Push, der acht Tage lang tot war. Er darf nicht sofort losgehen.

    Von Hand: review_by = 2026-12-07, Drossel-Wochentag = Montag. Fällig ist
    er erst, wenn BEIDES stimmt — Datum überschritten UND Montag. Der 07.12.
    ist selbst ein Montag, aber ``now.date() > due`` ist an dem Tag noch False;
    der erste wirkliche Auslöser ist Montag, der **14.12.2026**.
    """
    import datetime as dt
    heute = dt.datetime(2026, 8, 1, 22, 45, tzinfo=dt.timezone.utc)
    assert notify.review_due(notify.SCORE_REVIEW_BY, heute) is False
    for tag, soll in (("2026-12-07", False),   # Montag, aber noch nicht drüber
                      ("2026-12-08", False),   # drüber, aber Dienstag
                      ("2026-12-13", False),   # drüber, aber Sonntag
                      ("2026-12-14", True)):   # Montag UND drüber -> fällig
        jetzt = dt.datetime.fromisoformat(tag + "T22:45:00+00:00")
        assert notify.review_due(notify.SCORE_REVIEW_BY, jetzt) is soll, tag
