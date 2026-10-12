"""Verlustbild (12.10.2026, Easy-Entscheid, Variante A) — analog zu #107/#123
(test_status_verteilung.py/test_r_werte_anzeige.py).

Easys Sicht: NUR "invalidiert" ist ein Verlust — Zone/Extension erreicht UND
gereift-neutral zählen für ihn positiv. NACHTRÄGLICH definiert (nach Kenntnis
des Primärergebnisses vom 06.09.2026), erklärend, KEIN Beleg.

DIAGNOSE/MINI-STOPP (11./12.10.2026): der Auftragssatz "Die Primärzeile
bleibt unverändert sichtbar" traf nicht zu — diese Zeile existierte im
Frontend bisher gar nicht (nur in `data/evaluation/ergebnis.json`, die das
Frontend nicht lädt). Easy-Entscheid (Option A): feste Textzeile neu
ergänzen (`primaerzeileHtml()`), keine neue Datei/kein Fetch.

VERBOTENE WÖRTER (Easy-Entscheid 12.10.2026): "Trefferquote"/"Erfolgsquote"/
"bestanden"/"signifikant"/"Signifikanz" bleiben verboten — bevorzugt eine
Formulierung ohne diese Wörter. Easy hat selbst "Erfolgs-Kriterien nicht
erfüllt" als Beispiel genannt (`primaerzeileHtml()`) — das einzige Vorkommen
von "Erfolg" in diesem Bereich, ausdrücklich von Easy freigegeben, NICHT
Teil der generischen Verbotsliste unten (die für `verlustbildHtml` gilt).

Zwei Netze (Muster aus test_r_werte_anzeige.py):
  (a) Literale/String-Anker.
  (b) node: `verlustbildPopulation()`/`verlustbildEimer()`/`verlustbildHtml()`
      WIRKLICH ausgeführt gegen die echten, AKTUELLEN Records — die Zahlen
      von Hand nachgerechnet (live gegen die Datei, KEIN eingefrorener
      Schnappschuss) UND gegen `scripts/evaluate_nicht_invalidiert.py`
      (`evaluate.build_population` + `neutrale_faelle`) gegengeprüft.
"""
from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# (a) Literale/String-Anker
# ---------------------------------------------------------------------------
def test_verlustbildpopulation_nutzt_dieselbe_regel_wie_evaluate_build_population():
    koerper = _fn("verlustbildPopulation")
    assert "r.matured" in koerper
    assert "!_recExcluded(r)" in koerper
    assert "Number.isFinite(r.score_heuristic)" in koerper
    assert "(r.target_hit === 0 || r.target_hit === 1)" in koerper


def test_verlustbildeimer_nutzt_bewusst_nicht_episodestatus():
    """Diagnose 12.10.2026 (Mini-Stopp-würdiger Fund, hier dokumentiert statt
    versteckt): `episodeStatus()` zählt `ext_hit === 1` ODER
    `target_hit === 1` als Zone/Extension — ein realer Fall (MA,
    2026-08-19) hat `ext_hit=1` bei `target_hit=0` ohne Guard-Beteiligung,
    dadurch würde die Wiederverwendung von `episodeStatus()` einen Fall MEHR
    als 'zone' zählen (62 statt 61) als `scripts/evaluate_nicht_invalidiert.
    py` (dessen `hit`-Feld exakt `target_hit` ist). Easy verlangt
    Übereinstimmung mit dem Skript — deshalb hier bewusst NICHT
    `episodeStatus()`, sondern `target_hit` allein."""
    koerper = _fn("verlustbildEimer")
    assert "episodeStatus" not in koerper
    assert "r.target_hit === 1" in koerper


def test_verlustbildeimer_prueft_invalidiert_vor_zone():
    koerper = _fn("verlustbildEimer")
    assert koerper.index("r.invalidated === 1") < koerper.index("r.target_hit === 1")


def test_verlustbildeimer_regression_ext_hit_ohne_target_hit_zaehlt_als_abgelaufen():
    """Der konkrete Fund: MA/2026-08-19 (ext_hit=1, target_hit=0,
    invalidated=0, keine Guards) muss als 'abgelaufen' zählen, NICHT als
    'zone' — exakt wie `scripts/evaluate_nicht_invalidiert.py`s `hit`-Feld
    (= target_hit) es werten würde."""
    treffer = [r for r in _RECORDS
              if r.get("ticker") == "MA" and r.get("first_seen_date") == "2026-08-19"]
    if not treffer:
        pytest.skip("MA/2026-08-19 nicht (mehr) in der Sammlung — Fund war Stand 12.10.2026")
    ma_fall = treffer[0]
    assert ma_fall.get("target_hit") == 0
    assert ma_fall.get("ext_hit") == 1
    assert ma_fall.get("invalidated") == 0


