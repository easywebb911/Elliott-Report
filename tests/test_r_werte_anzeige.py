"""R-Werte-Anzeige (07.09.2026, Easy-Wunsch) — analog zu #107
(test_status_verteilung.py), aber für die additiven R-Multiple-Felder aus
PR #122 (risiko_abstand/chance_abstand_*/crv_*/r_erreicht_*, siehe
docs/validation_registry.md, Eintrag 06.09.2026).

Neuer Block "R-Werte (Zwischenstand)" im Validierung-Hauptbereich
(`openValidierung()`), direkt unter der bestehenden Status-Verteilung: Ø
`r_erreicht_basis`/`r_erreicht_extension` und die Kategorien-Verteilung
darunter — REIN deskriptiv, KEIN Zufalls-Benchmark, KEINE Signifikanz, KEIN
Bezug zur bereits abgeschlossenen #121-Auswertung.

Rückfrage-Ergebnis (Mini-Stopp vor der Umsetzung): 6 von 103 Episoden mit
`r_erreicht_basis != null` sind PRU-Guard-ausgeschlossen (`pre_reached_target`/
`_ext`/`pre_guard_contaminated` — Zone schon bei Anlage erreicht,
`target_hit` dort strukturell gesperrt, kann also NIE `+crv_basis` zeigen).
Easy hat entschieden: dieselbe `_recExcluded()`-Ausschlusslogik wie bei #121
anwenden (nicht alle 103 einbeziehen) — Population also 97 Fälle, nicht 103.

Zwei Netze (Muster aus test_status_verteilung.py):
  (a) Literale/String-Anker.
  (b) node: `rWertePopulation()`/`rWerteHtml()` WIRKLICH ausgeführt gegen die
      echten, AKTUELLEN Records — der Durchschnitt von Hand nachgerechnet
      (`_soll_rwerte()`, live gegen die Datei, KEIN eingefrorener
      Schnappschuss — dieselbe Begründung wie bei #107).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
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
def test_rwertepopulation_nutzt_recexcluded_dieselbe_quelle_wie_121():
    koerper = _fn("rWertePopulation")
    assert "!_recExcluded(r)" in koerper
    assert "r.r_erreicht_basis != null" in koerper


def test_kategorien_sind_die_vier_relevanten_ohne_offen_und_ausgeschlossen():
    ordnung = _konst_array("RWERTE_CATS")
    assert "['st-ext', 'Extension']" in ordnung
    assert "['st-target', 'Zone']" in ordnung
    assert "['st-inval', 'invalidiert']" in ordnung
    assert "['st-neutral', 'gereift · neutral']" in ordnung
    assert "st-open" not in ordnung
    assert "st-excluded" not in ordnung


def test_rwerte_block_ist_lazy_gegen_fehlende_oder_leere_population():
    koerper = _fn("rWerteHtml")
    assert "if (!Array.isArray(records) || !records.length) return '';" in koerper
    assert "if (!pop.length) return '';" in koerper


def test_rwerte_sitzt_direkt_unter_der_statusverteilung_ohne_aufklappen():
    koerper = _fn("openValidierung", tiefe="    ")
    dist_pos = koerper.index("statusDistributionHtml")
    rwerte_pos = koerper.index("rWerteHtml")
    hero_pos = koerper.index("vsum-hero")
    assert dist_pos < rwerte_pos < hero_pos, (
        "R-Werte-Block muss zwischen Status-Verteilung und den drei "
        "bestehenden Kennzahlen eingefügt werden")
    block = koerper[koerper.index("head =") - 5:hero_pos]
    assert "<details" not in block


def test_keine_ergebnis_woerter_im_rwerte_block():
    """Leitplanke aus dem Auftrag: keine Erfolgs-/Signifikanz-Sprache."""
    rwerte_block = _fn("rWerteHtml")
    for verboten in ("Erfolgsquote", "bestanden", "signifikant", "Signifikanz"):
        assert verboten not in rwerte_block, f"'{verboten}' in rWerteHtml"


def test_heuristisch_unvalidiert_bleibt_sichtbar_im_rwerte_block():
    rwerte_block = _fn("rWerteHtml")
    assert '<span class="vsum-stamp">heuristisch · unvalidiert</span>' in rwerte_block


def test_rwerte_nennt_die_abgrenzung_zur_121_auswertung():
    rwerte_block = _fn("rWerteHtml")
    assert "Noch keine" in rwerte_block and "offizielle Auswertung" in rwerte_block
    assert "Trefferquoten-Auswertung" in rwerte_block


def test_ausschluss_hinweis_erscheint_nur_wenn_es_etwas_zu_melden_gibt():
    koerper = _fn("rWerteHtml")
    assert "const excl = records.length - pop.length;" in koerper
    assert "excl > 0" in koerper


# ---------------------------------------------------------------------------
# Regression: bestehende Status-Verteilung (#107) unverändert
# ---------------------------------------------------------------------------
def test_bestehende_statusverteilung_unveraendert():
    ordnung = _konst_array("VSDIST_ORDER")
    for eintrag in ("['st-open', 'offen']", "['st-ext', 'Extension']",
                    "['st-target', 'Zone']", "['st-inval', 'invalidiert']",
                    "['st-neutral', 'gereift · neutral']", "['st-excluded', 'ausgeschlossen']"):
        assert eintrag in ordnung
    koerper = _fn("openValidierung")
    assert "<b>${collected}</b><span>gesammelt</span>" in koerper
    assert "<b>${matured}</b><span>fertig beobachtet</span>" in koerper
    assert "<b>${evaluable}</b><span>auswertbar</span>" in koerper


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
        _konst_obj("VSDIST_COLOR"),
        _fn("esc"),
        _fn("rWertePopulation"),
        _konst_array("RWERTE_CATS"),
        _fn("fmtR"),
        _fn("rWerteHtml"),
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(quelle + "\n" + script)
        pfad = f.name
    try:
        r = subprocess.run([_NODE, pfad], capture_output=True, text=True, timeout=60)
    finally:
        Path(pfad).unlink(missing_ok=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _rec_excluded(r):
    return bool(r.get("pre_reached_target") or r.get("pre_reached_ext") or r.get("pre_guard_contaminated"))


def _status(r):
    if r.get("invalidated") == 1:
        return "st-inval"
    if _rec_excluded(r):
        return "st-excluded"
    if r.get("ext_hit") == 1:
        return "st-ext"
    if r.get("target_hit") == 1:
        return "st-target"
    if r.get("matured"):
        return "st-neutral"
    return "st-open"


def _rwerte_population():
    return [r for r in _RECORDS if r.get("r_erreicht_basis") is not None and not _rec_excluded(r)]


def _soll_rwerte():
    """Von Hand nachgerechnet (Python, unabhängig von `rWerteHtml`) — IMMER
    gegen den aktuell committeten `data/forward_collection.json`-Stand, wie
    bei #107 (die Sammlung wächst fortlaufend, ein hartkodierter Soll-Wert
    würde am nächsten Cron-Lauf veralten)."""
    pop = _rwerte_population()
    n = len(pop)
    avg_basis = sum(r["r_erreicht_basis"] for r in pop) / n if n else None
    avg_ext = sum(r["r_erreicht_extension"] for r in pop) / n if n else None
    counts = {"st-ext": 0, "st-target": 0, "st-inval": 0, "st-neutral": 0}
    for r in pop:
        counts[_status(r)] += 1
    return pop, n, avg_basis, avg_ext, counts


def _fmt_r(n):
    if n == 0:
        return "0,00 R"
    zeichen = "+" if n > 0 else "-"
    return f"{zeichen}{abs(n):.2f}".replace(".", ",") + " R"


def test_population_schliesst_genau_die_pru_guard_faelle_aus():
    """Der konkrete Rückfrage-Fall: 103 Episoden haben r_erreicht_basis
    != null, aber 6 davon sind PRU-Guard-ausgeschlossen -> Population 97."""
    mit_r = [r for r in _RECORDS if r.get("r_erreicht_basis") is not None]
    pop, n, _avg_basis, _avg_ext, _counts = _soll_rwerte()
    assert len(mit_r) - n == len([r for r in mit_r if _rec_excluded(r)])
    assert n == len(mit_r) - len([r for r in mit_r if _rec_excluded(r)])

    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      console.log(JSON.stringify(rWertePopulation(records).length));
    """)
    assert ergebnis == n


