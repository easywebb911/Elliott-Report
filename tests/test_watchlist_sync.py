"""Watchlist-Sync: der Fehler wird laut, der Konflikt löst sich, nichts leckt.

VORFALL (04.08.2026, von Easy live beobachtet): GME hinzufügen lief durch,
GME entfernen schlug fehl — Toast „Nicht gesynct (HTTP 409):
watchlist_personal.json does not match 19c5f5d2…", Badge orange, keine weitere
Spur. Die Git-Historie zeigt: zum Zeitpunkt des 409 stand im Repo der Blob
`b1e922d4` (MIT GME); der Client schickte `19c5f5d2` — den Stand VOR dem
Hinzufügen, also einen sha, der bereits zwei Stände alt war. Der frische sha
lag zu diesem Zeitpunkt aus der vorigen PUT-Antwort im Speicher und wurde vom
GET überschrieben.

Zwei Netze wie beim Zonen-Abstand:
  (a) LITERALE Pins auf die Stellen, an denen ein stiller Dreher die Wirkung
      kippt — laufen überall, ohne Zusatz-Abhängigkeit;
  (b) die Mechanik wird mit **node wirklich ausgeführt** (fake fetch mit
      Zwischenspeicher-Modell, fake localStorage). Fehlt node, greift (a).
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) Literale Pins
# ---------------------------------------------------------------------------
def test_der_sha_GET_umgeht_den_zwischenspeicher():
    """Der Kern des Vorfalls. Ohne beides — `no-store` UND eine je Aufruf
    eindeutige URL — liefert der Retry denselben veralteten sha wie der erste
    Versuch, und der 409 ist dauerhaft."""
    assert "{ headers: H, cache: 'no-store' }" in HTML
    assert "&_=${Date.now()}-${++_ghNonce}" in HTML


def test_der_gemerkte_sha_wird_nicht_mehr_ueberschrieben():
    """Die PUT-Antwort nennt den neuen sha selbst — das ist die verlässlichste
    Quelle. Gelesen wird nur, wenn wir keinen haben."""
    assert "if (shaBox.sha == null) {" in HTML
    assert "shaBox.sha = (await r.json()).content?.sha || null;" in HTML


def test_nach_gescheitertem_retry_wird_der_sha_verworfen():
    """Sonst zöge der nächste Versuch denselben toten sha erneut heran."""
    assert ("else if (r.status === 409 || r.status === 422) { shaBox.sha = null; }"
            in HTML)


def test_die_sha_wird_NICHT_aus_dem_fehlertext_gelesen():
    """Belegt am echten Vorfall: die 409-Meldung nannte `19c5f5d2` — NICHT den
    erwarteten sha (der war `b1e922d4`). Wer den Text parst, schickt beim
    Retry genau denselben falschen Wert noch einmal."""
    assert "does not match" not in HTML
    for verdaechtig in ("/[0-9a-f]{40}/", "match(/[0-9a-f]", "does not match"):
        assert verdaechtig not in HTML


def test_die_warteschlange_ist_eine_liste_und_kein_slot():
    assert "let _pendingTokenCbs = [];" in HTML
    assert "_pendingTokenCbs.push({ cb, onAbbruch });" in HTML
    assert "_pendingTokenCb " not in HTML and "_pendingTokenCb;" not in HTML


def test_closeTokModals_verwirft_die_warteschlange_NICHT():
    """Der Erfolgspfad kommt hier ebenfalls durch — würde er die Aufträge
    löschen, wäre er selbst der Auftragsvernichter."""
    start = HTML.index("    function _closeTokModals() {")
    koerper = HTML[start:HTML.index("\n    }", start)]
    assert "_pendingTokenCbs" not in koerper


@pytest.mark.parametrize("bindung", [
    "document.getElementById('tok-modal-overlay').addEventListener('click', _abbrechenTokenWarteschlange);",
    "document.getElementById('tok-setup-cancel').addEventListener('click', _abbrechenTokenWarteschlange);",
    "document.getElementById('tok-unlock-cancel').addEventListener('click', _abbrechenTokenWarteschlange);",
    "if (!document.getElementById('tok-modal-overlay').hidden) { _abbrechenTokenWarteschlange(); return; }",
])
def test_jeder_abbruch_weg_meldet_den_abbruch(bindung):
    assert bindung in HTML


def test_der_zustand_wird_persistiert_und_endet_nur_beim_erfolg():
    assert "const WL_STATE_KEY = 'elliott_wl_sync_state_v1';" in HTML
    # genau EIN Aufräum-Aufruf im Erfolgszweig des PUT
    start = HTML.index("    async function _wlDoPut(token) {")
    koerper = HTML[start:HTML.index("\n    }", start)]
    assert "_wlStateClear();                            // Zustand endet NUR hier" in koerper
    assert "_wlMerkeFehlschlag(grund, r.status, detail);" in koerper


def test_der_antworttext_wird_vor_dem_speichern_gefiltert():
    """Kein Pfad, auf dem ein ROHER Antworttext in den Zustand wandert."""
    start = HTML.index("    async function _wlDoPut(token) {")
    koerper = HTML[start:HTML.index("\n    }", start)]
    assert "const detail = _wlScrub(roh, token);" in koerper
    assert "_wlMerkeFehlschlag(grund, r.status, roh)" not in koerper


def test_backoff_statt_dauerschleife():
    assert "const WL_SYNC_MAX_BACKOFF_MS = 180000;" in HTML
    assert "const WL_SYNC_MAX_TRIES = 6;" in HTML
    assert "if (n >= WL_SYNC_MAX_TRIES) return;" in HTML
    # der Fehlschlag-Pfad plant NICHT mehr den 3-Sekunden-Takt
    start = HTML.index("    async function _wlDoPut(token) {")
    koerper = HTML[start:HTML.index("\n    }", start)]
    assert "if (_wlDirty()) { if (ok) _wlScheduleSync(); else _wlPlanSync(); }" in koerper


def test_der_wiederanlauf_oeffnet_niemals_einen_dialog():
    """Ein Passwort-Dialog bei jedem App-Start wäre schlimmer als der Fehler."""
    start = HTML.index("    function _wlSyncNow(opt) {")
    koerper = HTML[start:HTML.index("\n    }", start)]
    assert "if (opt.still) {" in koerper
    assert "_trySessionUnlock" in koerper
    assert "_wlWiederanlauf();   // offener Sync aus einer früheren Sitzung" in HTML


def test_der_menuepunkt_existiert_und_haengt_am_klartext_pfad():
    assert 'id="mi-wlsync"' in HTML
    assert "<span class=\"mi-label\">Watchlist synchronisieren</span>" in HTML
    assert ("document.getElementById('mi-wlsync').addEventListener('click', _wlSyncJetzt);"
            in HTML)


def test_der_dirty_vergleich_laeuft_ueber_mengen():
    assert "return JSON.stringify(Array.from(new Set(arr.map(String))).sort());" in HTML
    # der alte, reihenfolge-empfindliche Vergleich ist überall ersetzt
    assert "JSON.stringify(_wlArr) !== _wlSyncedJson" not in HTML
    assert "JSON.stringify(_wlArr) === _wlSyncedJson" not in HTML


# ---------------------------------------------------------------------------
# (b) node: die Mechanik WIRKLICH ausführen
# ---------------------------------------------------------------------------
_NODE = shutil.which("node") or shutil.which("nodejs")


def _fn(name: str) -> str:
    marke = f"    function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index("\n    }", start) + len("\n    }")]


def _afn(name: str) -> str:
    marke = f"    async function {name}("
    start = HTML.index(marke)
    return HTML[start:HTML.index("\n    }", start) + len("\n    }")]


def _konst(name: str) -> str:
    """Die Zeile bis zum Semikolon — der nachgestellte Kommentar bleibt draußen
    (er enthält selbst Semikolons und riss sonst die nächste Zeile mit)."""
    start = HTML.index(f"    const {name} =")
    zeile = HTML[start:HTML.index("\n", start)]
    return zeile[:zeile.index(";") + 1]


_STUBS = """
// --- Doubles: nur so viel Umgebung wie nötig ---------------------------------
const _store = new Map();
globalThis.localStorage = {
  getItem: (k) => (_store.has(k) ? _store.get(k) : null),
  setItem: (k, v) => { _store.set(k, String(v)); },
  removeItem: (k) => { _store.delete(k); },
};
globalThis.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
globalThis.unescape = globalThis.unescape || ((s) => decodeURIComponent(s));
const GH_OWNER = 'easywebb911', GH_REPO = 'Elliott-Report', GH_BRANCH = 'main';
let _wlArr = null, _wlSyncedJson = null, _wlState = null, _wlSyncing = false;
let _wlGhSha = null, _wlSyncTimer = null;
let _chipText = null, _chipHidden = true;
function _wlUpdateSyncChip() { _chipHidden = !_wlDirty(); if (!_chipHidden) _chipText = _wlChipText(); }
function _antwort(status, body, kopf) {
  const h = new Map(Object.entries(kopf || {}));
  return { ok: status >= 200 && status < 300, status,
           headers: { get: (n) => (h.has(String(n).toLowerCase()) ? h.get(String(n).toLowerCase()) : null) },
           json: async () => body,
           text: async () => (typeof body === 'string' ? body : JSON.stringify(body)) };
}
"""


def _js(script: str, extra: str = ""):
    if not _NODE:
        pytest.skip("kein node vorhanden — die Literal-Tests decken dieselben Fälle")
    quelle = "\n".join([
        _konst("WL_SYNC_DEBOUNCE_MS"), _konst("WL_SYNC_MAX_BACKOFF_MS"),
        _konst("WL_SYNC_MAX_TRIES"), _konst("WL_STATE_KEY"), _konst("WL_DETAIL_MAX"),
        _STUBS,
        _fn("_wlStateLoad"), _fn("_wlStateSave"), _fn("_wlStateClear"),
        _fn("_wlScrub"), _fn("_wlMerkeFehlschlag"), _fn("_wlMerkeAbbruch"),
        _fn("_wlKanon"), _fn("_wlDirty"), _fn("_wlZeitKurz"), _fn("_wlChipText"),
        _fn("_wlBackoffMs"), _fn("_ghFehlerGrund"),
        "let _ghNonce = 0;", _afn("_ghGetSha"), _afn("_ghPutFile"),
        extra,
    ])
    r = subprocess.run([_NODE, "--input-type=module", "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# --- Der echte 409-Fall ------------------------------------------------------
_GITHUB = """
// Modell des Vorfalls: ein Zwischenspeicher, der GET-Antworten je URL festhält.
// Genau so verhielt sich der Browser am 04.08. — der zweite GET bekam dieselbe
// Antwort wie der erste und damit denselben veralteten sha.
function macheGithub(startSha) {
  const zustand = { sha: startSha, log: [] };
  const cache = new Map();
  globalThis.fetch = async (url, init) => {
    init = init || {};
    if ((init.method || 'GET') === 'GET') {
      const frisch = init.cache === 'no-store' || !cache.has(url);
      zustand.log.push({ m: 'GET', frisch });
      if (!frisch) return _antwort(200, { sha: cache.get(url) });
      cache.set(url, zustand.sha);
      return _antwort(200, { sha: zustand.sha });
    }
    const body = JSON.parse(init.body);
    zustand.log.push({ m: 'PUT', sha: body.sha || null });
    if ((body.sha || null) !== zustand.sha) {
      return _antwort(409, { message: `watchlist_personal.json does not match ${body.sha}` });
    }
    zustand.sha = 'sha-' + zustand.log.length;
    return _antwort(200, { content: { sha: zustand.sha } });
  };
  return zustand;
}
"""


def test_der_zweite_PUT_geht_durch_ohne_erneuten_GET():
    """Der GME-Fall: hinzufügen, dann entfernen. Der sha aus der ERSTEN
    PUT-Antwort trägt den zweiten PUT — kein GET, also auch kein veralteter."""
    erg = _js("""
      (async () => {
        const gh = macheGithub('alt');
        const box = { sha: null };
        const r1 = await _ghPutFile('tok', 'p.json', '["A","GME"]', 'm', box);
        const nachErstem = box.sha;
        const r2 = await _ghPutFile('tok', 'p.json', '["A"]', 'm', box);
        console.log(JSON.stringify({ s1: r1.status, s2: r2.status,
          nachErstem, log: gh.log }));
      })();
    """, extra=_GITHUB)
    assert erg["s1"] == 200 and erg["s2"] == 200, "beide Syncs müssen durchgehen"
    assert erg["nachErstem"] and erg["nachErstem"] != "alt"
    # genau ein GET (der allererste), danach nur noch PUTs
    assert [e["m"] for e in erg["log"]] == ["GET", "PUT", "PUT"]


def test_ein_fremder_stand_loest_sich_ueber_den_frischen_GET():
    """Ein anderes Gerät hat inzwischen geschrieben: der gemerkte sha ist tot,
    der PUT bekommt 409 — und der Retry holt den sha OHNE Zwischenspeicher."""
    erg = _js("""
      (async () => {
        const gh = macheGithub('alt');
        const box = { sha: 'veraltet' };        // Stand von vorgestern
        const r = await _ghPutFile('tok', 'p.json', '["A"]', 'm', box);
        console.log(JSON.stringify({ status: r.status, log: gh.log }));
      })();
    """, extra=_GITHUB)
    assert erg["status"] == 200, "der Retry muss den Konflikt auflösen"
    assert [e["m"] for e in erg["log"]] == ["PUT", "GET", "PUT"]
    assert erg["log"][1]["frisch"] is True, "der Retry-GET darf NICHT aus dem Cache kommen"
    assert erg["log"][2]["sha"] == "alt"


def test_ohne_cache_umgehung_bleibt_der_konflikt_bestehen():
    """Gegenprobe zum Vorfall: liest der Retry MIT Zwischenspeicher, bekommt er
    denselben veralteten sha und der 409 ist dauerhaft. Das war der 04.08."""
    erg = _js("""
      (async () => {
        const gh = macheGithub('aktuell');
        const H = {};
        const base = 'https://api.github.com/x';
        // erster GET füllt den Zwischenspeicher …
        await fetch(`${base}?ref=main`, { headers: H });
        // … jemand schreibt dazwischen …
        gh.sha = 'inzwischen-anders';
        const mitCache = await fetch(`${base}?ref=main`, { headers: H });
        const ohneCache = await _ghGetSha(base, H);
        console.log(JSON.stringify({ mitCache: (await mitCache.json()).sha, ohneCache }));
      })();
    """, extra=_GITHUB)
    assert erg["mitCache"] == "aktuell", "so entstand der dauerhafte 409"
    assert erg["ohneCache"] == "inzwischen-anders", "die Umgehung sieht den echten Stand"


def test_auch_ein_zwischenspeicher_der_no_store_ignoriert_wird_umgangen():
    """`no-store` ist eine BITTE an den Browser. Ein Zwischenspeicher, der sie
    überhört, bekommt trotzdem nichts zu tun — weil die URL je Aufruf eine
    andere ist. Das ist der Zweck des Zählers in `_ghGetSha`."""
    erg = _js("""
      (async () => {
        const cache = new Map();
        let echt = 'A';
        const gesehen = [];
        globalThis.fetch = async (url) => {          // ignoriert `cache: no-store`
          gesehen.push(url);
          if (!cache.has(url)) cache.set(url, echt);
          return _antwort(200, { sha: cache.get(url) });
        };
        const eins = await _ghGetSha('https://x/y', {});
        echt = 'B';                                   // jemand schreibt dazwischen
        const zwei = await _ghGetSha('https://x/y', {});
        console.log(JSON.stringify({ eins, zwei, verschieden: gesehen[0] !== gesehen[1] }));
      })();
    """)
    assert erg["verschieden"] is True, "zwei Aufrufe müssen verschiedene URLs erzeugen"
    assert erg["eins"] == "A" and erg["zwei"] == "B"


def test_nach_gescheitertem_retry_ist_der_gemerkte_sha_leer():
    erg = _js("""
      (async () => {
        globalThis.fetch = async (url, init) => {
          if ((init && init.method) !== 'PUT') return _antwort(500, {});
          return _antwort(409, { message: 'nope' });
        };
        const box = { sha: 'x' };
        const r = await _ghPutFile('tok', 'p.json', '["A"]', 'm', box);
        console.log(JSON.stringify({ status: r.status, sha: box.sha }));
      })();
    """)
    assert erg["status"] == 409
    assert erg["sha"] is None, "sonst zieht der nächste Versuch denselben toten sha"


# --- Der volle Fehlschlag-Pfad ----------------------------------------------
_PUT_STUBS = """
const WL_GH_PATH = 'watchlist_personal.json';
let _toasts = [], _geplant = [];
function showToast(t, art) { _toasts.push({ t, art: art || null }); }
function _wlScheduleSync() { _geplant.push('debounce'); }
function _wlPlanSync() { _geplant.push('backoff'); }
"""


def _put_js(script: str, extra: str = ""):
    return _js(script, extra=_PUT_STUBS + "\n" + _afn("_wlDoPut") + "\n" + extra)


def test_der_fehlerzustand_ueberlebt_den_PUT_und_landet_im_speicher():
    """Der ganze Weg, nicht nur die Bausteine: ein 409 muss NACH dem PUT noch
    im localStorage stehen — sonst fiele der Badge auf „noch nicht gesynct"
    zurück und wir hätten wieder das grundlose Dauer-Orange.

    Diese Probe fehlte zuerst: eine Mutation, die den Zustand direkt nach dem
    Merken wieder löschte, überlebte die gesamte Suite."""
    erg = _put_js("""
      (async () => {
        _wlArr = ['A', 'B']; _wlSyncedJson = '[]';
        globalThis.fetch = async (url, init) => {
          if ((init && init.method) !== 'PUT') return _antwort(200, { sha: 'x' });
          return _antwort(409, 'watchlist_personal.json does not match x');
        };
        await _wlDoPut('ghp_geheim_geheim_geheim');
        const roh = localStorage.getItem(WL_STATE_KEY);
        console.log(JSON.stringify({ roh: roh ? JSON.parse(roh) : null,
                                     chip: _chipText, geplant: _geplant,
                                     toast: _toasts.map(t => t.t) }));
      })();
    """)
    assert erg["roh"] is not None, "der Fehlerzustand darf NICHT verschwinden"
    assert erg["roh"]["status"] == "offen" and erg["roh"]["http"] == 409
    assert erg["roh"]["grund"] == "Konflikt (409)"
    assert erg["chip"].startswith("Sync scheitert seit ")
    assert erg["geplant"] == ["backoff"], "nach einem Fehlschlag greift der Backoff"
    assert any("Konflikt (409)" in t for t in erg["toast"])


def test_der_erfolg_raeumt_den_zustand_weg():
    erg = _put_js("""
      (async () => {
        _wlArr = ['A']; _wlSyncedJson = '[]';
        _wlMerkeFehlschlag('Konflikt (409)', 409, '');   // Altlast aus gestern
        globalThis.fetch = async (url, init) => ((init && init.method) === 'PUT')
          ? _antwort(200, { content: { sha: 'neu' } })
          : _antwort(200, { sha: 'alt' });
        await _wlDoPut('tok');
        console.log(JSON.stringify({ gespeichert: localStorage.getItem(WL_STATE_KEY),
                                     zustand: _wlState, dirty: _wlDirty(),
                                     geplant: _geplant, toast: _toasts.map(t => t.t) }));
      })();
    """)
    assert erg["gespeichert"] is None and erg["zustand"] is None
    assert erg["dirty"] is False
    assert erg["geplant"] == [], "nichts mehr offen -> kein weiterer Versuch"
    assert erg["toast"] == ["✓ Watchlist gesynct"]


def test_der_toast_bei_fehlschlag_traegt_kein_token():
    erg = _put_js("""
      (async () => {
        _wlArr = ['A']; _wlSyncedJson = '[]';
        globalThis.fetch = async (url, init) => ((init && init.method) === 'PUT')
          ? _antwort(401, 'Bad credentials for ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8')
          : _antwort(200, { sha: 'x' });
        await _wlDoPut('ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8');
        console.log(JSON.stringify({ toast: _toasts.map(t => t.t),
                                     detail: _wlState.detail }));
      })();
    """)
    alles = " ".join(erg["toast"]) + " " + erg["detail"]
    for i in range(len(_TOKEN) - 7):
        assert _TOKEN[i:i + 8] not in alles
    assert any("Token ungültig oder abgelaufen" in t for t in erg["toast"])


def test_ein_netzfehler_wird_als_offen_gemerkt():
    erg = _put_js("""
      (async () => {
        _wlArr = ['A']; _wlSyncedJson = '[]';
        globalThis.fetch = async () => { throw new Error('offline'); };
        await _wlDoPut('tok');
        console.log(JSON.stringify({ status: _wlState.status, grund: _wlState.grund,
                                     geplant: _geplant }));
      })();
    """)
    assert erg["status"] == "offen"
    assert erg["grund"] == "Offline oder Netzfehler"
    assert erg["geplant"] == ["backoff"]


def test_die_versuchszahl_waechst_ueber_mehrere_fehlschlaege():
    """Backoff messbar: N Fehlversuche -> wachsende Abstände, danach Ruhe."""
    erg = _put_js("""
      (async () => {
        _wlArr = ['A']; _wlSyncedJson = '[]';
        globalThis.fetch = async (url, init) => ((init && init.method) === 'PUT')
          ? _antwort(409, 'nope') : _antwort(200, { sha: 'x' });
        const abstaende = [];
        for (let i = 0; i < 8; i++) {
          await _wlDoPut('tok');
          abstaende.push(_wlState.versuche >= WL_SYNC_MAX_TRIES
                         ? 'ruhe' : _wlBackoffMs(_wlState.versuche));
        }
        console.log(JSON.stringify({ abstaende, versuche: _wlState.versuche }));
      })();
    """)
    assert erg["versuche"] == 8, "die Serie zählt weiter"
    assert erg["abstaende"][:5] == [3000, 6000, 12000, 24000, 48000]
    assert erg["abstaende"][5:] == ["ruhe", "ruhe", "ruhe"], "danach Ruhe"


# --- Sicherheit --------------------------------------------------------------
_TOKEN = "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


@pytest.mark.parametrize("text", [
    f"Bad credentials for {_TOKEN}",
    f'{{"message":"401","token":"{_TOKEN}"}}',
    f"Authorization: Bearer {_TOKEN}",
    _TOKEN[:20],                       # abgeschnittener Rest
    _TOKEN[7:25],                      # Mittelstück ohne Präfix
    "x" * 200 + _TOKEN,                # jenseits der Kürzungsgrenze
])
def test_kein_token_material_ueberlebt_die_filterung(text):
    """Zwei Netze: die bekannten Formen werden ersetzt, und ein 8-Zeichen-
    Fenster des echten Tokens verwirft den GANZEN Text."""
    erg = _js(f"console.log(JSON.stringify(_wlScrub({json.dumps(text)}, "
              f"{json.dumps(_TOKEN)})))")
    for i in range(len(_TOKEN) - 7):
        assert _TOKEN[i:i + 8] not in erg, f"Token-Fenster {i} überlebt"
    assert len(erg) <= 140


def test_der_gespeicherte_zustand_traegt_kein_token():
    """Der ganze Weg, nicht nur der Filter: Fehlschlag merken -> localStorage."""
    erg = _js(f"""
      const roh = 'Bad credentials: {_TOKEN} (also {_TOKEN[10:30]})';
      _wlMerkeFehlschlag('Token ungültig', 401, _wlScrub(roh, {json.dumps(_TOKEN)}));
      console.log(JSON.stringify(localStorage.getItem(WL_STATE_KEY)));
    """)
    for i in range(len(_TOKEN) - 7):
        assert _TOKEN[i:i + 8] not in erg
    assert "401" in erg and "Token ungültig" in erg


def test_ein_harmloser_text_bleibt_lesbar():
    """Der Filter darf nicht alles wegwerfen — der sha im 409-Text ist genau
    die Information, die den Vorfall aufgeklärt hat."""
    erg = _js("console.log(JSON.stringify(_wlScrub("
              "'watchlist_personal.json does not match 19c5f5d2a7016274c1a360df5e676e44e451058c', "
              "'ghp_zzzzzzzzzzzzzzzzzzzz')))")
    assert "19c5f5d2a7016274c1a360df5e676e44e451058c" in erg


# --- Backoff -----------------------------------------------------------------
def test_die_abstaende_wachsen_und_haben_einen_deckel():
    erg = _js("console.log(JSON.stringify([1,2,3,4,5,6,7,8,20].map(_wlBackoffMs)))")
    assert erg[:6] == [3000, 6000, 12000, 24000, 48000, 96000]
    assert erg[6] == 180000 and erg[-1] == 180000, "Deckel greift"
    assert erg == sorted(erg), "die Abstände dürfen nie schrumpfen"


def test_die_versuchszahl_waechst_nur_innerhalb_einer_serie():
    erg = _js("""
      _wlMerkeFehlschlag('Konflikt (409)', 409, '');
      _wlMerkeFehlschlag('Konflikt (409)', 409, '');
      const serie = { versuche: _wlState.versuche, seit: _wlState.seit };
      const zweiter = _wlState.zuletzt;
      _wlStateClear();
      _wlMerkeFehlschlag('Konflikt (409)', 409, '');
      console.log(JSON.stringify({ serie: serie.versuche, neu: _wlState.versuche,
                                   seitBleibt: serie.seit === zweiter ? null : serie.seit,
                                   serieStart: serie.seit }));
    """)
    # Der Zaehler ist die Aussage — NICHT der Zeitstempel: zwei Aufrufe in
    # derselben Millisekunde ergeben denselben, und ein Test darauf waere
    # zeitabhaengig (genau so einmal rot gelaufen).
    assert erg["serie"] == 2 and erg["neu"] == 1


# --- 403 ehrlich unterscheiden ----------------------------------------------
@pytest.mark.parametrize("status, kopf, erwartet", [
    (403, {"x-ratelimit-remaining": "0"}, "Rate-Limit erschöpft"),
    (403, {"x-ratelimit-remaining": "4711"}, "Berechtigung fehlt"),
    (403, {}, "Grund nicht auslesbar"),
    (429, {}, "Rate-Limit erschöpft"),
    (401, {}, "Token ungültig oder abgelaufen"),
    (409, {}, "Konflikt (409)"),
    (404, {}, "Datei oder Repo nicht gefunden"),
    (500, {}, "HTTP 500"),
])
def test_der_grund_wird_nicht_geraten(status, kopf, erwartet):
    erg = _js(f"console.log(JSON.stringify(_ghFehlerGrund("
              f"_antwort({status}, {{}}, {json.dumps(kopf)}))))")
    assert erwartet in erg


def test_bei_erschoepftem_limit_steht_die_uhrzeit_dabei():
    erg = _js("console.log(JSON.stringify(_ghFehlerGrund(_antwort(403, {}, "
              "{'x-ratelimit-remaining':'0','x-ratelimit-reset':'1785283200'}))))")
    assert erg.startswith("Rate-Limit erschöpft (frei ab ")
    assert "undefined" not in erg and "NaN" not in erg


# --- Badge-Text --------------------------------------------------------------
@pytest.mark.parametrize("zustand, erwartet", [
    (None, "noch nicht gesynct"),
    ({"status": "offen", "grund": "Konflikt (409)", "seit": "2026-08-03T21:14:00"},
     "Sync scheitert seit 03.08., 21:14 — Konflikt (409)"),
    ({"status": "abgebrochen", "grund": "Passwort-Dialog abgebrochen",
      "seit": "2026-08-03T21:14:00"},
     "Nicht gesynct seit 03.08., 21:14 — Passwort-Dialog abgebrochen"),
    ({"status": "offen", "grund": "", "seit": "2026-08-03T21:14:00"},
     "Sync scheitert seit 03.08., 21:14 — unbekannter Grund"),
    ({"status": "offen", "grund": "Offline oder Netzfehler", "seit": "kaputt"},
     "Sync scheitert — Offline oder Netzfehler"),
    ({"status": "offen"}, "Sync scheitert — unbekannter Grund"),
])
def test_jeder_zustand_ergibt_einen_ganzen_satz(zustand, erwartet):
    """Von Hand gegengelesen: kein „undefined", kein leerer Grund, kein
    abgehackter Satz."""
    erg = _js(f"_wlState = {json.dumps(zustand)}; "
              f"console.log(JSON.stringify(_wlChipText()))")
    assert erg == erwartet
    assert "undefined" not in erg and "null" not in erg
    assert not erg.rstrip().endswith("—")


def test_der_zeitstempel_wird_lokal_und_zweistellig_formatiert():
    erg = _js("console.log(JSON.stringify([_wlZeitKurz('2026-08-03T09:04:00'), "
              "_wlZeitKurz(''), _wlZeitKurz('unsinn')]))")
    assert erg[0] == "03.08., 09:04"
    assert erg[1] is None and erg[2] is None


# --- Mengen-Vergleich --------------------------------------------------------
@pytest.mark.parametrize("lokal, gesynct, dirty", [
    (["A", "B"], ["A", "B"], False),
    (["B", "A"], ["A", "B"], False),      # nur Reihenfolge -> NICHT dirty
    (["A", "B", "A"], ["A", "B"], False),  # Dublette -> keine echte Änderung
    (["A", "B", "C"], ["A", "B"], True),
    (["A"], ["A", "B"], True),
    ([], ["A"], True),
    (["A"], None, True),                   # noch keine Baseline
])
def test_nur_echte_mengen_unterschiede_zaehlen(lokal, gesynct, dirty):
    """Der Reihenfolge-Fall hielt die Watchlist sonst dauerhaft „dirty" und
    löste bei jedem Start einen überflüssigen Commit aus."""
    js = (f"_wlArr = {json.dumps(lokal)}; "
          f"_wlSyncedJson = {json.dumps(json.dumps(gesynct) if gesynct is not None else None)}; "
          f"console.log(JSON.stringify(_wlDirty()))")
    assert _js(js) is dirty


def test_ohne_liste_ist_nichts_dirty():
    assert _js("_wlArr = null; _wlSyncedJson = '[\"A\"]'; "
               "console.log(JSON.stringify(_wlDirty()))") is False


# --- Warteschlange -----------------------------------------------------------
_QUEUE_STUBS = """
let _pendingTokenCbs = [];
let _modal = null, _geschlossen = 0;
function _showTokModal(id) { _modal = id; }
function _closeTokModals() { _modal = null; _geschlossen++; }
function _hasToken() { return true; }
let _sessionToken = null;
async function _trySessionUnlock() { return _sessionToken; }
"""


def _queue_js(script: str):
    if not _NODE:
        pytest.skip("kein node vorhanden")
    quelle = "\n".join([_QUEUE_STUBS, _afn("_ensureToken"),
                        _fn("_abbrechenTokenWarteschlange"),
                        _fn("_tokenWarteschlangeAusfuehren")])
    r = subprocess.run([_NODE, "-e", quelle + "\n" + script],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_recalculate_verdraengt_den_wartenden_sync_nicht():
    """Der Verdrängungs-Fall: der Sync wartet auf das Passwort, Recalculate
    kommt dazwischen — vorher überschrieb dessen Callback den Sync spurlos."""
    erg = _queue_js("""
      (async () => {
        const gelaufen = [];
        await _ensureToken(() => gelaufen.push('sync'), () => gelaufen.push('sync-ab'));
        await _ensureToken(() => gelaufen.push('recalc'), () => gelaufen.push('recalc-ab'));
        _tokenWarteschlangeAusfuehren('tok');
        console.log(JSON.stringify({ gelaufen, rest: _pendingTokenCbs.length }));
      })();
    """)
    assert erg["gelaufen"] == ["sync", "recalc"], "beide Aufträge müssen laufen"
    assert erg["rest"] == 0


def test_ein_abbruch_erreicht_JEDEN_wartenden_auftrag():
    erg = _queue_js("""
      (async () => {
        const ab = [];
        await _ensureToken(() => ab.push('sync-ok'), () => ab.push('sync-ab'));
        await _ensureToken(() => ab.push('recalc-ok'), () => ab.push('recalc-ab'));
        _abbrechenTokenWarteschlange();
        console.log(JSON.stringify({ ab, rest: _pendingTokenCbs.length, zu: _geschlossen }));
      })();
    """)
    assert erg["ab"] == ["sync-ab", "recalc-ab"]
    assert erg["rest"] == 0 and erg["zu"] == 1


def test_ein_werfender_auftrag_reisst_die_anderen_nicht_mit():
    erg = _queue_js("""
      (async () => {
        const gelaufen = [];
        await _ensureToken(() => { throw new Error('kaputt'); }, () => {});
        await _ensureToken(() => gelaufen.push('zweiter'), () => {});
        _tokenWarteschlangeAusfuehren('tok');
        console.log(JSON.stringify(gelaufen));
      })();
    """)
    assert erg == ["zweiter"]


def test_bei_offener_sitzung_wartet_niemand():
    erg = _queue_js("""
      (async () => {
        _sessionToken = 'tok';
        let got = null;
        await _ensureToken((t) => { got = t; }, () => {});
        console.log(JSON.stringify({ got, wartend: _pendingTokenCbs.length, modal: _modal }));
      })();
    """)
    assert erg == {"got": "tok", "wartend": 0, "modal": None}


# --- Der Abbruch-Zustand -----------------------------------------------------
def test_abbruch_hinterlaesst_einen_sichtbaren_zustand():
    erg = _js("""
      _wlArr = ['A']; _wlSyncedJson = '[]';
      _wlMerkeAbbruch();
      console.log(JSON.stringify({ status: _wlState.status, text: _chipText,
                                   sichtbar: !_chipHidden,
                                   gespeichert: JSON.parse(localStorage.getItem(WL_STATE_KEY)).status }));
    """)
    assert erg["status"] == "abgebrochen" and erg["gespeichert"] == "abgebrochen"
    assert erg["sichtbar"] is True
    assert erg["text"].startswith("Nicht gesynct seit ")


def test_der_zustand_ueberlebt_den_reload():
    erg = _js("""
      _wlMerkeFehlschlag('Konflikt (409)', 409, 'nur Diagnose');
      const roh = localStorage.getItem(WL_STATE_KEY);
      _wlState = null;                       // „Reload"
      _wlState = _wlStateLoad();
      console.log(JSON.stringify({ da: !!roh, grund: _wlState.grund,
                                   versuche: _wlState.versuche }));
    """)
    assert erg == {"da": True, "grund": "Konflikt (409)", "versuche": 1}


@pytest.mark.parametrize("kaputt", ["nicht json", "[]", "42", '"text"', "null"])
def test_ein_kaputter_gespeicherter_zustand_wirft_nicht(kaputt):
    erg = _js(f"localStorage.setItem(WL_STATE_KEY, {json.dumps(kaputt)}); "
              f"console.log(JSON.stringify(_wlStateLoad()))")
    assert erg is None
