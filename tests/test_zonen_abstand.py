"""Zonen-Abstand in Prozent — an Zielzone und Extension jeder Live-Karte.

Rein im Frontend gerechnet (01.08.2026): `(Zonen-Unterkante / Kurs − 1) × 100`.
Bezugskante ist bewusst die **Unterkante** — dieselbe Kante, an der die Pipeline
`target_exceeded` schneidet und an der die Erfolgsmessung einen Treffer zählt.
Eine andere Kante wäre eine zweite, stille Definition von „Ziel".

Zwei Netze, wie beim Trade-Journal (#65):
  (a) LITERALE Pins auf die Stellen, an denen ein stiller Dreher die Zahl kippt
      — laufen überall, ohne Zusatz-Abhängigkeit;
  (b) die Rechenkerne werden mit **node wirklich ausgeführt**, inklusive der
      Live-Patch-Verdrahtung an einem DOM-Doppel. Fehlt node, greift (a) allein
      (skip statt Fehler — die Suite bekommt keine neue harte Abhängigkeit).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) Literale Pins
# ---------------------------------------------------------------------------
def test_die_bezugskante_ist_die_UNTERKANTE():
    """Der Kernsatz. Ein Wechsel auf `.high` wäre lautlos plausibel — und
    würde die Zahl von der Filter- und Messkante entkoppeln."""
    assert "return (zl / p - 1) * 100;" in HTML
    for aufruf in (
        "zoneDistSpan(ez.low, c.close)",
        "zoneDistSpan(c.target_zone.low, c.close)",
        "zoneDistSpan(hd.target_zone.low, c.close)",
        "zoneDistSpan(hd.target_zone_extended.low, c.close)",
        "zoneDistSpan(c.target_zone.low, cardClose)",
        "zoneDistSpan(c.target_zone_extended.low, cardClose)",
        # Alt-Zählung (Guardian-Nit 04.08.): liegt auf DERSELBEN live
        # getickten Karte und hatte als einzige Zonen-Anzeige keinen Abstand.
        "zoneDistSpan(alt.target_zone.low, c.close)",
    ):
        assert aufruf in HTML, f"{aufruf} fehlt — Bezugskante oder Kurs vertauscht?"
    assert ".high, c.close)" not in HTML and ".high, cardClose)" not in HTML, \
        "irgendwo wird die OBERkante als Bezug benutzt"


def test_der_live_poller_zieht_den_abstand_mit():
    """Ohne diese Zeile stünde ein frischer Kurs neben einer Prozentzahl, die
    noch den Report-Stand meint — beide auf derselben Karte."""
    assert ("card.querySelectorAll('[data-zone-dist]')"
            ".forEach(el => _setZoneDist(el, q.price));") in HTML


def test_der_bezugskurs_ist_der_angezeigte_kurs():
    """Gerendert wird mit `c.close` bzw. `cardClose` — demselben Wert, der im
    Kurs-Feld steht. Danach übernimmt der Poller (Test darüber)."""
    assert "function zoneDistSpan(low, price)" in HTML
    assert "const txt = zoneDistText(zoneDistPct(low, price));" in HTML


def test_die_farbe_ist_neutral():
    """Abstand ist ein Fakt, kein Gut/Schlecht: kein Grün, kein Rot, keine
    Vorzeichen-Farbe."""
    start = HTML.index("    .zone-dist {")
    block = HTML[start:HTML.index("}", start)]
    assert "var(--txt-dim)" in block
    for verboten in ("--grn", "--red", "green", "red", "chg-up", "chg-down"):
        assert verboten not in block, f"Farb-Semantik eingeschleppt: {verboten}"


def test_kein_umbruch_zwischen_zahl_und_prozentzeichen():
    start = HTML.index("    .zone-dist {")
    block = HTML[start:HTML.index("}", start)]
    assert "white-space:nowrap" in block
    assert "tabular-nums" in block, "sonst springen die Spalten beim Live-Tick"


def test_der_abstand_steht_NEBEN_dem_nowrap_wert_nicht_darin():
    """`.tf-v` ist `white-space:nowrap`. Läge der Abstand darin, wären Zone und
    Prozentzahl EIN unumbrechbarer Block und die 390px-Kachel risse auf."""
    assert ("`<span class=\"tf-v\">${vv}</span>${dist || ''}</span>`") in HTML


def test_report_und_pipeline_bleiben_unberuehrt():
    """Reines Frontend: der Zweig darf NUR docs/ und tests/ anfassen."""
    r = subprocess.run(["git", "diff", "--name-only", "origin/main", "--",
                        "scripts/", "config.py", "data/", ".github/"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip() == "", f"nicht-Frontend im Diff: {r.stdout!r}"


def test_die_methodik_nennt_die_bezugskante():
    assert "'Zonen-Abstand (%)'" in HTML
    stelle = HTML.index("'Zonen-Abstand (%)'")
    eintrag = HTML[stelle:stelle + 1400]
    assert "Unterkante" in eintrag
    assert "target_exceeded" in eintrag
    assert "neutral" in eintrag


# ---------------------------------------------------------------------------
# (b) node: die Rechenkerne WIRKLICH ausführen
# ---------------------------------------------------------------------------
_NODE = shutil.which("node") or shutil.which("nodejs")


def _fn(name: str) -> str:
    start = HTML.index(f"    function {name}(")
    return HTML[start:HTML.index("\n    }", start) + len("\n    }")]


def _konst(name: str) -> str:
    start = HTML.index(f"    const {name} =")
    return HTML[start:HTML.index(";\n", start) + 1]


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken dieselben Fälle")
    quelle = (_konst("ZONE_DIST_TITLE") + "\n"
              + "\n".join(_fn(n) for n in
                          ("zoneDistPct", "zoneDistText", "zoneDistSpan")))
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("kante, kurs, soll", [
    # Von Hand nachgerechnet — die drei Fälle aus dem Auftrag …
    (107.4, 100, "+7,4 %"),
    (98.8, 100, "−1,2 %"),
    # … plus die Ränder, an denen die Rundung entscheidet.
    (100.0, 100, "0,0 %"),        # exakt auf dem Kurs -> KEIN Vorzeichen
    (99.96, 100, "0,0 %"),        # -0,04 % -> gerundet -0 -> kein „−0,0 %"
    (100.04, 100, "0,0 %"),       # +0,04 % -> gerundet 0 -> kein „+0,0 %"
    (100.06, 100, "+0,1 %"),      # klar über der Rundungsgrenze -> auf
    (150.0, 100, "+50,0 %"),
    (50.0, 100, "−50,0 %"),
    (38.5944, 36.7566, "+5,0 %"), # der echte IONQ-Fall aus der 390px-Probe
])
def test_werte_von_hand_nachgerechnet(kante, kurs, soll):
    ist = _js(f"console.log(JSON.stringify(zoneDistText(zoneDistPct({kante}, {kurs}))))")
    assert ist == soll


@pytest.mark.parametrize("kante, kurs", [
    (100, None), (100, 0), (100, "keine-zahl"), (None, 100), (100, float("inf")),
])
def test_ohne_darstellbaren_wert_kommt_NICHTS(kante, kurs):
    """Kein Kurs / Kurs 0 / nicht-finit -> Prozentangabe weglassen, nie NaN.

    Der Fall `kante=None` hat beim Schreiben dieses Tests einen echten Defekt
    gehoben: `Number(null)` ist 0 und damit endlich, eine FEHLENDE Kante ergab
    also brav „−100,0 %". Jetzt fängt `zoneDistPct` null/undefined/'' zuerst ab.
    """
    k = "null" if kante is None else json.dumps(kante)
    p = ("null" if kurs is None else
         ("Infinity" if kurs == float("inf") else json.dumps(kurs)))
    # `String(...)` statt des Rohwerts (Guardian-Fund 04.08.2026): `JSON`
    # bildet Infinity auf `null` ab — der Test konnte „echtes null" und
    # „Infinity durchgerutscht" nicht unterscheiden und überlebte deshalb das
    # Entfernen des `p === 0`-Guards. Als Zeichenkette sind sie verschieden.
    pct, txt = _js(
        f"console.log(JSON.stringify([String(zoneDistPct({k}, {p})), "
        f"zoneDistText(zoneDistPct({k}, {p}))]))")
    assert pct == "null", f"zoneDistPct lieferte {pct!r} statt null"
    assert txt == ""


def test_der_span_traegt_die_kante_und_versteckt_sich_ohne_wert():
    html_mit, html_ohne = _js(
        "console.log(JSON.stringify(["
        "zoneDistSpan(107.4, 100), zoneDistSpan(107.4, 0)]))")
    assert 'data-zl="107.4"' in html_mit and ">+7,4 %<" in html_mit
    assert " hidden>" in html_ohne, "ohne Kurs muss der Baustein versteckt sein"
    assert "NaN" not in html_ohne and "undefined" not in html_ohne


def test_ohne_kante_entsteht_gar_kein_baustein():
    leer = _js("console.log(JSON.stringify(["
               "zoneDistSpan(null, 100), zoneDistSpan(undefined, 100)]))")
    assert leer == ["", ""]


# ---------------------------------------------------------------------------
# (b2) Der Poller-Beweis — _setZoneDist an einem DOM-Doppel WIRKLICH ausführen
# ---------------------------------------------------------------------------
_DOM_DOPPEL = """
function El(zl) {
  return { dataset: { zl: String(zl) }, textContent: '(Report-Stand)',
           hidden: false };
}
"""


def test_ein_quote_tick_setzt_den_NEUEN_abstand():
    """Der Poller-Beweis: nach dem Tick steht der Abstand zum NEUEN Kurs da,
    nicht mehr der Report-Stand.

    Von Hand: Kante 107,4. Report-Kurs 100 -> „+7,4 %". Tick auf 110 ->
    107,4/110 − 1 = −2,363…% -> „−2,4 %".
    """
    ergebnis = _js(_DOM_DOPPEL + _fn("_setZoneDist") + """
      const el = El(107.4);
      _setZoneDist(el, 100);   const vorher = el.textContent;
      _setZoneDist(el, 110);   const nachher = el.textContent;
      console.log(JSON.stringify({vorher, nachher, hidden: el.hidden}));
    """)
    assert ergebnis["vorher"] == "+7,4 %"
    assert ergebnis["nachher"] == "−2,4 %"
    assert ergebnis["hidden"] is False


def test_ein_unbrauchbarer_tick_versteckt_statt_NaN_zu_zeigen():
    ergebnis = _js(_DOM_DOPPEL + _fn("_setZoneDist") + """
      const el = El(107.4);
      _setZoneDist(el, 100);
      _setZoneDist(el, 0);
      console.log(JSON.stringify({text: el.textContent, hidden: el.hidden}));
    """)
    assert ergebnis["hidden"] is True
    assert "NaN" not in ergebnis["text"]


def test_nach_einem_schlechten_tick_kommt_der_abstand_ZURUECK():
    """Guardian-Fund 04.08.2026: `el.hidden = false;` aus ``_setZoneDist`` zu
    entfernen überlebte alle 27 Tests.

    Die Folge wäre live spürbar: ein einziger unbrauchbarer Quote-Tick (etwa
    ein Preis 0 vom Proxy) versteckt den Abstand — und er käme **nie wieder**,
    obwohl jeder folgende Tick gültig ist. Kein Test durchlief den Übergang
    versteckt → sichtbar, weil das DOM-Doppel immer mit ``hidden:false``
    startete. Genau dieser Übergang steht jetzt hier.
    """
    ergebnis = _js(_DOM_DOPPEL + _fn("_setZoneDist") + """
      const el = El(107.4);
      _setZoneDist(el, 0);            // schlechter Tick -> versteckt
      const dazwischen = el.hidden;
      _setZoneDist(el, 100);          // wieder gueltig -> muss zurueckkommen
      console.log(JSON.stringify(
        {dazwischen, hidden: el.hidden, text: el.textContent}));
    """)
    assert ergebnis["dazwischen"] is True
    assert ergebnis["hidden"] is False, \
        "der Abstand bleibt nach einem schlechten Tick für immer versteckt"
    assert ergebnis["text"] == "+7,4 %"


def test_auch_ein_von_ANFANG_an_versteckter_baustein_wird_sichtbar():
    """Der Renderpfad: ohne Kurs entsteht der Baustein mit `hidden`. Der erste
    gültige Tick muss ihn zeigen — sonst bliebe eine Karte ohne Report-Kurs
    dauerhaft ohne Abstand."""
    ergebnis = _js(_DOM_DOPPEL + _fn("_setZoneDist") + """
      const el = El(107.4); el.hidden = true; el.textContent = '';
      _setZoneDist(el, 100);
      console.log(JSON.stringify({hidden: el.hidden, text: el.textContent}));
    """)
    assert ergebnis["hidden"] is False and ergebnis["text"] == "+7,4 %"


def test_quotePatch_verdrahtet_ALLE_abstaende_der_karte():
    """Nicht nur „die Zeile steht da": quotePatch wird an einem Karten-Doppel
    mit DREI Abständen ausgeführt — Zielzone, Extension, Zeitebene."""
    ergebnis = _js(_DOM_DOPPEL + _fn("_setZoneDist") + """
      const els = [El(107.4), El(120), El(90)];
      // Nur der Zweig, den dieser PR ergaenzt — die uebrigen Patch-Zweige
      // haben eigene Tests und brauchen hier keine Doppel.
      const card = { querySelectorAll: sel =>
        (sel === '[data-zone-dist]' ? els : []) };
      const q = { price: 100 };
      card.querySelectorAll('[data-zone-dist]').forEach(el => _setZoneDist(el, q.price));
      console.log(JSON.stringify(els.map(e => e.textContent)));
    """)
    assert ergebnis == ["+7,4 %", "+20,0 %", "−10,0 %"]
