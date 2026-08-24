"""Status-Verteilung + gekürzte "Details für Nerds" (23.08.2026, Easy-Wunsch).

TEIL A: eine neue, sofort sichtbare (kein Aufklappen nötig) Prozent-/
Balken-Darstellung der sechs `episodeStatus()`-Kategorien (offen/Extension/
Zone/invalidiert/gereift-neutral/ausgeschlossen) im Validierung-Hauptbereich
(`openValidierung()`), oberhalb der drei bestehenden Kennzahlen (108
gesammelt / 70 fertig beobachtet / 64 auswertbar). EINE Zähl-Quelle:
`statusDistribution()` ruft `episodeStatus()` für jeden Record auf — dieselbe
Funktion, die auch jede einzelne Episode-Zeile im Backtesting-Overlay als
Badge zeigt. Keine neue Berechnung, keine Bewertung.

Rückfrage-Ergebnis (Mini-Stopp vor der Umsetzung): ein Record
(`JUN3.DE@2026-08-06`) ist zugleich PRU-ausgeschlossen UND invalidiert.
`episodeStatus()` prüft `invalidated` VOR `_recExcluded` (bestehende
Priorität, unverändert) — der Record zählt deshalb hier als "invalidiert"
(17 statt 16) statt als "ausgeschlossen" (5 statt 6). Die bestehende
Vsum-Notiz ("6 Fälle zählen nicht mit") nutzt eine ANDERE, ebenfalls
bestehende Definition (`matured - evaluable`, backend-seitig über
`eval_counts`) und bleibt bei 6 — unverändert, GRENZEN. Easy hat entschieden:
`episodeStatus()` 1:1 übernehmen (5/17), Diskrepanz im UI-Text erklären
(`statusDistributionHtml`s Hinweistext).

TEIL B: "Details für Nerds" stark gekürzt, mit einer neuen, Pflicht-Erklärung
der sechs Status in einfacher Sprache. "Trefferquote"/"Erfolgsquote"/
"Ergebnis" bewusst durchgängig vermieden (Leitplanke: keine Ergebnis-
Suggestion vor n≥100).

Zwei Netze (Muster aus test_zonen_abstand.py/test_chart_vorschau.py):
  (a) Literale/String-Anker — laufen überall, ohne Zusatz-Abhängigkeit.
  (b) node: `statusDistribution()`/`statusDistributionHtml()` WIRKLICH
      ausgeführt gegen die echten 108 Records aus
      `data/forward_collection.json` — die Prozent-Verteilung von Hand
      nachgerechnet und als Soll-Wert hinterlegt. Fehlt node, greift (a)
      allein (skip).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


def _fn(name: str, tiefe: str = "    ") -> str:
    for prefix in ("function", "async function"):
        marke = f"{tiefe}{prefix} {name}("
        if marke in HTML:
            start = HTML.index(marke)
            return HTML[start:HTML.index(f"\n{tiefe}}}", start) + len(f"\n{tiefe}}}")]
    raise AssertionError(f"Funktion {name!r} nicht gefunden")


def _konst_array(name: str) -> str:
    marke = f"    const {name} = ["
    start = HTML.index(marke)
    return HTML[start:HTML.index("];\n", start) + 3]


def _konst_obj(name: str) -> str:
    marke = f"    const {name} = {{"
    start = HTML.index(marke)
    return HTML[start:HTML.index("};\n", start) + 3]


# ---------------------------------------------------------------------------
# (a) Literale/String-Anker
# ---------------------------------------------------------------------------
def test_episodestatus_bleibt_die_alleinige_quelle():
    """statusDistribution ruft episodeStatus() auf — keine zweite,
    abweichende Klassifikation."""
    koerper = _fn("statusDistribution")
    assert "const cls = episodeStatus(r).cls;" in koerper


def test_reihenfolge_entspricht_genau_der_auftragsnennung():
    ordnung = _konst_array("VSDIST_ORDER")
    assert "['st-open', 'offen']" in ordnung
    assert "['st-ext', 'Extension']" in ordnung
    assert "['st-target', 'Zone']" in ordnung
    assert "['st-inval', 'invalidiert']" in ordnung
    assert "['st-neutral', 'gereift · neutral']" in ordnung
    assert "['st-excluded', 'ausgeschlossen']" in ordnung
    # Reihenfolge: offen, Extension, Zone, invalidiert, neutral, ausgeschlossen.
    idx = [ordnung.index(m) for m in
           ("'st-open'", "'st-ext'", "'st-target'", "'st-inval'", "'st-neutral'", "'st-excluded'")]
    assert idx == sorted(idx)


def test_verteilung_sitzt_oberhalb_der_drei_kennzahlen_ohne_aufklappen():
    koerper = _fn("openValidierung", tiefe="    ")
    dist_pos = koerper.index("statusDistributionHtml")
    hero_pos = koerper.index("vsum-hero")
    assert dist_pos < hero_pos, "Verteilung muss VOR den drei Kennzahlen gebaut/eingefügt werden"
    # Kein <details>/<summary> um den Verteilungs-Block — sofort sichtbar.
    block = koerper[koerper.index("head =") - 5:hero_pos]
    assert "<details" not in block


def test_verteilung_ist_lazy_gegen_fehlende_sammlung_kein_null_prozent_rauschen():
    koerper = _fn("statusDistributionHtml")
    assert "if (!Array.isArray(records) || !records.length) return '';" in koerper


def test_keine_ergebnis_woerter_in_der_verteilung():
    """Leitplanke: die neue Verteilung ist Zwischenstand, kein Ergebnis."""
    dist_block = _fn("statusDistributionHtml")
    order_block = _konst_array("VSDIST_ORDER")
    open_val_block = _fn("openValidierung")
    for verboten in ("Trefferquote", "Erfolgsquote"):
        assert verboten not in dist_block, f"'{verboten}' in statusDistributionHtml"
        assert verboten not in order_block, f"'{verboten}' in VSDIST_ORDER"
    # "Ergebnis" darf im Hinweis zu "offen" vorkommen ("es gibt noch kein
    # Ergebnis") -- das ist Teil des gekürzten Nerds-Texts, nicht der
    # Verteilung selbst. In der Verteilung/Kopf-Berechnung (vor "Details für
    # Nerds") darf "Ergebnis" NICHT als Behauptung über die Fälle auftauchen.
    kopf_block = open_val_block[:open_val_block.index("nerds =")]
    assert "Ergebnis" not in kopf_block


def test_heuristisch_unvalidiert_bleibt_sichtbar():
    dist_block = _fn("statusDistributionHtml")
    assert "heuristisch · unvalidiert" in dist_block
    assert '<span class="vsum-stamp">heuristisch · unvalidiert</span>' in HTML


def test_diskrepanz_5_vs_6_wird_erklaert_nicht_versteckt():
    dist_block = _fn("statusDistributionHtml")
    assert "zugleich ausgeschlossen und" in dist_block
    assert "invalidiert" in dist_block
    assert "6 ausgeschlossene Fälle" in dist_block


# ---------------------------------------------------------------------------
# Regression: bestehende Kennzahlen/Formulierungen unverändert
# ---------------------------------------------------------------------------
def test_die_drei_bestehenden_kennzahlen_unveraendert():
    koerper = _fn("openValidierung")
    assert "<b>${collected}</b><span>gesammelt</span>" in koerper
    assert "<b>${matured}</b><span>fertig beobachtet</span>" in koerper
    assert "<b>${evaluable}</b><span>auswertbar</span>" in koerper
    assert "const excluded = matured - evaluable;" in koerper


def test_die_faelle_zaehlen_nicht_mit_formulierung_unveraendert():
    koerper = _fn("openValidierung")
    assert '<p class="vsum-note">${excluded} Fälle zählen nicht mit: Der Kurs' in koerper
    assert "war schon in der Beobachtungszone, als sie auf die Liste kamen.</p>" in koerper


def test_details_fuer_nerds_erklaert_alle_sechs_status_einfach():
    koerper = _fn("openValidierung")
    for stichwort in ("<b>offen</b>", "<b>Extension</b>", "<b>Zone</b>",
                       "<b>invalidiert</b>", "<b>gereift · neutral</b>", "<b>ausgeschlossen</b>"):
        assert stichwort in koerper


def test_details_fuer_nerds_ohne_ergebnis_woerter():
    koerper = _fn("openValidierung")
    nerds_block = koerper[koerper.index("const nerds ="):]
    for verboten in ("Trefferquote", "Erfolgsquote"):
        assert verboten not in nerds_block


def test_was_noch_mitgemessen_wird_entfernt_nicht_nur_gekuerzt():
    koerper = _fn("openValidierung")
    assert "Was noch mitgemessen wird" not in koerper


def test_details_fuer_nerds_nennt_die_zwei_rechnungen():
    """Grundmethodik-Pflichtinhalt (Primär-/Sensitivitätsanalyse), s. Auftrag
    Punkt 5 — in einfacher Sprache ("Haupt-Rechnung"/"unterstützende
    Rechnung"), keine Fachbegriffe ohne Erklärung."""
    koerper = _fn("openValidierung")
    assert "Haupt-Rechnung" in koerper
    assert "unterstützende" in koerper


# ---------------------------------------------------------------------------
# (b) node: die Rechenkerne WIRKLICH ausgeführt
# ---------------------------------------------------------------------------
_NODE = shutil.which("node") or shutil.which("nodejs")
_RECORDS = json.loads((ROOT / "data/forward_collection.json").read_text(encoding="utf-8"))["records"]


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken dieselben Fälle")
    quelle = "\n".join([
        _fn("_recExcluded"),
        _fn("episodeStatus"),
        _konst_array("VSDIST_ORDER"),
        _konst_obj("VSDIST_COLOR"),
        _fn("fmtPct1"),
        _fn("esc"),
        _fn("statusDistribution"),
        _fn("statusDistributionHtml"),
    ])
    # Als Datei statt `-e`: die vollen 108 Records als JSON-Literal sprengen
    # das argv-Limit (`Argument list too long`) — die Datei hat keine solche
    # Grenze.
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(quelle + "\n" + script)
        pfad = f.name
    try:
        r = subprocess.run([_NODE, pfad], capture_output=True, text=True, timeout=60)
    finally:
        Path(pfad).unlink(missing_ok=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_verteilung_von_hand_nachgerechnet_gegen_echte_108_records():
    """Der Wert-Test aus dem Auftrag: mit dem committeten Stand von
    `data/forward_collection.json` (108 Records) von Hand nachgerechnet
    (Python, unabhängig von `statusDistribution`) und gegen den ECHTEN
    node-Lauf verglichen."""
    def rec_excluded(r):
        return bool(r.get("pre_reached_target") or r.get("pre_reached_ext") or r.get("pre_guard_contaminated"))

    def status(r):
        if r.get("invalidated") == 1:
            return "st-inval"
        if rec_excluded(r):
            return "st-excluded"
        if r.get("ext_hit") == 1:
            return "st-ext"
        if r.get("target_hit") == 1:
            return "st-target"
        if r.get("matured"):
            return "st-neutral"
        return "st-open"

    counts = {"st-open": 0, "st-ext": 0, "st-target": 0, "st-inval": 0, "st-neutral": 0, "st-excluded": 0}
    for r in _RECORDS:
        counts[status(r)] += 1
    total = len(_RECORDS)

    assert total == 108, f"Datensatz hat sich verändert ({total} statt 108) — Soll-Werte neu ziehen"
    assert counts == {
        "st-open": 23, "st-ext": 19, "st-target": 20,
        "st-inval": 17, "st-neutral": 24, "st-excluded": 5,
    }
    soll_pct = {cls: round(n / total * 1000) / 10 for cls, n in counts.items()}
    assert soll_pct == {
        "st-open": 21.3, "st-ext": 17.6, "st-target": 18.5,
        "st-inval": 15.7, "st-neutral": 22.2, "st-excluded": 4.6,
    }

    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      const dist = statusDistribution(records);
      const byClass = {{}};
      dist.forEach(d => {{ byClass[d.cls] = {{ n: d.n, pct: d.pct }}; }});
      console.log(JSON.stringify(byClass));
    """)
    for cls, n in counts.items():
        assert ergebnis[cls]["n"] == n, f"{cls}: node={ergebnis[cls]['n']} vs. Hand={n}"
        assert ergebnis[cls]["pct"] == soll_pct[cls], f"{cls}: node={ergebnis[cls]['pct']} vs. Hand={soll_pct[cls]}"


def test_summe_der_counts_ergibt_108():
    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      const dist = statusDistribution(records);
      console.log(JSON.stringify(dist.reduce((s, d) => s + d.n, 0)));
    """)
    assert ergebnis == 108


def test_gerenderter_balken_und_zeilen_zeigen_die_echten_zahlen():
    """DOM-/Snapshot-Test: die tatsächlich gerenderte HTML-Ausgabe enthält
    Name + Anzahl + Prozent für alle sechs Kategorien, mit den von Hand
    nachgerechneten Werten."""
    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      const html = statusDistributionHtml(records);
      console.log(JSON.stringify(html));
    """)
    for erwartet in (
        "offen <b>23</b> <em>21,3 %</em>",
        "Extension <b>19</b> <em>17,6 %</em>",
        "Zone <b>20</b> <em>18,5 %</em>",
        "invalidiert <b>17</b> <em>15,7 %</em>",
        "gereift · neutral <b>24</b> <em>22,2 %</em>",
        "ausgeschlossen <b>5</b> <em>4,6 %</em>",
    ):
        assert erwartet in ergebnis, f"fehlt im gerenderten HTML: {erwartet!r}"
    for verboten in ("Trefferquote", "Erfolgsquote"):
        assert verboten not in ergebnis


def test_leere_sammlung_ergibt_leeren_block_kein_kaputtes_html():
    ergebnis = _js("""
      console.log(JSON.stringify(statusDistributionHtml([])));
    """)
    assert ergebnis == ""
