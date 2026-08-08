"""Die stille-Ausfälle-Klasse: EIN Pfad-Baustein und LAUTE Rückfälle.

WORUM ES GEHT (Befund #69, 01.08.2026 — und die Code-Inventur vom 08.08.2026):
``config.py`` liegt im **Repo-Root**, die Module in ``scripts/``. Beim Start
**als Skript** — genau so ruft ``daily.yml`` sie auf — ist ``sys.path[0]`` das
**Skript-Verzeichnis**. Wer den Repo-Root nicht selbst auf den Pfad legt, findet
``config`` nicht.

Das allein wäre laut. Tödlich wird es durch die zweite Hälfte: die betroffenen
Module fangen den Import-Fehler ab und fallen auf ``getattr(config, …,
<Literal>)`` zurück — und diese Literale stimmen mit den echten config-Werten
überein. Der Ausfall sieht damit **exakt wie Normalbetrieb** aus. In #69 hat das
den Meilenstein-Push und den Review-Wecker acht Tage lang totgestellt.

Diese Datei nagelt beide Hälften fest:

  A) **Ein** Pfad-Aufbau statt drei Kopien (``scripts/repo_path.py``) — geprüft
     an der WIRKUNG im Kindprozess, nicht am Quelltext.
  B) Ein Rückfall darf nicht mehr **stumm** sein — ``health_check`` und
     ``notify`` melden ihn laut, und der Review-Wecker unterscheidet endlich
     „nicht auffindbar" (Fehler) von „bewusst None" (Abschaltung).

Die entscheidenden Tests laufen als **Kindprozess mit neutralem
Arbeitsverzeichnis** und stellen die Skript-Start-Lage exakt nach. Ein
``import`` in pytest würde den Defekt garantiert verfehlen: pytest hat den
Repo-Root längst auf dem Pfad — genau diese Bequemlichkeit hat #69 acht Tage
lang verdeckt.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import importlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import health_check as hc  # noqa: E402
import notify  # noqa: E402
import repo_path  # noqa: E402


def _neutrales_arbeitsverzeichnis() -> str:
    """Bewusst NICHT das Repo-Root — und bewusst kein tmp_path.

    Für den ``python -c``-Start IST ``sys.path[0]`` das Arbeitsverzeichnis
    (``''``). Stünde der Test im Repo-Root, fände er ``config`` aus Versehen und
    wäre blind für genau den Fehler, den er nachstellen soll.
    """
    return str(Path(sys.prefix))


def _kindprozess(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)      # nichts von außen unterschieben
    env.pop("NTFY_TOPIC", None)      # ohne Topic ist jeder Sendepfad ein no-op
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, "-c", code],
                          cwd=_neutrales_arbeitsverzeichnis(), env=env,
                          capture_output=True, text=True, timeout=90)


#: Ausgangslage wie beim echten Skript-Start: das Arbeitsverzeichnis (``''``)
#: fliegt vom Pfad, ``scripts/`` kommt davor — sonst nichts Projektbezogenes.
SKRIPT_LAGE = (
    "import sys, json\n"
    "sys.path.pop(0)\n"
    f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
)


# ═══════════════════════════════════════════════════════════════════════════
# A) EIN Pfad-Baustein — geprüft an der Wirkung
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("modul", ["health_check", "notify", "elliott_pipeline"])
def test_der_skript_start_findet_config(modul):
    """Der Kernbeweis, für jeden Einstieg einzeln: wie ein Mensch aufgerufen.

    ``elliott_pipeline`` ist hier bewusst mitgeprüft, obwohl es seinen Pfad
    (noch) selbst aufbaut: der Test misst die WIRKUNG, nicht die Bauweise. Er
    bleibt damit grün, egal ob dort die eigene Kopie steht oder der gemeinsame
    Baustein — und er würde rot, wenn beim Umbau der Root verloren ginge.
    """
    p = _kindprozess(
        SKRIPT_LAGE
        + f"import {modul} as m\n"
        + "import config\n"
        + f"print(json.dumps({{'root': {str(ROOT)!r} in sys.path,"
          f" 'scripts': {str(SCRIPTS)!r} in sys.path,"
          " 'config_da': getattr(m, 'config', config) is not None}))\n"
    )
    assert p.returncode == 0, p.stderr
    lage = json.loads(p.stdout.strip().splitlines()[-1])
    assert lage["root"], (
        f"{modul} legt den Repo-Root nicht auf sys.path — `import config` "
        f"stirbt beim Skript-Start (Defekt #69)")
    assert lage["scripts"], f"{modul}: scripts/ fehlt auf dem Pfad"
    assert lage["config_da"], f"{modul}: config ist beim Skript-Start None"


def test_negativ_kontrolle_ohne_den_baustein_ist_config_wirklich_weg():
    """Ohne diese Kontrolle bewiese der Test oben nur, dass es GERADE geht.

    Hier wird die alte Lage nachgestellt — ``scripts/`` auf dem Pfad, sonst
    nichts. ``config`` liegt im Root und ist damit unerreichbar.
    """
    p = _kindprozess(
        SKRIPT_LAGE
        + "ergebnis = {}\n"
        "for name in ('config', 'forward_collection', 'market_calendar'):\n"
        "    try:\n"
        "        __import__(name); ergebnis[name] = 'ok'\n"
        "    except Exception as e:\n"
        "        ergebnis[name] = type(e).__name__\n"
        "print(json.dumps(ergebnis))\n"
    )
    assert p.returncode == 0, p.stderr
    ergebnis = json.loads(p.stdout.strip().splitlines()[-1])
    assert ergebnis["config"] == "ModuleNotFoundError"
    assert ergebnis["forward_collection"] == "ModuleNotFoundError"
    # market_calendar liegt in scripts/ und gelang schon immer — deshalb fiel
    # der Staleness-Modus in #69 nie auf.
    assert ergebnis["market_calendar"] == "ok"


def test_der_baustein_selbst_hat_kein_bootstrap_problem():
    """``repo_path`` liegt neben seinen Aufrufern und ist deshalb immer da.

    Wäre das nicht so, verschöbe der gemeinsame Baustein das Problem nur eine
    Ebene tiefer. Geprüft mit NUR ``scripts/`` auf dem Pfad — der ungünstigsten
    Lage, die real vorkommt.
    """
    p = _kindprozess(
        SKRIPT_LAGE
        + "import repo_path\n"
          "import config\n"
          "print(json.dumps({'root': repo_path.REPO_ROOT.as_posix(),"
          " 'config': bool(config.SCORE_REVIEW_BY is not None"
          " or config.SCORE_REVIEW_BY is None)}))\n"
    )
    assert p.returncode == 0, p.stderr
    lage = json.loads(p.stdout.strip().splitlines()[-1])
    assert lage["root"] == ROOT.as_posix()
    assert lage["config"] is True


def test_ensure_ist_idempotent_und_legt_beide_verzeichnisse():
    """Mehrfacher Aufruf darf den Pfad nicht mit Dubletten zumüllen.

    Wichtig, weil der Baustein von mehreren Modulen importiert wird und
    ``ensure()`` zusätzlich von Hand aufrufbar ist.
    """
    vorher = list(sys.path)
    try:
        # Gemessen wird die WIRKUNG von ensure(), nicht der Zustand davor:
        # conftest.py und dieses Testmodul haben beide Pfade längst eingefügt,
        # eine absolute Zählung prüfte also deren Aufräumverhalten, nicht dieses.
        sys.path[:] = [str(repo_path.REPO_ROOT), str(repo_path.SCRIPTS)]
        repo_path.ensure()
        repo_path.ensure()
        assert sys.path.count(str(repo_path.REPO_ROOT)) == 1
        assert sys.path.count(str(repo_path.SCRIPTS)) == 1
    finally:
        sys.path[:] = vorher
    assert repo_path.REPO_ROOT == ROOT
    assert repo_path.SCRIPTS == SCRIPTS


def test_ensure_stellt_beide_verzeichnisse_wieder_her():
    """Der Wirkungsbeweis der Funktion selbst — an einem leeren Pfad."""
    vorher = list(sys.path)
    try:
        sys.path[:] = [p for p in sys.path
                       if p not in (str(ROOT), str(SCRIPTS))]
        assert str(ROOT) not in sys.path and str(SCRIPTS) not in sys.path
        repo_path.ensure()
        assert str(ROOT) in sys.path and str(SCRIPTS) in sys.path
    finally:
        sys.path[:] = vorher


def test_es_gibt_nur_noch_EINE_pfad_stelle_in_den_beiden_modulen():
    """Kein eigener ``sys.path``-Aufbau mehr in ``health_check``/``notify``.

    Das ist bewusst eine Quelltext-Prüfung: geprüft wird nicht ein Verhalten,
    sondern die Zusage „EINE Stelle statt Kopien". Drei gleichlautende Blöcke
    sind drei Gelegenheiten zum Auseinanderlaufen, und ein wiedereingefügter
    Block wäre an der Wirkung NICHT zu erkennen (er täte ja dasselbe).

    ``elliott_pipeline.py`` ist hier bewusst NICHT aufgeführt: sein Umbau lag
    außerhalb des Auftrags-Rahmens. Der Wirkungs-Test oben deckt es trotzdem ab.
    """
    for name in ("health_check.py", "notify.py"):
        quelle = (SCRIPTS / name).read_text(encoding="utf-8")
        code = "\n".join(z for z in quelle.splitlines()
                         if not z.lstrip().startswith("#"))
        assert "sys.path.insert" not in code, (
            f"{name} baut den Pfad wieder selbst auf — der gemeinsame Baustein "
            f"ist damit umgangen")
        assert "import repo_path" in code, f"{name} nutzt den Baustein nicht"


def test_die_liste_der_verbliebenen_eigenkopien_stimmt():
    """``repo_path.py`` nennt die Module mit Eigenkopie NAMENTLICH — und die
    Liste muss stimmen, sonst ist sie schlimmer als keine.

    Eine Aufzählung im Kommentar altert lautlos: wer die achte Kopie anlegt oder
    die siebte umbaut, merkt nichts. Dieser Test koppelt die Zusage an die
    Wirklichkeit — er wird rot, wenn ein Modul umgebaut wird, OHNE die Liste
    nachzuziehen. Das ist der Zweck, kein Nebeneffekt.
    """
    doku = (SCRIPTS / "repo_path.py").read_text(encoding="utf-8")
    block = re.search(r"EIGENKOPIEN-ANFANG\n(.*?)EIGENKOPIEN-ENDE", doku,
                      re.S)
    assert block, "der maschinell geprüfte Listen-Block fehlt in repo_path.py"
    genannt = set(re.findall(r"\b([a-z_]+\.py)\b", block.group(1)))
    assert genannt, "der Listen-Block ist leer"

    tatsaechlich = set()
    for datei in sorted(SCRIPTS.glob("*.py")):
        if datei.name == "repo_path.py":
            continue
        code = "\n".join(z for z in datei.read_text(encoding="utf-8").splitlines()
                         if not z.lstrip().startswith("#"))
        if "sys.path.insert" in code:
            tatsaechlich.add(datei.name)

    assert genannt == tatsaechlich, (
        f"die Liste in repo_path.py ist nicht mehr wahr — "
        f"nur dort genannt: {sorted(genannt - tatsaechlich)}, "
        f"nur tatsächlich: {sorted(tatsaechlich - genannt)}")


# ═══════════════════════════════════════════════════════════════════════════
# B1) health_check: die 13 Rückfälle sind nicht mehr stumm
# ═══════════════════════════════════════════════════════════════════════════
def test_health_warnung_schweigt_im_normalbetrieb(capsys):
    """Ein gesunder Lauf bleibt still — sonst stumpft die Warnung ab."""
    assert hc.warne_bei_import_fehler() is False
    assert capsys.readouterr().out == ""


def test_health_warnung_nennt_den_grund(monkeypatch, capsys):
    monkeypatch.setattr(hc, "_IMPORT_FEHLER",
                        {"config": "ModuleNotFoundError: No module named 'config'"})
    assert hc.warne_bei_import_fehler() is True
    text = capsys.readouterr().out
    assert "WARNUNG" in text
    assert "No module named 'config'" in text, \
        "der Grund fehlt — genau das machte den Defekt unsichtbar"


class _Blockiert:
    """Meta-Path-Finder, der genau EIN Modul unimportierbar macht."""

    def __init__(self, name: str):
        self.name = name

    def find_spec(self, name, path=None, target=None):
        if name == self.name:
            raise ImportError(f"Testfall: {self.name} nicht importierbar")
        return None


def test_der_ECHTE_except_zweig_in_health_check_haelt_den_grund_fest():
    """Der ``except``-Zweig wird WIRKLICH ausgelöst, nicht nur nachgestellt.

    Lesson aus #69: die Grund-Tests setzten ``_IMPORT_FEHLER`` direkt; die
    Zuweisung im ``except`` selbst war dadurch ungeschützt und ließ sich durch
    ``pass`` ersetzen, ohne dass ein Test rot wurde.
    """
    blocker = _Blockiert("config")
    gemerkt = {n: sys.modules.pop(n, None)
               for n in ("config", "forward_collection", "notify",
                         "health_check")}
    sys.meta_path.insert(0, blocker)
    try:
        neu = importlib.import_module("health_check")
        assert neu.config is None, "der Blocker hat nicht gegriffen"
        assert "config" in neu._IMPORT_FEHLER, \
            "der echte except-Zweig hält den Grund NICHT fest"
        assert "Testfall: config nicht importierbar" in neu._IMPORT_FEHLER["config"]
        # ... und die Rückfall-Literale sind wirklich im Einsatz.
        assert neu.MIN_CANDIDATES == 3
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            assert neu.warne_bei_import_fehler() is True
        assert "Testfall: config nicht importierbar" in puffer.getvalue()
    finally:
        sys.meta_path.remove(blocker)
        for n, mod in gemerkt.items():
            if mod is not None:
                sys.modules[n] = mod
        importlib.reload(hc)
    # Sauber wiederhergestellt — sonst verseucht dieser Test die ganze Suite.
    assert hc.config is not None and hc._IMPORT_FEHLER == {}


def test_der_lauf_meldet_den_ausfall_ZUERST(tmp_path, monkeypatch):
    """``run()`` ruft die Warnung wirklich auf — und zwar als erste Handlung.

    Ohne diesen Test wäre die laute Meldung zwar vorhanden, aber im echten
    Durchlauf nie ausgelöst: genau die Lücke, die #69 ausgemacht hat.
    """
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(hc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hc, "_IMPORT_FEHLER", {"config": "Testfall: kaputt"})
    monkeypatch.setattr(notify, "_post",
                        lambda url, data, headers, timeout: None)
    reihenfolge = []
    echte_warnung = hc.warne_bei_import_fehler
    monkeypatch.setattr(hc, "warne_bei_import_fehler",
                        lambda: (reihenfolge.append("warnung"),
                                 echte_warnung())[1])
    monkeypatch.setattr(hc, "collect_findings",
                        lambda *a, **k: reihenfolge.append("arbeit") or [])
    now = _dt.datetime(2026, 7, 27, 21, 45, tzinfo=_dt.timezone.utc)
    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer):
        hc.run({"markets": {}}, None, [], None, None, has_agent_key=False,
               topic="", run_date="2026-07-27",
               now_iso="2026-07-27T21:45:00Z", now=now)
    assert reihenfolge[:2] == ["warnung", "arbeit"], \
        f"die Warnung kommt nicht zuerst: {reihenfolge}"
    assert "Testfall: kaputt" in puffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# B2) notify: der Review-Wecker stirbt nicht mehr lautlos
# ═══════════════════════════════════════════════════════════════════════════
MONTAG_UEBERFAELLIG = _dt.datetime(2026, 12, 14, 22, 45, tzinfo=_dt.timezone.utc)


def test_nicht_auffindbar_ist_LAUT(capsys):
    """Der eigentliche B2-Beweis: fehlender Wert → Warnung statt Stille."""
    assert notify.review_due(notify.FEHLT, MONTAG_UEBERFAELLIG) is False
    text = capsys.readouterr().out
    assert "WARNUNG" in text
    assert "SCORE_REVIEW_BY" in text
    assert "nicht auffindbar" in text
    assert "KEINE Abschaltung" in text, \
        "die Meldung muss Fehler von bewusster Abschaltung unterscheiden"


def test_bewusstes_None_bleibt_still(capsys):
    """Die Gegenprobe — sonst wäre die Warnung wertlos.

    ``SCORE_REVIEW_BY = None`` heißt laut Konvention „falsifiziert / menschlich
    abgeschaltet" und ist ein gültiger Zustand. Wer den anmeckert, erzeugt eine
    Dauer-Warnung, die niemand mehr liest.
    """
    assert notify.review_due(None, MONTAG_UEBERFAELLIG) is False
    assert notify.review_due("", MONTAG_UEBERFAELLIG) is False
    assert capsys.readouterr().out == ""


def test_der_sentinel_ist_falsy_und_lesbar():
    """Falsy, damit jeder bestehende ``if not wert``-Pfad unverändert greift;
    lesbar, damit die Logzeile ``review_by=<nicht auffindbar>`` sich selbst
    erklärt statt ``<object object at 0x…>`` zu zeigen."""
    assert bool(notify.FEHLT) is False
    assert repr(notify.FEHLT) == "<nicht auffindbar>"
    assert f"{notify.FEHLT}" == "<nicht auffindbar>"
    assert notify.FEHLT is not None


def test_gueltiges_datum_verhaelt_sich_unveraendert(capsys):
    """B2 ändert NICHTS an der Wecker-Logik selbst (Regel/Drossel/Schwelle)."""
    for tag, soll in (("2026-12-07", False),   # Montag, aber noch nicht drüber
                      ("2026-12-08", False),   # drüber, aber Dienstag
                      ("2026-12-13", False),   # drüber, aber Sonntag
                      ("2026-12-14", True)):   # Montag UND drüber → fällig
        jetzt = _dt.datetime.fromisoformat(tag + "T22:45:00+00:00")
        assert notify.review_due("2026-12-07", jetzt) is soll, tag
    assert notify.review_due("kein-datum", MONTAG_UEBERFAELLIG) is False
    assert capsys.readouterr().out == "", \
        "gültige Werte dürfen keine Warnung erzeugen"


def test_im_normalbetrieb_ist_der_wert_da_und_KEIN_sentinel():
    import config
    assert notify.SCORE_REVIEW_BY == config.SCORE_REVIEW_BY
    assert notify.SCORE_REVIEW_BY is not notify.FEHLT
    assert notify._KONFIG_LUECKEN == [], \
        f"Ersatzwerte im Normalbetrieb in Gebrauch: {notify._KONFIG_LUECKEN}"


def test_bei_kaputtem_config_wird_der_sentinel_wirklich_gesetzt():
    """Der reale Weg zum Sentinel: ``config`` ist nicht importierbar.

    Ohne diesen Test bewiese ``test_nicht_auffindbar_ist_LAUT`` nur, dass die
    Funktion mit ``FEHLT`` umgehen kann — nicht, dass der Wert je so entsteht.
    """
    blocker = _Blockiert("config")
    gemerkt = {n: sys.modules.pop(n, None)
               for n in ("config", "forward_collection")}
    sys.meta_path.insert(0, blocker)
    try:
        neu = importlib.reload(notify)
        assert neu.SCORE_REVIEW_BY is neu.FEHLT
        assert "SCORE_REVIEW_BY" in neu._KONFIG_LUECKEN
        assert "config" in neu._IMPORT_FEHLER
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            assert neu.review_due(neu.SCORE_REVIEW_BY,
                                  MONTAG_UEBERFAELLIG) is False
            neu.warne_bei_import_fehler()
        text = puffer.getvalue()
        assert "Testfall: config nicht importierbar" in text, \
            "die Warnung nennt den GRUND nicht"
        assert "SCORE_REVIEW_BY" in text
    finally:
        sys.meta_path.remove(blocker)
        for n, mod in gemerkt.items():
            if mod is not None:
                sys.modules[n] = mod
        importlib.reload(notify)
    assert notify.config is not None and notify._KONFIG_LUECKEN == []


def test_der_ECHTE_lauf_ist_laut_wenn_config_fehlt():
    """Ende zu Ende im Kindprozess: ``notify --mode daily`` mit totem config.

    Der Ausfall muss im Actions-Log stehen — dort schaut ein Mensch hin, nicht
    in eine pytest-Assertion. Der Rückgabewert bleibt 0: fail-soft bleibt
    fail-soft, nur eben nicht mehr lautlos.
    """
    p = _kindprozess(
        "import sys, json\n"
        f"sys.path.insert(0, {str(SCRIPTS)!r})\n"
        "class B:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'config':\n"
        "            raise ImportError('Testfall: config tot')\n"
        "        return None\n"
        "sys.meta_path.insert(0, B())\n"
        "import notify\n"
        "print('RC=%d' % notify.main(['--mode', 'daily']))\n"
    )
    assert p.returncode == 0, p.stderr
    ausgabe = p.stdout + p.stderr
    assert "RC=0" in ausgabe, "fail-soft gebrochen — der Lauf würde rot"
    assert "WARNUNG" in ausgabe, "der Ausfall bleibt im echten Lauf STUMM"
    assert "Testfall: config tot" in ausgabe, "der Grund fehlt im Log"
    assert "SCORE_REVIEW_BY" in ausgabe, \
        "der tote Review-Wecker wird im echten Lauf nicht benannt"
    # Und der Sammel-Bericht aus main() selbst — NACHGETRAGEN 08.08.2026 nach
    # einer überlebenden Mutationsprobe: `warne_bei_import_fehler()` aus main()
    # zu entfernen ließ die Suite grün, weil `review_due` seine eigene Warnung
    # ausgibt und alle Zusicherungen oben damit schon erfüllt waren. Die beiden
    # Zeilen hier kann NUR main() erzeugen.
    assert "`import forward_collection` ist fehlgeschlagen" in ausgabe, \
        "der mitgerissene forward_collection-Ausfall wird nicht gemeldet"
    assert "Ersatzwerte statt config-Werten in Gebrauch" in ausgabe, \
        "der Sammel-Bericht aus main() fehlt — die Rückfall-Literale laufen " \
        "wieder unbenannt mit"


def test_der_gesunde_lauf_bleibt_ohne_WARNUNG():
    """Gegenprobe zum vorigen Test: kein Fehler → kein Rauschen."""
    p = _kindprozess(SKRIPT_LAGE
                     + "import notify\n"
                       "print('RC=%d' % notify.main(['--mode', 'daily']))\n")
    assert p.returncode == 0, p.stderr
    ausgabe = p.stdout + p.stderr
    assert "RC=0" in ausgabe
    assert "WARNUNG" not in ausgabe, ausgabe
    assert "review_by=<nicht auffindbar>" not in ausgabe
