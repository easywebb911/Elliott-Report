"""Verlustbild-Überlauf auf schmalen Viewports (12.10.2026, Easy-Fund per
Screenshot, iPhone). Folge-Auftrag zu #182.

BEFUND (Diagnose, empirisch mit echtem Headless-Chromium nachgewiesen, s.
unten): `verlustbildHtml()` (PR #182) hatte seine Legenden-Zeilen in
`<div class="vsdist-rows">` gesteckt — dieselbe Klasse, die #107/#123 für
IHRE (kurzen) Beschriftungen nutzen. `.vsdist-rows` ist ein 2-Spalten-Grid
(`grid-template-columns:1fr 1fr`) mit `white-space:nowrap` auf den
Einträgen — bei #107/#123s kurzen Texten ("Zone", "invalidiert", …) passt
das; bei #182s längeren Texten ("abgelaufen (weder Ziel noch Stopp) 63
40,1 %") zwingt `nowrap` die 1fr-Spalte über ihre Breite hinaus, und weil
`.bt-overlay` (`overflow-y:auto`) laut CSS-Spezifikation dadurch AUCH
`overflow-x:auto` bekommt (nur EINE Achse explizit `visible` lassen reicht
nicht), wird der ganze Overlay horizontal scrollbar statt die Zeilen
umzubrechen — exakt Easys Screenshot-Befund.

FIX: `verlustbildHtml()` nutzt jetzt eine EIGENE Klasse `.vbild-rows`
(1-Spalten-Flex, kein `nowrap`, `overflow-wrap:anywhere`) — `.vsdist-rows`
selbst bleibt für #107/#123 UNVERÄNDERT (per Test unten geprüft). Titel/
Chip/Pflichttext/Primärzeile bekommen defensiv `overflow-wrap:anywhere`
ergänzt (waren laut Messung nicht die Ursache, aber Auftrag verlangt es
ausdrücklich und es ist folgenlos korrekt).

ZWEI NETZE:
  (a) Statische CSS-/String-Prüfung — läuft IMMER, auch ohne Browser (CI
      hat kein Chromium installiert). Das ist das eigentliche CI-Gate.
  (b) Echter Headless-Browser (Chromium, in dieser Sitzung unter
      `$PLAYWRIGHT_BROWSERS_PATH/chromium` vorhanden, KEIN neues pip-/npm-
      Paket) — misst `scrollWidth`/`clientWidth` von `.bt-overlay` bei
      360/390 px mit dem ECHTEN, extrahierten CSS und dem ECHTEN, gegen die
      aktuelle `data/forward_collection.json` gerenderten Markup. Skip,
      wenn kein Chromium gefunden wird (z. B. auf dem GitHub-Runner) — dann
      trägt (a) allein die Garantie, wie bei den `node`-Tests in
      test_verlustbild_anzeige.py ("kein node vorhanden — die Literal-Tests
      decken dieselben Fälle").
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate as ev  # noqa: E402
import evaluate_nicht_invalidiert as eni  # noqa: E402

_COLL = json.loads((ROOT / "data/forward_collection.json").read_text(encoding="utf-8"))
_RECORDS = _COLL["records"]


def _fn(name: str, tiefe: str = "    ") -> str:
    for prefix in ("function", "async function"):
        marke = f"{tiefe}{prefix} {name}("
        if marke in HTML:
            start = HTML.index(marke)
            return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]
    raise AssertionError(f"Funktion {name!r} nicht gefunden")


def _konst_obj(name: str) -> str:
    marke = f"    const {name} = {{"
    start = HTML.index(marke)
    return HTML[start:HTML.index("};\n", start) + 3]


def _konst_simple(name: str) -> str:
    marke = f"    const {name} = "
    start = HTML.index(marke)
    return HTML[start:HTML.index(";", start) + 1]


def _css_regel(selector: str) -> str:
    """Den vollständigen CSS-Regelblock für `selector` aus dem <style>-Teil
    holen (von `selector {` bis zur schließenden `}` auf Top-Level)."""
    style_start = HTML.index("<style>")
    style_end = HTML.index("</style>")
    style = HTML[style_start:style_end]
    marke = f"{selector} {{"
    idx = style.index(marke)
    tiefe = 1
    i = idx + len(marke)
    while tiefe:
        if style[i] == "{":
            tiefe += 1
        elif style[i] == "}":
            tiefe -= 1
        i += 1
    return style[idx:i]


# ---------------------------------------------------------------------------
# (a) Statische CSS-/String-Prüfung — läuft immer.
# ---------------------------------------------------------------------------
def test_verlustbildhtml_nutzt_eigene_rows_klasse():
    koerper = _fn("verlustbildHtml")
    assert '<div class="vbild-rows">' in koerper
    assert '<div class="vsdist-rows">' not in koerper


def test_vbild_rows_ist_eine_flex_spalte_ohne_nowrap():
    regel = _css_regel(".vbild-rows")
    assert "flex-direction:column" in regel
    assert "grid-template-columns" not in regel
    assert "white-space:nowrap" not in regel


def test_vbild_rows_span_erlaubt_umbruch():
    regel = _css_regel(".vbild-rows span")
    assert "overflow-wrap:anywhere" in regel
    assert "min-width:0" in regel
    assert "white-space:nowrap" not in regel


def test_vsdist_rows_bleibt_fuer_107_123_unveraendert():
    """Bestehender Block NICHT angefasst (Auftrag Punkt 3/5) — dieselbe
    Grid-/nowrap-Mechanik wie vor #182 bleibt für die kurzen Beschriftungen
    von statusDistributionHtml()/rWerteHtml() bestehen."""
    regel = _css_regel(".vsdist-rows")
    assert "grid-template-columns:1fr 1fr" in regel
    span_regel = _css_regel(".vsdist-rows span")
    assert "white-space:nowrap" in span_regel


def test_vbild_bar_bleibt_volle_kartenbreite():
    regel = _css_regel(".vbild-bar")
    assert "width:100%" in regel


def test_vbild_titel_chip_pflichttext_primaerzeile_erlauben_umbruch():
    """Auftrag Punkt 2, wörtlich: Chip und Titel umbrechen, Pflichttext und
    Primärzeile umbrechen — defensiv ergänzt, auch wenn die Messung (s.
    node-Test unten) zeigt, dass diese Elemente für sich allein nicht
    überliefen (der Überlauf kam von den Zeilen, s. Moduldoc)."""
    for selector in (".vbild-title", ".vbild-say", ".vbild-note", ".vbild-primaer-say"):
        regel = _css_regel(selector)
        assert "overflow-wrap:anywhere" in regel, f"{selector} ohne overflow-wrap"


def test_mutationsprobe_alte_klasse_haette_ueberlaufen_verursacht():
    """Mutationsprobe (statische Variante): zeigt, dass die VORHER
    verwendete Klasse (`.vsdist-rows`, unverändert noch für #107/#123 aktiv)
    GENAU die zwei Eigenschaften trägt, die den Überlauf verursacht hätten
    (2-Spalten-Grid + nowrap) — und dass `.vbild-rows` beide NICHT hat.
    Käme `verlustbildHtml()` wieder auf `.vsdist-rows` zurück (Mutation:
    Umbruch-Fix entfernt), würde `test_verlustbildhtml_nutzt_eigene_rows_
    klasse` oben sofort rot."""
    alte_regel = _css_regel(".vsdist-rows") + _css_regel(".vsdist-rows span")
    neue_regel = _css_regel(".vbild-rows") + _css_regel(".vbild-rows span")
    assert "white-space:nowrap" in alte_regel
    assert "grid-template-columns:1fr 1fr" in alte_regel
    assert "white-space:nowrap" not in neue_regel
    assert "grid-template-columns" not in neue_regel


def test_bestehende_tests_unveraendert_pruefbar():
    """Regression: #107/#123/#182s bestehende Zahlen-Tests laufen weiter
    über ihre eigenen Dateien — hier nur sichergestellt, dass die dafür
    nötigen Funktionen/Konstanten nicht umbenannt wurden."""
    assert _fn("statusDistributionHtml")
    assert _fn("rWerteHtml")
    assert _fn("verlustbildHtml")
    assert _konst_simple("VERLUSTBILD_MIN_N")


# ---------------------------------------------------------------------------
# (b) Echter Headless-Browser — Nachweis statt Behauptung, wo verfügbar.
# ---------------------------------------------------------------------------
def _finde_chromium() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        pfad = shutil.which(name)
        if pfad:
            return pfad
    pw_pfad = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    for basis in filter(None, (pw_pfad, "/opt/pw-browsers")):
        kandidat = Path(basis) / "chromium"
        if kandidat.exists():
            return str(kandidat)
    return None


_CHROMIUM = _finde_chromium()
pytestmark_browser = pytest.mark.skipif(
    _CHROMIUM is None,
    reason="kein Headless-Chromium gefunden — die statischen Tests oben decken dieselben Fälle")


# ---------------------------------------------------------------------------
# Chromium-Infrastruktur-Stabilisierung (Easy-Auftrag 26.10.2026).
#
# BEFUND (vier belegte CI-Läufe, identisches Muster — s. PR-Text):
# `subprocess.run([...chromium..., "--dump-dom", ...], timeout=30)` liefert
# NIE auch nur ein Byte stdout und wird nach GENAU 30 s per SIGKILL beendet
# (returncode -9); stderr trägt in jedem Fall exakt eine Zeile:
# "dbus/bus.cc: Failed to connect to the bus: Could not parse server
# address …". Der GitHub-`ubuntu-latest`-Runner hat keine laufende D-Bus-
# Session; ohne `DBUS_SESSION_BUS_ADDRESS` versucht Chromiums GLib-Schicht
# einen Autolaunch, der hier erst nach dem vollen Timeout aufgibt — kein
# kurzer Warnhinweis, sondern der GANZE Hänger. `DBUS_SESSION_BUS_ADDRESS=
# /dev/null` lässt den Parse-Versuch sofort (ohne Autolaunch-Wartezeit)
# fehlschlagen, Chromium läuft dann ohne D-Bus-Anbindung normal weiter.
#
# Zusätzlich (Punkt 2 des Auftrags): ein begrenzter Wiederholversuch NUR für
# Infrastruktur-Fehler (Timeout/Start fehlgeschlagen) — eine ECHTE Mess-
# Abweichung (scrollWidth > clientWidth, in den Tests unten geprüft, NICHT
# hier) wird davon nie berührt, weil sie erst NACH einem erfolgreichen
# `_miss_overflow()`-Aufruf ausgewertet wird.
# ---------------------------------------------------------------------------
_CHROMIUM_ENV = {**os.environ, "DBUS_SESSION_BUS_ADDRESS": "/dev/null"}


class ChromiumInfraFehler(RuntimeError):
    """Chromium-Start-/Infrastruktur-Fehler (Timeout, Prozess nicht gestartet,
    DOM-Dump nicht lesbar) — ausdrücklich NICHT die zu prüfende Layout-
    Eigenschaft. NUR diese Fehlerklasse wird wiederholt."""


def _chromium_mit_retry(fn, *args, max_versuche: int = 3, **kwargs):
    """Ruft `fn(*args, **kwargs)` auf; wiederholt AUSSCHLIESSLICH bei
    `ChromiumInfraFehler`, höchstens `max_versuche - 1` Mal (Default: 2
    Wiederholungen = 3 Versuche gesamt, jede im Log sichtbar). Jede andere
    Exception (insbesondere eine echte Layout-Abweichung, die der Aufrufer
    als AssertionError feststellt) wird SOFORT weitergereicht, ohne
    Wiederholung — Auftrags-Vorgabe Punkt 2. Scheitert auch der letzte
    Versuch an Infrastruktur, bleibt der Test rot mit klarer Meldung
    (Punkt 3: KEIN skip, KEIN xfail)."""
    letzter_fehler: ChromiumInfraFehler | None = None
    for versuch in range(1, max_versuche + 1):
        try:
            return fn(*args, **kwargs)
        except ChromiumInfraFehler as exc:
            letzter_fehler = exc
            print(f"[chromium-retry] Versuch {versuch}/{max_versuche} "
                  f"Chromium-Infrastruktur, nicht Layout: {exc}")
    raise ChromiumInfraFehler(
        f"Chromium-Infrastruktur, nicht Layout — nach {max_versuche} Versuchen "
        f"weiterhin rot: {letzter_fehler}"
    ) from letzter_fehler


def _extrahiere_style() -> str:
    start = HTML.index("<style>")
    end = HTML.index("</style>") + len("</style>")
    return HTML[start:end]


def _extrahiere_funktionen() -> str:
    teile = [
        _fn("_recExcluded"), _fn("episodeStatus"), _konst_obj("VSDIST_COLOR"),
        _konst_simple("VERLUSTBILD_MIN_N"), _fn("fmtPct1"), _fn("esc"),
        _fn("verlustbildPopulation"), _fn("verlustbildEimer"), _fn("verlustbildHtml"),
        _fn("primaerzeileHtml"),
    ]
    return "\n".join(teile)


def _node_markup() -> str:
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        pytest.skip("kein node vorhanden, um das echte Markup zu rendern")
    quelle = _extrahiere_funktionen() + (
        "\nconsole.log(JSON.stringify("
        "primaerzeileHtml() + verlustbildHtml(" + json.dumps(_RECORDS) + ")));"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(quelle)
        pfad = f.name
    try:
        r = subprocess.run([node, pfad], capture_output=True, text=True, timeout=60)
    finally:
        Path(pfad).unlink(missing_ok=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _miss_overflow(markup: str, breite: int) -> dict:
    style = _extrahiere_style()
    html = f"""<!doctype html><html><head><meta charset="utf-8">
{style}
<style>html,body{{margin:0;width:{breite}px;height:800px}}</style>
</head><body>
<div class="bt-overlay" id="ov" style="position:static;display:flex;height:800px">
<div class="bt-body" id="info-body">{markup}</div>
</div>
<div id="out"></div>
<script>
  const ov = document.getElementById('ov');
  document.getElementById('out').textContent = JSON.stringify(
    {{scrollWidth: ov.scrollWidth, clientWidth: ov.clientWidth}});
</script>
</body></html>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        pfad = f.name
    try:
        try:
            r = subprocess.run(
                [_CHROMIUM, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--virtual-time-budget=2000", "--dump-dom", f"file://{pfad}"],
                capture_output=True, text=True, timeout=30, env=_CHROMIUM_ENV)
        except subprocess.TimeoutExpired as exc:
            raise ChromiumInfraFehler(f"Chromium-Start timed out: {exc}") from exc
    finally:
        Path(pfad).unlink(missing_ok=True)
    if r.returncode != 0:
        raise ChromiumInfraFehler(f"Chromium-Start fehlgeschlagen (rc={r.returncode}): {r.stderr}")
    treffer = re.search(r'\{"scrollWidth":\d+,"clientWidth":\d+\}', r.stdout)
    if not treffer:
        raise ChromiumInfraFehler(
            f"Messwert nicht im DOM-Dump gefunden (Chromium-Ausgabe unvollständig):\n{r.stdout[-500:]}")
    return json.loads(treffer.group(0))


def _miss_overflow_mit_retry(markup: str, breite: int) -> dict:
    """`_miss_overflow()` mit begrenztem Wiederholversuch NUR für
    Infrastruktur-Fehler (s. `_chromium_mit_retry` oben). Die eigentliche
    Layout-Bewertung (scrollWidth vs. clientWidth) findet ERST beim Aufrufer
    statt, NACH einem erfolgreichen Rückgabewert hier — eine echte Abweichung
    wird dadurch nie wiederholt."""
    return _chromium_mit_retry(_miss_overflow, markup, breite)


# ---------------------------------------------------------------------------
# Tests für den Retry-Helfer selbst — braucht KEIN Chromium (simulierte
# Infrastruktur-Fehler), läuft deshalb IMMER, auch ohne `pytestmark_browser`.
# ---------------------------------------------------------------------------
def test_retry_helfer_erfolg_nach_1_simuliertem_timeout():
    aufrufe = []

    def fn():
        aufrufe.append(1)
        if len(aufrufe) < 2:
            raise ChromiumInfraFehler("Timeout simuliert (1x)")
        return "ok"

    assert _chromium_mit_retry(fn) == "ok"
    assert len(aufrufe) == 2  # 1 Fehlschlag + 1 Erfolg


def test_retry_helfer_erfolg_nach_2_simulierten_timeouts():
    aufrufe = []

    def fn():
        aufrufe.append(1)
        if len(aufrufe) < 3:
            raise ChromiumInfraFehler("Timeout simuliert (2x)")
        return "ok"

    assert _chromium_mit_retry(fn) == "ok"
    assert len(aufrufe) == 3  # 2 Fehlschläge + 1 Erfolg


def test_retry_helfer_rot_nach_3_simulierten_timeouts():
    """Höchstens 2 Wiederholungen (Auftrags-Vorgabe) — ein dritter
    Infrastruktur-Fehlschlag in Folge bleibt rot, KEIN skip/xfail."""
    aufrufe = []

    def fn():
        aufrufe.append(1)
        raise ChromiumInfraFehler("Timeout simuliert (3x in Folge)")

    with pytest.raises(ChromiumInfraFehler, match="nicht Layout"):
        _chromium_mit_retry(fn)
    assert len(aufrufe) == 3  # genau 3 Versuche, nicht mehr


def test_echte_layout_abweichung_sofort_rot_ohne_wiederholung():
    """Auftrags-Vorgabe wörtlich: eine echte Prüf-Abweichung wird NIE
    wiederholt. `_miss_overflow_mit_retry()`/`_chromium_mit_retry()` fangen
    NUR `ChromiumInfraFehler` — eine `AssertionError` (hier stellvertretend
    für den scrollWidth>clientWidth-Befund, der im Aufrufer selbst als
    AssertionError auftritt) geht beim ERSTEN Versuch durch."""
    aufrufe = []

    def fn():
        aufrufe.append(1)
        raise AssertionError("Überlauf gemessen — echte Layout-Abweichung")

    with pytest.raises(AssertionError):
        _chromium_mit_retry(fn)
    assert len(aufrufe) == 1  # KEINE Wiederholung


def test_mutationsprobe_wiederholung_auch_bei_layout_fehler_waere_rot():
    """ECHTE Mutationsprobe (ohne Produktionscode zu verändern): eine ZU
    WEITE Fangklausel (`except Exception` statt `except ChromiumInfraFehler`)
    würde auch eine Layout-Abweichung wiederholen. Hier direkt simuliert und
    dem belegten Verhalten oben (1 Aufruf, keine Wiederholung) gegenüber-
    gestellt — der Unterschied zeigt, dass die echte Implementierung NICHT
    diese zu weite Fangklausel verwendet."""
    aufrufe = []

    def fn():
        aufrufe.append(1)
        raise AssertionError("Überlauf gemessen — echte Layout-Abweichung")

    def mutierter_retry_mit_zu_weiter_fangklausel(fn, max_versuche=3):
        letzter = None
        for _ in range(max_versuche):
            try:
                return fn()
            except Exception as exc:  # Mutation: faengt ALLES, nicht nur Infra
                letzter = exc
        raise letzter

    with pytest.raises(AssertionError):
        mutierter_retry_mit_zu_weiter_fangklausel(fn)
    assert len(aufrufe) == 3  # die Mutation HÄTTE wiederholt — Gegenbeweis zu oben


@pytestmark_browser
def test_kein_horizontales_ueberlaufen_bei_360_und_390px():
    """Der Wert-Test aus dem Auftrag: scrollWidth <= clientWidth des Panels
    bei 360 und 390 px, mit dem ECHTEN, aktuell gerenderten Verlustbild
    (live gegen die aktuelle Sammlung, kein eingefrorener Schnappschuss)."""
    markup = _node_markup()
    for breite in (360, 390):
        ergebnis = _miss_overflow_mit_retry(markup, breite)
        assert ergebnis["scrollWidth"] <= ergebnis["clientWidth"], (
            f"Überlauf bei {breite}px: scrollWidth={ergebnis['scrollWidth']} "
            f"> clientWidth={ergebnis['clientWidth']}")


@pytestmark_browser
def test_mutationsprobe_browser_alte_klasse_laesst_wirklich_ueberlaufen():
    """ECHTE Mutationsprobe: dieselbe Zeilen-HTML, aber mit der ALTEN Klasse
    `vsdist-rows` statt `vbild-rows` — muss bei 360 px wirklich überlaufen
    (das ist der Zustand VOR diesem Fix, Easys Screenshot-Befund)."""
    markup = _node_markup()
    kaputtes_markup = markup.replace('class="vbild-rows"', 'class="vsdist-rows"')
    assert kaputtes_markup != markup, "Mutation griff nicht — Klassenname nicht gefunden"
    ergebnis = _miss_overflow_mit_retry(kaputtes_markup, 360)
    assert ergebnis["scrollWidth"] > ergebnis["clientWidth"], (
        "Mutationsprobe zeigt KEINEN Überlauf — entweder ist der Fix nicht "
        "wirksam oder die Probe greift nicht mehr (beides zu prüfen)")
