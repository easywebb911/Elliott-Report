"""Trade-Journal — die HARTEN Regeln, maschinell geprüft.

Das Journal ist eine eigene Handels-Aufzeichnung. Es darf die Validierung
**nicht berühren**: die Pipeline liest die Datei nie, Score/Ranking/Filter/
Reifung/Sammlung bleiben unverändert. Und es darf **keine Beträge und keine
Stückzahlen** kennen — das Repo ist öffentlich.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import forward_collection as fc  # noqa: E402

HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")
JOURNAL_DATEI = "trade_journal.json"


# ---------------------------------------------------------------------------
# 1 · STRIKT GETRENNT VON DER VALIDIERUNG
# ---------------------------------------------------------------------------
def test_kein_python_modul_kennt_die_journal_datei():
    """Weder Pipeline noch Sammlung noch Auswertung fassen sie an."""
    treffer = []
    for f in sorted((ROOT / "scripts").glob("*.py")) + [ROOT / "config.py"]:
        if JOURNAL_DATEI in f.read_text(encoding="utf-8"):
            treffer.append(f.name)
    assert not treffer, f"Journal-Datei im Backend referenziert: {treffer}"


def test_kein_workflow_fasst_die_journal_datei_an():
    for wf in (ROOT / ".github/workflows").glob("*.yml"):
        assert JOURNAL_DATEI not in wf.read_text(encoding="utf-8"), wf.name


def test_pipeline_lauf_mit_journal_datei_aendert_nichts(tmp_path, monkeypatch):
    """Ein Lauf MIT vorhandener Journal-Datei erzeugt denselben Report und
    dieselbe Sammlung wie einer ohne. Byte-für-Byte."""
    import elliott_pipeline as pipe
    import health_check as hc

    def lauf(mit_journal: bool):
        wd = tmp_path / ("mit" if mit_journal else "ohne")
        (wd / "data").mkdir(parents=True)
        (wd / "docs/data").mkdir(parents=True)
        (wd / "data/forward_collection.json").write_text(
            json.dumps({"schema_version": 1, "records": []}), encoding="utf-8")
        if mit_journal:
            # Ein realistisch befülltes Journal — es darf schlicht egal sein.
            (wd / "data/trade_journal.json").write_text(json.dumps([{
                "id": "tj_x", "ticker": "AAPL", "market": "US",
                "direction": "long", "entry_date": "2026-07-01",
                "entry_price": 100.0, "status": "geschlossen",
                "exit_date": "2026-07-20", "exit_price": 110.0,
                "note": "Test", "tool": {"setup": "Ende W4", "score": 88.0,
                                         "target_zone": {"low": 1, "high": 2},
                                         "invalidation": 90.0,
                                         "report_utc": "2026-07-01T00:00:00Z"}}]),
                encoding="utf-8")
        monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
        monkeypatch.delenv("NTFY_TOPIC", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(pipe, "REPO_ROOT", wd)
        monkeypatch.setattr(fc, "REPO_ROOT", wd)
        monkeypatch.setattr(hc, "REPO_ROOT", wd)
        monkeypatch.setattr(pipe.config, "MARKETS", {
            "US": {"label": "USA", "universe": ["AAPL", "MSFT"]},
            "DE": {"label": "Deutschland", "universe": ["SAP.DE"]},
        })
        monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
        assert pipe.main() == 0
        rep = json.loads((wd / "data/report.json").read_text(encoding="utf-8"))
        coll = json.loads((wd / "data/forward_collection.json").read_text("utf-8"))
        # Zeitstempel sind pro Lauf verschieden — sie sagen nichts über das Journal.
        for k in ("run_timestamp_utc", "generated_in_seconds"):
            rep.pop(k, None)
        # BERICHTIGUNG (04.08.2026): hier stand `checked_at` — ein Feld, das es
        # nicht gibt. Der Health-Block trägt `checked_utc`, und das ist derselbe
        # Zeitstempel wie `run_timestamp_utc`. Der Pop war also ein No-op, und
        # der Test wurde immer dann rot, wenn die beiden Pipeline-Läufe über
        # eine SEKUNDENGRENZE fielen (~5 % der Durchläufe). Vorbestehend, beim
        # Kurs-Stand-Wächter aufgefallen.
        (rep.get("health") or {}).pop("checked_utc", None)
        # Ebenfalls lauf-zeitabhängig (04.08.2026): der erwartete Handelstag
        # und der Rückstand leiten sich aus dem Lauf-Datum ab und würden über
        # eine MITTERNACHTS-Grenze auseinanderlaufen. Sie haben eigene Tests
        # (tests/test_kursstand_waechter.py) und sagen nichts über das Journal.
        for m in (rep.get("markets") or {}).values():
            for k in ("expected_bar_date", "bar_lag_trading_days"):
                (m.get("diag") or {}).pop(k, None)
        coll.pop("updated_utc", None)
        for r in coll.get("records", []):
            r.pop("created_utc", None)
            r.pop("last_update_utc", None)
        return rep, coll

    rep_ohne, coll_ohne = lauf(False)
    rep_mit, coll_mit = lauf(True)
    assert rep_mit == rep_ohne, "Report unterscheidet sich, wenn ein Journal existiert"
    assert coll_mit == coll_ohne, "Sammlung unterscheidet sich"
    # und die Journal-Datei selbst wurde nicht angefasst
    p = tmp_path / "mit/data/trade_journal.json"
    assert json.loads(p.read_text(encoding="utf-8"))[0]["ticker"] == "AAPL"


def test_es_gibt_genau_EINE_journal_ablage():
    """EIN Commit pro Änderung (30.07.2026): nur die Datei, die die Seite lädt.

    Die kanonische Kopie unter `data/` ist entfallen — sie hatte keinen Leser
    (per Netzwerk-Mitschnitt belegt: die Seite fragt genau
    `data/trade_journal.json` relativ zu /docs ab, also den docs-Spiegel).
    """
    gelesen = ROOT / "docs/data/trade_journal.json"
    # BERICHTIGT 31.07.2026: hier stand `== []`. Das war eine Aussage über den
    # INHALT, nicht über die Ablage — und sie wurde rot, sobald Easy den ersten
    # echten Eintrag anlegte (Commit „Update trade_journal.json"). Geprüft wird
    # jetzt, was der Test meint: EINE Datei, gültige Liste, keine zweite Ablage.
    assert isinstance(json.loads(gelesen.read_text(encoding="utf-8")), list)
    assert not (ROOT / "data/trade_journal.json").exists(), \
        "die kanonische Kopie ist wieder da — das wären zwei Commits pro Änderung"


# ---------------------------------------------------------------------------
# 2 · KEINE BETRÄGE, KEINE STÜCKZAHLEN
# ---------------------------------------------------------------------------
def _journal_js() -> str:
    i = HTML.index("TRADE-JOURNAL — eigene Handels-Aufzeichnung")
    j = HTML.index("const GH_OWNER", i)
    return HTML[i:j] + HTML[HTML.index("function tjAddBtn"):
                            HTML.index("function tjAddBtn") + 1200]


# Wortweise geprüft (nicht als Teilstring): `$` steckt in jedem
# Template-Literal, „eur" in „neuer" — Teilstring-Suche wäre hier nur Lärm.
VERBOTEN = [
    "betrag", "betraege", "beträge", "kapital", "invest", "investiert",
    "stueck", "stück", "stueckzahl", "stückzahl", "anzahl", "menge",
    "position_size", "positionsgroesse", "positionsgröße", "shares",
    "quantity", "qty", "amount", "gewinn_abs", "verlust_abs",
    "einsatz", "depot", "order", "volume", "lots",
]


def test_keine_geld_oder_stueckzahl_felder_im_journal_code():
    js = _journal_js().lower()
    treffer = [w for w in VERBOTEN
               if re.search(rf"\b{re.escape(w)}\b", js)
               and w not in ("stueck", "stück", "beträge", "betraege")]
    assert not treffer, f"Geld-/Stückzahl-Begriff im Journal-Code: {treffer}"


def test_keine_waehrungssymbole_in_den_journal_labels():
    """Die sichtbaren Beschriftungen nennen keine Währung — nur Prozent."""
    js = _journal_js()
    labels = re.findall(r"<label[^>]*>([^<]*)</label>", js)
    labels += re.findall(r'class="tj-sum-lbl">([^<]*)<', js)
    assert labels, "keine Beschriftungen gefunden — Test greift ins Leere"
    for lab in labels:
        assert "€" not in lab and "$" not in lab and "EUR" not in lab, lab


def test_der_eintrag_kennt_nur_die_erlaubten_felder():
    """Die Feldliste des angelegten Eintrags — ausgeschrieben, nicht abgeleitet."""
    block = re.search(r"function _tjNeu\(v, eingabe\) \{(.*?)\n    \}", HTML, re.S).group(1)
    # ALLE Schlüssel im Block, nicht nur die am Zeilenanfang.
    felder = set(re.findall(r"(?:^\s*|[{,]\s*)([a-z_]+):", block, re.M))
    erlaubt = {
        "id", "ticker", "market", "direction", "entry_date", "entry_price",
        # `note` ist das Altfeld aus #61 und bleibt im Schema, damit
        # bestehende Einträge nichts verlieren; `these`/`lesson` sind der
        # Lebenszyklus (31.07.2026).
        "status", "exit_date", "exit_price", "note", "these", "lesson", "tool",
        "setup", "score", "target_zone", "invalidation", "report_utc",
    }
    assert felder == erlaubt, f"Feldliste weicht ab: {sorted(felder ^ erlaubt)}"


def test_kein_eingabefeld_fuer_betraege_im_formular():
    """Beide Formulare — Eröffnen und Schließen — kennen NUR diese Eingaben."""
    schliessen = re.search(r"function _tjFormular\(e, offen\) \{(.*?)\n    \}",
                           HTML, re.S).group(1)
    ids = sorted(set(re.findall(r'id="tj-([a-z]+)-\$\{e\.id\}"', schliessen)))
    assert ids == ["le", "th", "xd", "xp"], f"Schließen-Formular: {ids}"

    eroeffnen = re.search(r"function _tjEntwurfBlock\(\) \{(.*?)\n    \}",
                          HTML, re.S).group(1)
    neu = sorted(set(re.findall(r'id="(tj-ne-[a-z])"', eroeffnen)))
    assert neu == ["tj-ne-d", "tj-ne-p", "tj-ne-t"], f"Eröffnen-Formular: {neu}"


# ---------------------------------------------------------------------------
# 3 · SYNC-PFAD WIEDERVERWENDET, NICHT NACHGEBAUT
# ---------------------------------------------------------------------------
def test_es_gibt_nur_eine_github_put_mechanik():
    """Watchlist UND Journal gehen durch `_ghPutFile` — nicht zwei Fassungen."""
    assert HTML.count("async function _ghPutFile(") == 1
    # Der 409/422-Retry steht genau EINMAL im ganzen Frontend. Gemessen am
    # Retry SELBST, nicht an der Zahl der Vorkommen von „status === 409" —
    # dieser Zaehler war ein Stellvertreter und schlug an, sobald irgendwo
    # sonst ein 409 nur BENANNT wurde (05.08.2026: sha-Verwerfen nach
    # gescheitertem Retry + Grund-Zuordnung fuer den Badge-Text).
    assert HTML.count("method: 'PUT'") == 1, "es gibt nur EINEN PUT im Frontend"
    put_block = re.search(r"async function _ghPutFile\(.*?\n    \}", HTML, re.S).group(0)
    assert put_block.count("r = await _put(") == 2, "erster Versuch + genau EIN Retry"
    assert HTML.count("r = await _put(") == 2, "kein zweiter Retry ausserhalb"
    for nutzer in ("_wlDoPut", "_tjDoPut"):
        block = re.search(rf"async function {nutzer}\(.*?\n    \}}", HTML, re.S).group(0)
        assert "_ghPutFile(" in block, f"{nutzer} nutzt die gemeinsame Mechanik nicht"
        assert "method: 'PUT'" not in block, f"{nutzer} baut den PUT nach"


def test_journal_schreibt_genau_einen_pfad():
    assert "const TJ_GH_PATH = 'docs/data/trade_journal.json';" in HTML
    assert "const TJ_FETCH_PATH = 'data/trade_journal.json';" in HTML
    assert "TJ_GH_PATHS" not in HTML and "TJ_FETCH_PATHS" not in HTML
    # genau EIN PUT pro Sync — keine Schleife über mehrere Ablagen
    block = re.search(r"async function _tjDoPut\(.*?\n    \}", HTML, re.S).group(0)
    assert block.count("_ghPutFile(") == 1, "mehr als ein PUT pro Journal-Sync"
    assert "for (const p of" not in block


# ---------------------------------------------------------------------------
# 4 · ANZEIGE SAGT, WAS ES IST
# ---------------------------------------------------------------------------
def test_anzeige_benennt_die_trennung_von_der_validierung():
    assert "Eigene Handels-Aufzeichnung, nicht Teil" in HTML
    assert "sagt nichts über die Güte des Werkzeugs" in HTML
    assert "Keine Beträge, keine\n        Stückzahlen." in HTML


def test_prozent_wird_berechnet_und_nicht_eingegeben():
    fn = re.search(r"function _tjPct\(e\) \{(.*?)\n    \}", HTML, re.S).group(1)
    assert "(b - a) / a * 100" in fn
    assert "e.direction === 'short' ? -roh : roh" in fn


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_der_testlauf_fasst_die_repo_journal_datei_nicht_an():
    import subprocess
    r = subprocess.run(["git", "status", "--porcelain", "--",
                        "docs/data/trade_journal.json"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip() == "", f"Journal-Datei verändert:\n{r.stdout}"


# ---------------------------------------------------------------------------
# 5 · LEBENSZYKLUS (31.07.2026): Eröffnen → Schließen, These/Lesson, Statistik
# ---------------------------------------------------------------------------
def _tj_block() -> str:
    """Der Journal-Abschnitt des Frontends (ohne den Token-Teil dahinter)."""
    i = HTML.index("TRADE-JOURNAL — eigene Handels-Aufzeichnung")
    return HTML[i:HTML.index("const GH_OWNER", i)]


# Felder, die der Nutzer selbst tippt. Alles davon landet in der Anzeige und
# muss dort escaped werden — `these`/`lesson` sind neu, `ticker`/`note` waren
# es schon. Die Liste steht ausgeschrieben: wer ein Feld ergänzt, muss sie
# anfassen und merkt es dabei.
NUTZERFELDER = ["these", "lesson", "note"]


def test_jede_ausgabe_von_freitext_ist_escaped():
    """XSS: KEINE Interpolation eines Freitextfeldes ohne `esc(...)`.

    Geprüft wird jede Stelle im Journal-Block, an der `e.<feld>` oder
    `_tjEntwurf.<feld>` in ein Template-Literal wandert — sie muss innerhalb
    von `esc(` stehen. Ein Test auf „irgendwo steht esc" hätte eine einzelne
    vergessene Stelle nicht gefunden.
    """
    block = _tj_block()
    offen = []
    for feld in NUTZERFELDER + ["ticker"]:
        for m in re.finditer(r"\$\{([^{}]*\b(?:e|_tjEntwurf|v|b)\."
                             + feld + r"\b[^{}]*)\}", block):
            if "esc(" not in m.group(1):
                offen.append(m.group(0))
    assert not offen, f"Freitext ohne esc(): {offen}"


def test_freitext_ist_auf_500_zeichen_begrenzt():
    block = _tj_block()
    assert "const TJ_TEXT_MAX = 500;" in block
    assert block.count('maxlength="500"') == 3, \
        "jedes der drei Freitextfelder braucht die Browser-Grenze"
    # ... und die Grenze gilt auch ohne Browser (eingefügter Text, altes Feld).
    assert "slice(0, TJ_TEXT_MAX)" in block
    for feld in ("these", "lesson"):
        assert re.search(rf"e\.{feld} = _tjTxt\(", block), feld


def test_status_verlangt_datum_UND_kurs():
    """Halb geschlossen gibt es nicht — sonst rechnete die Statistik ins Leere."""
    block = _tj_block()
    assert ("e.status = (e.exit_date && e.exit_price != null) "
            "? 'geschlossen' : 'offen';") in block


def test_statistik_rechnet_ueber_die_GEFILTERTE_menge():
    """Die Kennzahlen hängen an der gefilterten Liste, nicht am Gesamtbestand."""
    block = _tj_block()
    render = re.search(r"function _tjRender\(\) \{(.*?)\n    \}", block, re.S).group(1)
    assert "const zu = _tjGefiltert(" in render
    assert "const s = _tjStats(zu);" in render, \
        "Statistik muss die gefilterte Liste bekommen"
    # Offene Einträge werden SEPARAT gezählt (ungefiltert) — wie bisher.
    assert "const offen = arr.filter(e => e.status !== 'geschlossen');" in render


def test_prozent_kennt_die_kanten():
    """entry ≤ 0, nicht-numerisch, fehlend → kein Ergebnis statt Unsinn."""
    fn = re.search(r"function _tjPct\(e\) \{(.*?)\n    \}", HTML, re.S).group(1)
    assert "if (!isFinite(a) || !isFinite(b) || a <= 0) return null;" in fn


def test_datum_hat_EINEN_parser_fuer_beide_schreibweisen():
    block = _tj_block()
    iso = re.search(r"function _tjISO\(s\) \{(.*?)\n    \}", block, re.S).group(1)
    assert r"/^\d{4}-\d{2}-\d{2}$/" in iso, "ISO fehlt"
    assert r"/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/" in iso, "TT.MM.JJJJ fehlt"
    # Dauer und Zeitfilter gehen über DENSELBEN Parser — und zwar an JEDER
    # Stelle. Ein bloßes „_tjISO kommt darin vor" reichte nicht: die Mutation
    # „Zeitfilter nimmt `e.exit_date` roh" blieb damit grün, weil der Sortier-
    # Vergleich weiter unten den Parser noch benutzte (die #63-Lehre).
    for fn in ("_tjTage", "_tjGefiltert"):
        koerper = re.search(rf"function {fn}\(.*?\) \{{(.*?)\n    \}}",
                            block, re.S).group(1)
        roh = [m.start() for m in re.finditer(r"\b[a-z]\.exit_date\b", koerper)
               if not koerper[max(0, m.start() - 7):m.start()].endswith("_tjISO(")]
        assert not roh, f"{fn} liest ein Datum am gemeinsamen Parser vorbei"
        assert "_tjISO(" in koerper, f"{fn} parst am gemeinsamen Parser vorbei"
    # `_tjTage` bekommt zwei Rohwerte herein — BEIDE müssen durch den Parser.
    tage = re.search(r"function _tjTage\(a, b\) \{(.*?)\n    \}",
                     block, re.S).group(1)
    assert "_tjISO(a)" in tage and "_tjISO(b)" in tage, \
        "eine der beiden Datumsangaben umgeht den Parser"


def test_eingaben_werden_vor_jedem_neu_rendern_gesichert():
    """Ein Validierungs-Fehler darf getippten Text nicht verwerfen."""
    block = _tj_block()
    klick = re.search(r"function _tjClick\(ev\) \{(.*?)\n    \}", block, re.S).group(1)
    # Vor jedem `_tjRender()` im Fehlerzweig steht das Einlesen des Formulars.
    assert klick.count("_tjLeseEntwurf();") >= 3
    assert "_tjLeseEdit(id);" in klick
    speichern = klick[klick.index("if (t.dataset.tjSave)"):]
    assert speichern.index("_tjLeseEdit(id);") < speichern.index("showToast("), \
        "Eingaben werden erst nach der ersten Fehlermeldung gesichert"


def test_alt_eintraege_ohne_neue_felder_bleiben_lesbar():
    """Fehlende `these`/`lesson`/`note` → leerer Text, nie `undefined`.

    Zwei zulässige Formen: ein Rückfall (`e.x || ''`) für Werte, die in ein
    Eingabefeld wandern, oder eine Bedingung (`e.x ? … : ''`) für Blöcke, die
    ohne Inhalt gar nicht erst erscheinen. Ungeschützt darf kein Feld sein.
    """
    block = _tj_block()
    for feld in NUTZERFELDER:
        rueckfall = re.search(rf"e\.{feld} \|\| ''", block)
        bedingung = re.search(rf"e\.{feld} \?", block)
        assert rueckfall or bedingung, \
            f"{feld} ungeschützt — Alt-Einträge zeigten `undefined`"
    # Die beiden Felder, die in ein Formular geschrieben werden, brauchen den
    # Rückfall zwingend: `undefined` stünde sonst sichtbar im Textfeld.
    for feld in ("these", "lesson"):
        assert re.search(rf"{feld}: e\.{feld} \|\| ''", block), feld


# ---------------------------------------------------------------------------
# 6 · DIE KENNZAHLEN SELBST — WERTE, NICHT ANWESENHEIT
# ---------------------------------------------------------------------------
# Guardian-Nit 31.07.2026: die Statistik hatte nur einen „wird mit der
# gefilterten Liste aufgerufen"-Test. FÜNF Mutationen blieben grün —
# Breakeven als Gewinner, Schlechtester/Bester vertauscht, `>= 50` zu `> 50`,
# Score-Korrelation vertauscht, Zeitfilter-Randtag. Genau die Kennzahlen aus
# dem Auftrag könnten also still falsch sein. Zwei Netze dagegen:
#   (a) die entscheidenden Vergleiche stehen als LITERAL fest — läuft überall,
#   (b) die Funktionen werden mit node WIRKLICH AUSGEFÜHRT, wenn eins da ist.
# (a) allein fängt alle fünf; (b) prüft zusätzlich das Verhalten und überlebt
# ein Umformulieren des Codes.
import shutil          # noqa: E402
import subprocess      # noqa: E402


def _tj_fn(name: str) -> str:
    """Eine Funktion aus dem Frontend herausschneiden (Einrückung als Klammer)."""
    start = HTML.index(f"    function {name}(")
    ende = HTML.index("\n    }", start) + len("\n    }")
    return HTML[start:ende]


def test_die_entscheidenden_vergleiche_stehen_fest():
    """Ein stiller Dreher an einem dieser Zeichen kippt eine Kennzahl."""
    stats = _tj_fn("_tjStats")
    # Breakeven (p == 0) ist WEDER Gewinner NOCH Verlierer.
    assert "const win = paare.filter(x => x.p > 0), los = paare.filter(x => x.p < 0);" in stats
    # Bester ist das Maximum, Schlechtester das Minimum — nicht umgekehrt.
    assert "if (!best || x.p > best.p) best = x;" in stats
    assert "if (!mies || x.p < mies.p) mies = x;" in stats
    # Score-Korrelation: Gewinner-Score aus den Gewinnern, nicht vertauscht.
    assert "scoreWin: score(win), scoreLos: score(los)," in stats
    # Trefferquote: 50 % ist noch grün (so steht es im Auftrag).
    render = _tj_fn("_tjRender")
    assert "s.quote >= 50 ? ' tj-hit tj-good' : ' tj-hit tj-bad'" in render
    # Zeitfilter: der Randtag gehört noch dazu.
    gef = _tj_fn("_tjGefiltert")
    assert "Date.parse(iso + 'T00:00:00Z') >= grenze" in gef


_NODE = shutil.which("node") or shutil.which("nodejs")


def _js(script: str):
    """Die Journal-Rechenkerne in node ausführen und JSON zurückgeben.

    Bewusst OHNE feste Node-Abhängigkeit für die Suite: fehlt node, bleibt der
    Literal-Test oben als vollständiges Netz. Deshalb skip statt Fehler.
    """
    if not _NODE:
        import pytest
        pytest.skip("kein node vorhanden — der Literal-Test deckt dieselben Fälle")
    prelude = ("let _tjFZeit = 'alle', _tjFErg = 'alle';\n"
               "Date.now = () => Date.parse('2026-07-31T12:00:00Z');\n")
    quelle = "\n".join(_tj_fn(n) for n in
                       ("_tjPct", "_tjISO", "_tjTage", "_tjStats", "_tjGefiltert"))
    r = subprocess.run([_NODE, "-e", prelude + quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _rec(ticker, entry, exit_, score, exit_date="2026-07-30"):
    return {"ticker": ticker, "direction": "long", "entry_price": entry,
            "exit_price": exit_, "entry_date": "2026-07-01",
            "exit_date": exit_date, "status": "geschlossen",
            "tool": {"score": score}}


def test_statistik_rechnet_die_beispielliste_richtig():
    """Feste Liste, von Hand nachgerechnet — inklusive Breakeven."""
    liste = [_rec("A", 100, 120, 90),     # +20 %
             _rec("B", 100, 90, 60),      # -10 %
             _rec("C", 100, 100, 70),     # ±0  -> weder noch
             _rec("D", 50, 55, 80)]       # +10 %
    s = _js("console.log(JSON.stringify(_tjStats(%s)))" % json.dumps(liste))
    assert s["n"] == 4
    # Gewinner A und D, Verlierer B, C zählt zu keinem von beiden.
    assert round(s["quote"], 4) == 50.0
    assert round(s["avg"], 4) == 5.0            # (20 - 10 + 0 + 10) / 4
    assert round(s["avgWin"], 4) == 15.0        # (20 + 10) / 2
    assert round(s["avgLos"], 4) == -10.0
    assert s["best"]["t"] == "A" and round(s["best"]["p"], 4) == 20.0
    assert s["mies"]["t"] == "B" and round(s["mies"]["p"], 4) == -10.0
    assert round(s["scoreWin"], 4) == 85.0      # (90 + 80) / 2
    assert round(s["scoreLos"], 4) == 60.0


def test_zeitfilter_nimmt_den_randtag_mit():
    """Genau 30 Tage her → gehört noch dazu; 31 Tage → nicht mehr."""
    liste = [_rec("RAND", 100, 110, 80, exit_date="2026-07-01"),   # 30 Tage
             _rec("DRAUSSEN", 100, 110, 80, exit_date="2026-06-30")]  # 31 Tage
    tk = _js("_tjFZeit = '30';"
             "console.log(JSON.stringify(_tjGefiltert(%s).map(e => e.ticker)))"
             % json.dumps(liste))
    assert tk == ["RAND"], tk


def test_geschlossene_liste_ist_neueste_zuerst():
    liste = [_rec("ALT", 100, 110, 80, exit_date="2026-05-01"),
             _rec("NEU", 100, 110, 80, exit_date="2026-07-20"),
             _rec("MITTE", 100, 110, 80, exit_date="2026-06-10")]
    tk = _js("console.log(JSON.stringify(_tjGefiltert(%s).map(e => e.ticker)))"
             % json.dumps(liste))
    assert tk == ["NEU", "MITTE", "ALT"], tk