def test_durchschnitt_von_hand_nachgerechnet_gegen_echte_records():
    """Der Wert-Test aus dem Auftrag."""
    _pop, n, soll_basis, soll_ext, _counts = _soll_rwerte()
    if n == 0:
        pytest.skip("keine Population — Auftrag verlangt Test nur bei Daten")

    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      const pop = rWertePopulation(records);
      const avgBasis = pop.reduce((s, r) => s + r.r_erreicht_basis, 0) / pop.length;
      const avgExt = pop.reduce((s, r) => s + r.r_erreicht_extension, 0) / pop.length;
      console.log(JSON.stringify({{ n: pop.length, avgBasis, avgExt }}));
    """)
    assert ergebnis["n"] == n
    assert round(ergebnis["avgBasis"], 8) == round(soll_basis, 8)
    assert round(ergebnis["avgExt"], 8) == round(soll_ext, 8)


def test_kategorien_verteilung_stimmt_und_summiert_sich_zur_population():
    _pop, n, _avg_basis, _avg_ext, soll_counts = _soll_rwerte()
    assert sum(soll_counts.values()) == n

    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      const pop = rWertePopulation(records);
      const counts = {{ 'st-ext': 0, 'st-target': 0, 'st-inval': 0, 'st-neutral': 0 }};
      pop.forEach(r => {{ const cls = episodeStatus(r).cls; if (cls in counts) counts[cls]++; }});
      console.log(JSON.stringify(counts));
    """)
    assert ergebnis == soll_counts


def test_gerenderter_block_zeigt_die_echten_durchschnittswerte_und_kategorien():
    """DOM-/Snapshot-Test: die tatsächlich gerenderte HTML-Ausgabe enthält
    die von Hand nachgerechneten Ø-Werte, das n und alle vier Kategorien."""
    _pop, n, soll_basis, soll_ext, soll_counts = _soll_rwerte()
    if n == 0:
        pytest.skip("keine Population — Auftrag verlangt Test nur bei Daten")

    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      const html = rWerteHtml(records);
      console.log(JSON.stringify(html));
    """)
    assert f">{_fmt_r(soll_basis)}<" in ergebnis
    assert f">{_fmt_r(soll_ext)}<" in ergebnis
    assert f"über {n} Fälle mit ermittelbarem R" in ergebnis
    label = {"st-ext": "Extension", "st-target": "Zone", "st-inval": "invalidiert",
            "st-neutral": "gereift · neutral"}
    for cls, n_cls in soll_counts.items():
        assert f"{label[cls]} <b>{n_cls}</b>" in ergebnis
    for verboten in ("Erfolgsquote", "bestanden", "signifikant", "Signifikanz"):
        assert verboten not in ergebnis


def test_leere_sammlung_ergibt_leeren_block_kein_kaputtes_html():
    ergebnis = _js("""
      console.log(JSON.stringify(rWerteHtml([])));
    """)
    assert ergebnis == ""