def test_vbild_ist_lazy_gegen_fehlende_sammlung_kein_rauschen():
    koerper = _fn("verlustbildHtml")
    assert "if (!Array.isArray(records) || !records.length) return '';" in koerper
    assert "if (!pop.length) return '';" in koerper


def test_vbild_sitzt_zwischen_rwerte_und_den_drei_kennzahlen_ohne_aufklappen():
    koerper = _fn("openValidierung", tiefe="    ")
    rwerte_pos = koerper.index("rWerteHtml(records)")
    verlust_pos = koerper.index("verlustbildHtml(records)")
    hero_pos = koerper.index("vsum-hero")
    assert rwerte_pos < verlust_pos < hero_pos, (
        "Verlustbild muss zwischen R-Werten und den drei bestehenden "
        "Kennzahlen eingefügt werden")
    block = koerper[koerper.index("head =") - 5:hero_pos]
    assert "<details" not in block


def test_verlust_variable_wird_in_beiden_zweigen_eingebunden():
    koerper = _fn("openValidierung")
    assert koerper.count("${verlust}") == 2  # _val-Zweig UND _reportOnly-Zweig


def test_drei_eimer_bezeichnungen_wie_im_auftrag():
    """ANGEPASST (12.10.2026, Easy-Fund B): Label ehrlich gemacht —
    "Zone/Extension erreicht" → "Ziel-Zone erreicht", weil der Eimer nur
    `target_hit` zählt (s. `verlustbildEimer()`), nicht `ext_hit` — die
    alte Beschriftung suggerierte fälschlich, Extension zähle mit."""
    koerper = _fn("verlustbildHtml")
    assert "Ziel-Zone erreicht" in koerper
    assert "Zone/Extension erreicht" not in koerper
    # Im Quelltext per String-Konkatenation über zwei Zeilen gebrochen
    # (ergibt zur Laufzeit "abgelaufen (weder Ziel noch Stopp)" — geprüft im
    # node-Test unten gegen den tatsächlich gerenderten Text).
    assert "abgelaufen (weder Ziel " in koerper
    assert "noch Stopp)" in koerper
    assert "invalidiert" in koerper
    assert "im Minus am Tag 10" in koerper


def test_schraffur_ist_reines_css_kein_neues_bild():
    koerper = _fn("verlustbildHtml")
    assert "repeating-linear-gradient" in koerper
    assert ".png" not in koerper and ".svg" not in koerper and "url(" not in koerper


def test_kein_erfolgs_gruen_fuer_abgelaufen_nur_fuer_zone():
    """GRENZEN: kein Erfolgs-Grün für 'nicht invalidiert' — nur der echte
    Ziel-Zone-Treffer bleibt grün (st-target), 'abgelaufen' bekommt die
    neutrale Farbe (st-neutral), nicht st-target/st-ext."""
    koerper = _fn("verlustbildHtml")
    zone_zeile = [z for z in koerper.splitlines() if "titel: `Ziel-Zone erreicht" in z][0]
    abgelaufen_zeile = [z for z in koerper.splitlines()
                        if "weder Ziel noch Stopp:" in z and "titel" in z][0]
    assert "st-target" in koerper[:koerper.index(zone_zeile) + len(zone_zeile)]
    assert "st-neutral" in abgelaufen_zeile or "'st-neutral'" in koerper


def test_abweichungs_hinweis_zur_status_verteilung_vorhanden():
    """Easy-Fund B: die Status-Verteilung oben trennt Zone/Extension und
    zählt alle gesammelten Fälle, das Verlustbild nur `target_hit` auf der
    auswertbaren Population — deshalb weichen Zahlen um einzelne Fälle ab
    (konkret: MA/2026-08-19, s. test_verlustbildeimer_regression_*). Diese
    Erklärung muss sichtbar sein, nicht nur im Code-Kommentar."""
    koerper = _fn("verlustbildHtml")
    assert "Zählt nur Ziel-Zone erreicht" in koerper
    assert "wie im Auswertungsskript" in koerper
    assert "weichen Zahlen um einzelne Fälle ab" in koerper


