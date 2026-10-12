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
        r = subprocess.run(
            [_CHROMIUM, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--virtual-time-budget=2000", "--dump-dom", f"file://{pfad}"],
            capture_output=True, text=True, timeout=30)
    finally:
        Path(pfad).unlink(missing_ok=True)
    assert r.returncode == 0, r.stderr
    treffer = re.search(r'\{"scrollWidth":\d+,"clientWidth":\d+\}', r.stdout)
    assert treffer, f"Messwert nicht im DOM-Dump gefunden:\n{r.stdout[-500:]}"
    return json.loads(treffer.group(0))


@pytestmark_browser
def test_kein_horizontales_ueberlaufen_bei_360_und_390px():
    """Der Wert-Test aus dem Auftrag: scrollWidth <= clientWidth des Panels
    bei 360 und 390 px, mit dem ECHTEN, aktuell gerenderten Verlustbild
    (live gegen die aktuelle Sammlung, kein eingefrorener Schnappschuss)."""
    markup = _node_markup()
    for breite in (360, 390):
        ergebnis = _miss_overflow(markup, breite)
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
    ergebnis = _miss_overflow(kaputtes_markup, 360)
    assert ergebnis["scrollWidth"] > ergebnis["clientWidth"], (
        "Mutationsprobe zeigt KEINEN Überlauf — entweder ist der Fix nicht "
        "wirksam oder die Probe greift nicht mehr (beides zu prüfen)")
