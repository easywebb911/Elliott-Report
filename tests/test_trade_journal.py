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
        (rep.get("health") or {}).pop("checked_at", None)
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
    assert json.loads(gelesen.read_text(encoding="utf-8")) == []
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
    block = re.search(r"function _tjNeu\(v\) \{(.*?)\n    \}", HTML, re.S).group(1)
    # ALLE Schlüssel im Block, nicht nur die am Zeilenanfang.
    felder = set(re.findall(r"(?:^\s*|[{,]\s*)([a-z_]+):", block, re.M))
    erlaubt = {
        "id", "ticker", "market", "direction", "entry_date", "entry_price",
        "status", "exit_date", "exit_price", "note", "tool",
        "setup", "score", "target_zone", "invalidation", "report_utc",
    }
    assert felder == erlaubt, f"Feldliste weicht ab: {sorted(felder ^ erlaubt)}"


def test_kein_eingabefeld_fuer_betraege_im_formular():
    form = re.search(r'const form = bearbeiten \? `(.*?)`', HTML, re.S).group(1)
    ids = re.findall(r'id="tj-([a-z]+)-', form)
    assert sorted(set(ids)) == ["nt", "xd", "xp"], \
        f"unerwartete Eingabefelder: {sorted(set(ids))}"


# ---------------------------------------------------------------------------
# 3 · SYNC-PFAD WIEDERVERWENDET, NICHT NACHGEBAUT
# ---------------------------------------------------------------------------
def test_es_gibt_nur_eine_github_put_mechanik():
    """Watchlist UND Journal gehen durch `_ghPutFile` — nicht zwei Fassungen."""
    assert HTML.count("async function _ghPutFile(") == 1
    # Der 409/422-Retry steht genau EINMAL im ganzen Frontend.
    assert len(re.findall(r"status === 409", HTML)) == 1
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