def test_pflichttext_vorhanden_wortgetreu():
    """ANGEPASST (12.10.2026, Easy-Fund A): Pflichttext gekürzt — der
    einleitende Satz "Nachträglich definierte Sicht (nach Kenntnis des
    Primärergebnisses vom 06.09.2026)." entfällt, weil "nachträglich" dann
    doppelt stand (Chip UND Pflichttext). Das Datum steht weiterhin in der
    Primärzeile, die Transparenz bleibt über den Chip gewahrt (s.
    test_nachtraeglich_kommt_im_verlustbild_block_genau_einmal_vor)."""
    koerper = _fn("verlustbildHtml")
    assert ("Ersetzt die Primärwertung nicht.\n            Über die Hälfte "
           "der abgelaufenen Fälle steht am Tag 10 im Minus.") in koerper
    assert "Nachträglich definierte Sicht" not in koerper


def test_nachtraeglich_kommt_im_verlustbild_block_genau_einmal_vor():
    """Easy-Fund A: "nachträglich" stand doppelt (Chip + Pflichttext) —
    jetzt genau einmal, im Chip."""
    koerper = _fn("verlustbildHtml")
    assert koerper.lower().count("nachträglich") == 1
    assert "nachträglich definiert · explorativ · kein Beleg" in koerper


def test_min_n_hinweis_nutzt_dieselbe_schwelle_wie_evaluate_nicht_invalidiert():
    assert "VERLUSTBILD_MIN_N = 30" in _konst_simple("VERLUSTBILD_MIN_N")
    assert eni.SECONDARY_MIN_N == 30
    koerper = _fn("verlustbildHtml")
    assert "n < VERLUSTBILD_MIN_N" in koerper


def test_kein_zufallsvergleich_im_verlustbild():
    """Auftrag: kein Zufallsvergleich auf der Seite (braucht die Kursdatei,
    nicht im Repo)."""
    koerper = _fn("verlustbildHtml")
    for verboten in ("Zufall", "p_wert", "p-Wert", "Perzentil"):
        assert verboten not in koerper


def test_keine_erfolgs_oder_wahrscheinlichkeits_woerter_im_verlustbild():
    """Leitplanke (Auftrag + bestehende Tests einhalten): dieselben Wörter,
    die test_r_werte_anzeige.py/test_status_verteilung.py bereits verbieten
    — geprüft am tatsächlich ERZEUGTEN Text (Quelltext-Kommentare dürfen das
    Wort 'Erfolg' nennen, z. B. 'kein neues Erfolgs-Grün' — das ist keine
    Nutzer-Ausgabe; node-Test unten prüft den gerenderten Text zusätzlich)."""
    for fn_name in ("verlustbildPopulation", "verlustbildEimer", "verlustbildHtml"):
        block = _fn(fn_name)
        for verboten in ("Trefferquote", "Erfolgsquote", "bestanden",
                        "signifikant", "Signifikanz", "Wahrscheinlichkeit"):
            assert verboten not in block, f"'{verboten}' in {fn_name}"


# ---------------------------------------------------------------------------
# Primärzeile — fester Text, UNABHÄNGIG von records/_val (Easy-Entscheid A)
# ---------------------------------------------------------------------------
def test_primaerzeile_wird_immer_angehaengt_unabhaengig_von_records():
    assert ("innerHTML = primaerzeileHtml() + head + nerds;") in HTML


def test_primaerzeile_nennt_die_eingefrorene_zahl_und_grenzt_klar_ab():
    koerper = _fn("primaerzeileHtml")
    assert "06.09.2026" in koerper
    assert "44,6" in koerper
    assert "n=101" in koerper
    assert "Erfolgs-Kriterien nicht erfüllt" in koerper
    assert "kein Vergleich" in koerper
    assert "Andere Fallbasis" in koerper or "andere Fallbasis" in koerper


def test_primaerzeile_vermeidet_die_generisch_verbotenen_woerter():
    """Easy-Entscheid 12.10.2026: 'Erfolgs-Kriterien' ist ausdrücklich
    erlaubt (Easys eigenes Beispiel) — die übrigen verbotenen Wörter bleiben
    trotzdem verboten, auch hier."""
    koerper = _fn("primaerzeileHtml")
    for verboten in ("Trefferquote", "Erfolgsquote", "bestanden",
                    "signifikant", "Signifikanz", "Wahrscheinlichkeit"):
        assert verboten not in koerper, f"'{verboten}' in primaerzeileHtml"


