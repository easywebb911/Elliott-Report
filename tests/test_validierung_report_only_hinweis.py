"""Validierung-Panel: "Zwischenstand" statt Fehlertext bei REPORT_ONLY-Reports
(11.09.2026, Diagnose-Folgeauftrag).

ANLASS: Easy sah im Validierung-Bereich "Die gesammelten Fälle konnten nicht
geladen werden" — Ursache war KEIN Datenfehler, sondern ein legitim
erreichbarer Zustand: `report.validation` fehlt IMMER, wenn der geladene
Report vom Mittagslauf (#124, REPORT_ONLY=1) stammt, der diesen Block
bewusst nie schreibt. Diagnose vom selben Tag lokalisierte die Stelle exakt
(docs/index.html: `_val`-Zuweisung, `if (_val)`-Bedingung, Fallback-Text).

ZWEI FÄLLE, JETZT UNTERSCHIEDEN:
  (a) `validation` fehlt WEIL REPORT_ONLY — erkennbar am additiven
      Backend-Marker `report.mode === "report_only"`
      (scripts/elliott_pipeline.py, s. tests/test_report_only_modus.py).
      -> freundlicher, nicht alarmierender Zwischenstands-Hinweis.
  (b) `validation` fehlt aus einem ANDEREN, unerwarteten Grund (kein
      `mode`-Marker gesetzt) -> weiterhin der (korrigierte) Fehlertext,
      NICHT verschluckt.

DIESE TESTS FÜHREN DEN ECHTEN, AUS docs/index.html EXTRAHIERTEN
JavaScript-Entscheidungs-Kern von `openValidierung()` in Node.js aus (kein
Nachbau) — dieselbe Lehre wie an anderer Stelle in diesem Repo: Quelltext-
Nähe allein beweist kein Verhalten. `loadCollection()`/
`statusDistributionHtml()`/`rWerteHtml()` werden minimal gestubbt (reine
Markierungs-Strings als Rückgabewert), der zu testende Entscheidungscode
selbst bleibt unverändert der echte.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")

NODE = shutil.which("node")


def _extrahiere_openvalidierung_kern() -> str:
    """Der Entscheidungs-Kern von openValidierung(): von `let head = '';`
    bis zum Ende des `if (!head) {...}`-Fallbacks — exakt der Text aus der
    Datei, keine Kopie/Abschrift."""
    fn_marker = "async function openValidierung() {"
    fn_start = HTML.index(fn_marker)
    kern_start = HTML.index("let head = '';", fn_start)
    ende_marker = "+ 'geladen werden.</p>';\n      }"
    kern_ende = HTML.index(ende_marker, kern_start) + len(ende_marker)
    kern = HTML[kern_start:kern_ende]
    assert "openInfo" not in kern, "Kern sollte DOM-frei sein (nur head wird zurückgegeben)"
    return kern


KERN = _extrahiere_openvalidierung_kern()

# Reine Marker-Rückgaben statt echter Sammlung — die Wert-Tests hier prüfen
# die VERZWEIGUNG (welcher Text erscheint), nicht die Status-Verteilung/
# R-Werte selbst (dafür: test_status_verteilung.py / test_r_werte_anzeige.py).
_STUBS = """
    function statusDistributionHtml(records) { return '<STATUSDIST>'; }
    function rWerteHtml(records) { return '<RWERTE>'; }
    async function loadCollection() { throw new Error('sollte hier nicht noetig sein'); }