def test_primaerzeile_eigener_rahmen_getrennt_vom_verlustbild():
    koerper = _fn("primaerzeileHtml")
    assert "vbild-primaer" in koerper
    assert "class=\"vbild\"" not in koerper  # nicht dieselbe CSS-Box wie der Balken


# ---------------------------------------------------------------------------
# Mutationsprobe — eine ABSICHTLICH FALSCHE Variante, die sich vom echten
# Ergebnis unterscheiden MUSS (sonst wäre die Testabdeckung Theater).
# ---------------------------------------------------------------------------
def test_mutationsprobe_invalidiert_faelschlich_als_zone_gezaehlt():
    """Eine kaputte Variante, die `target_hit` VOR `invalidated` prüft,
    würde einen Fall, der laut Tie-Break-Regel eigentlich invalidiert ist
    (aber zufällig `target_hit`/`ext_hit` gesetzt hat — kommt laut
    `forward_collection.mature_record` nicht vor, s. Moduldoc Tie-Break),
    FÄLSCHLICH als 'Zone' werten. Konkret und ohne Spekulation über reale
    Daten geprüft: ein synthetischer Fall mit `invalidated=1` UND
    `target_hit=1` gleichzeitig — nur über eine fehlerhafte Prioritäts-
    Reihenfolge möglich, zeigt die Mutation sofort den Unterschied."""
    fall = {"invalidated": 1, "target_hit": 1, "ext_hit": 0, "matured": True,
           "pre_reached_target": False, "pre_reached_ext": False,
           "pre_guard_contaminated": False}

    def echter_status(r):
        if r.get("invalidated") == 1:
            return "invalidiert"
        if r.get("target_hit") == 1 or r.get("ext_hit") == 1:
            return "zone"
        return "abgelaufen"

    def kaputter_status_target_hit_vor_invalidiert(r):
        if r.get("target_hit") == 1 or r.get("ext_hit") == 1:
            return "zone"
        if r.get("invalidated") == 1:
            return "invalidiert"
        return "abgelaufen"

    echt = echter_status(fall)
    kaputt = kaputter_status_target_hit_vor_invalidiert(fall)
    assert echt == "invalidiert"
    assert kaputt == "zone"
    assert echt != kaputt


# ---------------------------------------------------------------------------
# (b) node: die Rechenkerne WIRKLICH ausgeführt, gegen scripts/
# evaluate_nicht_invalidiert.py gegengeprüft.
# ---------------------------------------------------------------------------
_NODE = shutil.which("node") or shutil.which("nodejs")


def _js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken dieselben Fälle")
    quelle = "\n".join([
        _fn("_recExcluded"),
        _fn("episodeStatus"),
        _konst_obj("VSDIST_COLOR"),
        _konst_simple("VERLUSTBILD_MIN_N"),
        _fn("fmtPct1"),
        _fn("esc"),
        _fn("verlustbildPopulation"),
        _fn("verlustbildEimer"),
        _fn("verlustbildHtml"),
        _fn("primaerzeileHtml"),
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


def _soll_verlustbild():
    """Von Hand nachgerechnet gegen `scripts/evaluate_nicht_invalidiert.py`
    selbst (NICHT nur eine Python-Abschrift der JS-Logik) — IMMER gegen den
    aktuell committeten `data/forward_collection.json`-Stand, wie bei
    #107/#123 (die Sammlung wächst fortlaufend)."""
    cases, _zaehlwerk = ev.build_population(_COLL)
    n = len(cases)
    inval = sum(1 for c in cases if c["rec"]["invalidated"])
    zone = sum(1 for c in cases if c["hit"] and not c["rec"]["invalidated"])
    neutral = eni.neutrale_faelle(cases)
    minus = sum(
        1 for c in neutral
        if (c["rec"].get("r_erreicht_basis") or 0) < 0
        and c["rec"].get("r_erreicht_basis") is not None)
    assert zone + len(neutral) + inval == n
    return n, zone, len(neutral), inval, minus


def test_population_groesse_stimmt_mit_evaluate_build_population_ueberein():
    n, *_rest = _soll_verlustbild()
    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      console.log(JSON.stringify(verlustbildPopulation(records).length));
    """)
    assert ergebnis == n


def test_drei_eimer_zahlen_stimmen_mit_evaluate_nicht_invalidiert_ueberein():
    """Der Wert-Test aus dem Auftrag: 157/61/63/33/34 (heutiger Stand) —
    hier NICHT hartkodiert, sondern live gegen die echte Datei UND das echte
    Skript nachgerechnet (dieselbe Lehre wie bei #107: ein hartkodierter
    Soll-Wert würde morgen grundlos rot)."""
    n, zone, neutral, inval, minus = _soll_verlustbild()

    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      const pop = verlustbildPopulation(records);
      let zone = 0, abgelaufen = 0, abgelaufenMinus = 0, inval = 0;
      pop.forEach(r => {{
        const eimer = verlustbildEimer(r);
        if (eimer === 'zone') zone++;
        else if (eimer === 'invalidiert') inval++;
        else {{
          abgelaufen++;
          if (r.r_erreicht_basis != null && r.r_erreicht_basis < 0) abgelaufenMinus++;
        }}
      }});
      console.log(JSON.stringify({{
        n: pop.length, zone, abgelaufen, abgelaufenMinus, inval
      }}));
    """)
    assert ergebnis["n"] == n
    assert ergebnis["zone"] == zone
    assert ergebnis["abgelaufen"] == neutral
    assert ergebnis["abgelaufenMinus"] == minus
    assert ergebnis["inval"] == inval


def test_gerenderter_balken_zeigt_die_echten_zahlen():
    n, zone, neutral, inval, minus = _soll_verlustbild()

    def fmt1(x):
        pct = round(x / n * 1000) / 10 if n else 0
        return f"{pct:.1f}".replace(".", ",")

    ergebnis = _js(f"""
      const records = {json.dumps(_RECORDS)};
      console.log(JSON.stringify(verlustbildHtml(records)));
    """)
    assert f"Ziel-Zone erreicht <b>{zone}</b> <em>{fmt1(zone)} %</em>" in ergebnis
    assert f"abgelaufen (weder Ziel noch Stopp) <b>{neutral}</b> <em>{fmt1(neutral)} %</em>" in ergebnis
    assert f"davon im Minus am Tag 10 <b>{minus}</b> <em>{fmt1(minus)} %</em>" in ergebnis
    assert f"invalidiert <b>{inval}</b> <em>{fmt1(inval)} %</em>" in ergebnis
    assert f"(n={n})" in ergebnis
    for verboten in ("Trefferquote", "Erfolgsquote", "bestanden", "signifikant",
                    "Signifikanz", "Wahrscheinlichkeit", "Erfolg"):
        assert verboten not in ergebnis


def test_primaerzeile_gerendert_enthaelt_die_feste_zahl():
    ergebnis = _js("""
      console.log(JSON.stringify(primaerzeileHtml()));
    """)
    assert "44,6" in ergebnis
    assert "n=101" in ergebnis
    assert "06.09.2026" in ergebnis
    assert "Erfolgs-Kriterien nicht erfüllt" in ergebnis


def test_leere_sammlung_ergibt_leeren_block_kein_kaputtes_html():
    ergebnis = _js("""
      console.log(JSON.stringify(verlustbildHtml([])));
    """)
    assert ergebnis == ""


def test_mutationsprobe_node_invalidiert_als_zone_gezaehlt_aendert_das_ergebnis():
    """Dieselbe Mutationsprobe wie oben, aber WIRKLICH in Node gegen die
    echte `verlustbildEimer()`-Reihenfolge laufen lassen: eine kaputte
    Variante, die `target_hit` vor `invalidated` prüft, muss beim
    synthetischen Randfall (invalidiert UND target_hit gleichzeitig) ein
    ANDERES Ergebnis liefern als die echte Funktion."""
    fall = {"invalidated": 1, "target_hit": 1, "ext_hit": 0, "matured": True,
           "score_heuristic": 80.0,
           "pre_reached_target": False, "pre_reached_ext": False,
           "pre_guard_contaminated": False}
    ergebnis = _js(f"""
      const fall = {json.dumps(fall)};
      const echt = verlustbildEimer(fall);
      function kaputt(r) {{
        if (r.target_hit === 1 || r.ext_hit === 1) return 'zone';
        if (r.invalidated === 1) return 'invalidiert';
        return 'abgelaufen';
      }}
      console.log(JSON.stringify({{ echt, kaputt: kaputt(fall) }}));
    """)
    assert ergebnis["echt"] == "invalidiert"
    assert ergebnis["kaputt"] == "zone"
    assert ergebnis["echt"] != ergebnis["kaputt"]