"""


def _lauf(val, report_only, wl_coll=None) -> str:
    """Führt den echten Entscheidungs-Kern mit gegebenen `_val`/`_reportOnly`/
    `_wlColl`-Werten aus und gibt den resultierenden `head`-String zurück."""
    if wl_coll is None:
        wl_coll = [{"ticker": "AAPL"}]  # nicht-leeres Array -> loadCollection() wird NICHT gebraucht
    js = f"""
    (async () => {{
      let _val = {json.dumps(val)};
      let _reportOnly = {json.dumps(report_only)};
      let _wlColl = {json.dumps(wl_coll)};
      {_STUBS}
      {KERN}
      process.stdout.write(JSON.stringify({{head}}));
    }})().catch(e => {{ console.error(e); process.exit(1); }});
    """
    res = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=15)
    assert res.returncode == 0, f"Node-Fehler: {res.stderr}"
    return json.loads(res.stdout)["head"]


pytestmark = pytest.mark.skipif(NODE is None, reason="node nicht verfügbar")


# ---------------------------------------------------------------------------
# (a) Wert-Test: REPORT_ONLY-artiger Report -> freundlicher Zwischenstand
# ---------------------------------------------------------------------------
def test_report_only_report_zeigt_zwischenstand_kein_fehlertext():
    head = _lauf(val=None, report_only=True)
    assert "Zwischenstand" in head
    assert "konnten nicht geladen werden" not in head
    assert "Lauf-Status" not in head
    # #107/#123 bleiben sichtbar — sie hängen an der Sammlung, nicht an
    # report.validation (Diagnose 11.09.2026, Auftrag Punkt 5).
    assert "<STATUSDIST>" in head
    assert "<RWERTE>" in head
    # GRENZEN: kein Warnsymbol/Fehler-Framing, keine Suggestion eines
    # bereits vorliegenden Ergebnisses.
    assert "⚠" not in head
    assert "err" not in head.lower() or "Fehler" not in head


# ---------------------------------------------------------------------------
# (b) Wert-Test: validation fehlt OHNE report_only-Marker -> weiterhin Fehler
# ---------------------------------------------------------------------------
def test_echter_fehlerfall_zeigt_weiterhin_fehlertext_korrigiert():
    head = _lauf(val=None, report_only=False)
    assert "konnten nicht geladen werden" in head
    assert "Zwischenstand" not in head
    # Diagnose 11.09.2026: der Verweis war ungenau (Lauf-Status zeigt die
    # fehlenden Zahlen NICHT) — muss jetzt weg sein.
    assert "Lauf-Status" not in head


# ---------------------------------------------------------------------------
# Regression: vollständiger Report mit validation-Block unverändert
# ---------------------------------------------------------------------------
def test_normaler_report_mit_validation_unveraendert():
    val = {"collected": 140, "matured": 112, "evaluable": 106, "eval_min_n": 100}
    head = _lauf(val=val, report_only=False)
    assert "vsum-hero" in head
    assert "<b>140</b>" in head
    assert "<b>106</b>" in head
    assert "<STATUSDIST>" in head
    assert "<RWERTE>" in head
    assert "Zwischenstand" not in head
    assert "konnten nicht geladen werden" not in head


def test_reportonly_marker_ueberstimmt_nicht_einen_vorhandenen_validation_block():
    """Randfall: sollte ein Report sowohl `mode==='report_only'` ALS AUCH
    (theoretisch) einen validation-Block tragen, hat `_val` Vorrang — der
    reale Zahlen-Block geht vor dem generischen Hinweis (kann heute laut
    Backend nicht vorkommen, s. PR-Text, aber die Fallreihenfolge im Code
    soll das trotzdem robust behandeln)."""
    val = {"collected": 5, "matured": 2, "evaluable": 1, "eval_min_n": 100}
    head = _lauf(val=val, report_only=True)
    assert "vsum-hero" in head
    assert "Zwischenstand" not in head


# ---------------------------------------------------------------------------
# Strukturelle Anker (Muster aus test_validierung_nerds_kein_rohtext.py) —
# ergänzen, nicht ersetzen die Wert-Tests oben.
# ---------------------------------------------------------------------------
def test_reportonly_variable_wird_aus_report_mode_gesetzt():
    assert "_reportOnly = !!(r && r.mode === 'report_only');" in HTML


def test_kein_warnsymbol_im_zwischenstands_text_im_quelltext():
    start = HTML.index("Zwischenstand: Dieser Lauf ist ein")
    ende = HTML.index("</p>`;", start)
    block = HTML[start:ende]
    assert "⚠" not in block
    assert "class=\"err\"" not in HTML[max(0, start - 200):start]


def test_alte_ungenaue_lauf_status_verweis_komplett_entfernt():
    assert "Der Stand steht auch im ☰ → Lauf-Status." not in HTML
