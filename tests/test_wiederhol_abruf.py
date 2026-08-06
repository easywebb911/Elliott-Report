"""Wiederhol-Abruf je Markt — mit der harten Regel: NIE VERSCHLECHTERN.

BEFUND, der das auslöst (06.08.2026): die Quelle liefert für DE regelmäßig eine
Tages-Zeile mit nicht-finiten Werten; die Härtung vom 27.07. verwirft sie, und
der Markt fällt auf den Vortag zurück. Gemessen an **116 von 117** Tickern in
JEDEM Abend-Cron-Lauf (30.07., 31.07., 03.08., 04.08., 05.08.).

Die Zusage dieses PRs ist nicht „der zweite Abruf hilft" — sie ist:
  * ein zweiter Abruf läuft NUR, wenn die Mehrheit betroffen ist,
  * sein Ergebnis wird NUR übernommen, wenn es ECHT besser ist,
  * und was er geliefert hat, steht je Versuch im Protokoll.

Alle Soll-Werte sind von Hand konstruiert und im Docstring hergeleitet.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import config  # noqa: E402
import elliott_pipeline as pipe  # noqa: E402


# ---------------------------------------------------------------------------
# Werkzeug: eine Reihe bauen, ein Markt-Universum stellen
# ---------------------------------------------------------------------------
def _reihe(n: int, ende: str):
    e = _dt.date.fromisoformat(ende)
    tage, kurse = [], []
    for i in range(n):
        tage.append(str(e - _dt.timedelta(days=n - 1 - i)))
        kurse.append(100.0 + (i % 11))
    return tage, kurse


def _markt(monkeypatch, tickers):
    monkeypatch.setitem(config.MARKETS, "TEST",
                        {"label": "Testmarkt", "universe": list(tickers)})


def _fetcher_folge(*runden):
    """Ein Fetcher, der bei JEDEM Markt-Durchlauf eine andere Runde liefert.

    ``runden``: je Runde ein Dict ticker -> (tage, kurse) oder None (tot).
    """
    zustand = {"runde": 0, "gesehen": set()}

    def f(ticker):
        # Neue Runde, sobald ein Ticker zum zweiten Mal drankommt.
        if ticker in zustand["gesehen"]:
            zustand["runde"] += 1
            zustand["gesehen"] = set()
        zustand["gesehen"].add(ticker)
        idx = min(zustand["runde"], len(runden) - 1)
        daten = runden[idx].get(ticker)
        if daten is None:
            return pipe.FetchOutcome(None, pipe.EMPTY_DATA, "leer")
        if isinstance(daten, dict):          # Reihe MIT verworfener Zeile
            return pipe.FetchOutcome(**daten)
        return pipe.FetchOutcome(daten)
    return f


# ---------------------------------------------------------------------------
# 1 · Die Auslöse-Schwelle
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("verworfen, universum, soll", [
    (0, 117, False),      # der Normalfall
    (1, 117, False),      # EIN Ticker loest NICHTS aus (sonst laeuft es taeglich)
    (58, 117, False),     # 49,6 % — knapp unter der Mehrheit
    (59, 117, True),      # 50,4 % — Mehrheit erreicht
    (116, 117, True),     # der reale DE-Abendfall
    (117, 117, True),
    (5, 0, False),        # leeres Universum -> keine Division, kein Ausloeser
])
def test_die_schwelle_ist_die_MEHRHEIT_der_ticker(verworfen, universum, soll):
    """Von Hand: 58/117 = 49,57 % < 50 % · 59/117 = 50,43 % >= 50 %."""
    assert pipe.wiederholung_noetig(verworfen, universum) is soll


def test_die_schwelle_haengt_an_einer_benannten_konstante():
    assert config.RETRY_LAST_ROW_SHARE == 0.5
    assert config.RETRY_MAX_ATTEMPTS == 2
    assert config.RETRY_PAUSE_SECONDS == 180
    # und sie ist überschreibbar, ohne den Aufrufer zu ändern
    assert pipe.wiederholung_noetig(10, 100, share=0.05) is True
    assert pipe.wiederholung_noetig(10, 100, share=0.5) is False


# ---------------------------------------------------------------------------
# 2 · „Nie verschlechtern" — das Auswahlkriterium
# ---------------------------------------------------------------------------
def _s(datum, am_juengsten, tickers=117):
    return {"last_bar_max": datum, "tickers_at_last_bar": am_juengsten,
            "tickers": tickers}


@pytest.mark.parametrize("neu, alt, soll, warum", [
    (_s("2026-08-05", 117), _s("2026-08-04", 117), True, "jüngeres Datum"),
    (_s("2026-08-04", 117), _s("2026-08-04", 116), True, "gleiches Datum, mehr Ticker"),
    (_s("2026-08-04", 116), _s("2026-08-04", 116), False, "GLEICHSTAND ist keine Verbesserung"),
    (_s("2026-08-03", 117), _s("2026-08-04", 1), False, "älteres Datum schlägt nie durch"),
    (_s("2026-08-04", 5), _s("2026-08-04", 117), False, "gleiches Datum, WENIGER Ticker"),
    (None, _s("2026-08-04", 117), False, "kein Ergebnis ist nie besser"),
    (_s(None, 0), _s("2026-08-04", 117), False, "kein Bar-Datum ist nie besser"),
    (_s("2026-08-04", 117), None, True, "gegen gar nichts gewinnt jedes Ergebnis"),
    (_s("2026-08-04", 117), _s(None, 0), True, "gegen ein leeres Ergebnis ebenso"),
])
def test_besser_heisst_juengeres_datum_ODER_mehr_ticker(neu, alt, soll, warum):
    assert pipe.versuch_besser(neu, alt) is soll, warum


def test_das_kriterium_ist_deterministisch():
    """Zweimal dieselbe Frage, zweimal dieselbe Antwort — und antisymmetrisch:
    wenn A besser als B ist, ist B nicht besser als A."""
    a, b = _s("2026-08-05", 100), _s("2026-08-04", 117)
    for _ in range(2):
        assert pipe.versuch_besser(a, b) is True
        assert pipe.versuch_besser(b, a) is False
    gleich = _s("2026-08-04", 117)
    assert pipe.versuch_besser(gleich, dict(gleich)) is False
    assert pipe.versuch_besser(dict(gleich), gleich) is False


# ---------------------------------------------------------------------------
# 3 · Der volle Weg durch build_market
# ---------------------------------------------------------------------------
def _baue(monkeypatch, *runden, tickers=("A", "B", "C", "D")):
    _markt(monkeypatch, tickers)
    pausen = []
    preise, volumen = {}, {}
    m = pipe.build_market("TEST", _fetcher_folge(*runden), None,
                          preise, volumen, sleeper=pausen.append)
    return m, pausen, preise


def test_OHNE_verworfene_zeilen_laeuft_genau_EIN_abruf(monkeypatch):
    """Die Laufzeit an normalen Tagen bleibt unverändert — das ist die
    Voraussetzung dafür, dass dieser PR harmlos ist."""
    gut = {t: _reihe(60, "2026-08-05") for t in ("A", "B", "C", "D")}
    m, pausen, _ = _baue(monkeypatch, gut, gut)
    assert pausen == [], "es darf gar nicht geschlafen werden"
    prot = m["diag"]["fetch_attempts"]
    assert len(prot) == 1 and prot[0]["attempt"] == 1
    assert prot[0]["dropped_last_row"] == 0
    assert m["diag"]["last_bar_date"] == "2026-08-05"


def _mit_kaputter_letzter_zeile(tickers, ende, n=60):
    """Der DE-Abendfall: die Quelle liefert die Zeile für ``ende``, aber
    nicht-finit — der Parser verwirft sie, die Reihe endet einen Tag früher.

    Nachgebildet auf der Ebene des FETCH-VERTRAGS (``FetchOutcome``), nicht mit
    einem rohen NaN: das Verwerfen passiert in ``parse_download_df``, und ein
    Test-Fetcher, der daran vorbeigeht, würde die Zähler nie setzen — dann
    misst der Test die Auslöse-Schwelle gar nicht.
    """
    aus = {}
    for t in tickers:
        tage, kurse = _reihe(n, ende)
        aus[t] = {"data": (tage[:-1], kurse[:-1]), "dropped_bars": 1,
                  "dropped_dates": (tage[-1],), "dropped_last_row": 1}
    return aus


def test_a_ZWEITER_VERSUCH_BESSER_wird_uebernommen(monkeypatch):
    """Runde 1: letzte Zeile bei allen vier kaputt -> Markt auf dem 04.08.
    Runde 2: sauber -> 05.08. Von Hand: jüngeres Datum, also übernommen."""
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    gut = {t: _reihe(60, "2026-08-05") for t in tickers}
    m, pausen, preise = _baue(monkeypatch, kaputt, gut)
    assert pausen == [config.RETRY_PAUSE_SECONDS], "genau EINE Pause"
    prot = m["diag"]["fetch_attempts"]
    assert len(prot) == 2
    assert prot[0]["last_bar_date"] == "2026-08-04" and prot[0]["dropped_last_row"] == 4
    assert prot[1]["last_bar_date"] == "2026-08-05" and prot[1]["adopted"] is True
    assert m["diag"]["last_bar_date"] == "2026-08-05", "der Sieger steht im Report"
    assert m["diag"]["dropped_last_row"] == 0, "auch die Zähler kommen vom Sieger"
    # und die KURSE stammen vollständig aus dem zweiten Versuch
    assert preise["A"][0][-1] == "2026-08-05"


def test_b_ZWEITER_VERSUCH_GLEICH_erster_bleibt(monkeypatch):
    """Beide Runden identisch kaputt. Gleichstand ist KEINE Verbesserung —
    der erste Abruf bleibt, und zwar unverändert."""
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    m, pausen, preise = _baue(monkeypatch, kaputt, dict(kaputt))
    assert pausen == [config.RETRY_PAUSE_SECONDS]
    prot = m["diag"]["fetch_attempts"]
    assert len(prot) == 2 and prot[1]["adopted"] is False
    assert m["diag"]["last_bar_date"] == "2026-08-04"
    assert preise["A"][0][-1] == "2026-08-04"
    # Gegenprobe: das Ergebnis ist byte-identisch mit einem Lauf OHNE Wiederholung
    _markt(monkeypatch, tickers)
    ohne = pipe.build_market("TEST", _fetcher_folge(kaputt), None, {}, {},
                             sleeper=lambda s: None)
    a = {k: v for k, v in m["diag"].items() if k != "fetch_attempts"}
    b = {k: v for k, v in ohne["diag"].items() if k != "fetch_attempts"}
    assert a == b, "der verworfene Versuch hat Spuren hinterlassen"
    assert m["candidates"] == ohne["candidates"]


def test_c_ZWEITER_VERSUCH_SCHLECHTER_erster_bleibt(monkeypatch):
    """Runde 2 liefert einen ÄLTEREN Stand — sie darf nichts überschreiben."""
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")     # -> 04.08.
    aelter = {t: _reihe(50, "2026-07-31") for t in tickers}          # -> 31.07.
    m, pausen, preise = _baue(monkeypatch, kaputt, aelter)
    prot = m["diag"]["fetch_attempts"]
    assert prot[1]["last_bar_date"] == "2026-07-31"
    assert prot[1]["adopted"] is False, "ein älterer Stand darf NIE gewinnen"
    assert m["diag"]["last_bar_date"] == "2026-08-04"
    assert preise["A"][0][-1] == "2026-08-04", "die Kurse bleiben die des ersten Abrufs"


def test_d_ZWEITER_VERSUCH_WIRFT_erster_bleibt_und_es_wird_laut(monkeypatch, capsys):
    """Rate-Limit oder Netzfehler: abbrechen, ersten Abruf behalten, laut sein."""
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    _markt(monkeypatch, tickers)

    def krachender_sleeper(_s):
        raise RuntimeError("429 Too Many Requests")

    preise = {}
    m = pipe.build_market("TEST", _fetcher_folge(kaputt), None, preise, {},
                          sleeper=krachender_sleeper)
    ausgabe = capsys.readouterr().out
    assert "FEHLGESCHLAGEN" in ausgabe and "429" in ausgabe
    assert "erste Abruf bleibt gültig" in ausgabe
    prot = m["diag"]["fetch_attempts"]
    assert len(prot) == 2 and prot[1]["adopted"] is False
    assert "429" in prot[1]["error"]
    assert m["diag"]["last_bar_date"] == "2026-08-04"
    assert preise["A"][0][-1] == "2026-08-04"


def test_der_lauf_ist_bei_gleichen_eingaben_zweimal_gleich(monkeypatch):
    """Determinismus über den vollen Weg — inklusive Auswahl."""
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    gut = {t: _reihe(60, "2026-08-05") for t in tickers}
    erst, _, p1 = _baue(monkeypatch, kaputt, gut)
    zweit, _, p2 = _baue(monkeypatch, dict(kaputt), dict(gut))
    assert erst["diag"] == zweit["diag"]
    assert erst["candidates"] == zweit["candidates"]
    assert p1.keys() == p2.keys()


def test_hoechstens_EIN_wiederholungsversuch(monkeypatch):
    """Der Deckel: auch wenn Runde 2 wieder kaputt ist, wird nicht weiter
    versucht — die Zusatz-Laufzeit je Markt bleibt gedeckelt."""
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    m, pausen, _ = _baue(monkeypatch, kaputt, dict(kaputt), dict(kaputt))
    assert len(pausen) == config.RETRY_MAX_ATTEMPTS - 1 == 1
    assert len(m["diag"]["fetch_attempts"]) == config.RETRY_MAX_ATTEMPTS


def test_der_DECKEL_greift_auch_wenn_jeder_versuch_BESSER_waere(monkeypatch):
    """Nachgezogen (Mutationsprobe 06.08.2026): der vorige Test kam ohne den
    Deckel aus, weil die Schleife bei „nicht besser" ohnehin abbricht — eine
    entfernte Obergrenze blieb dort unbemerkt.

    Hier wird JEDE Runde besser (jüngeres Bar-Datum) UND bleibt über der
    Auslöse-Schwelle. Ohne Deckel liefe das immer weiter; mit Deckel ist nach
    dem zweiten Versuch Schluss — und der zweite Stand ist der, der gilt.
    """
    tickers = ("A", "B", "C", "D")
    r1 = _mit_kaputter_letzter_zeile(tickers, "2026-08-02")   # -> 01.08.
    r2 = _mit_kaputter_letzter_zeile(tickers, "2026-08-03")   # -> 02.08., besser
    r3 = _mit_kaputter_letzter_zeile(tickers, "2026-08-04")   # -> 03.08., noch besser
    m, pausen, _ = _baue(monkeypatch, r1, r2, r3)
    assert len(pausen) == 1, "genau EIN Wiederholungsversuch, egal wie verlockend"
    assert len(m["diag"]["fetch_attempts"]) == 2
    assert m["diag"]["last_bar_date"] == "2026-08-02", "der zweite Stand gilt"
    assert m["diag"]["fetch_attempts"][1]["adopted"] is True


def test_ein_EINZELNER_kaputter_ticker_loest_nichts_aus(monkeypatch):
    """25 % betroffen — unter der Mehrheit, also kein zweiter Abruf."""
    tickers = ("A", "B", "C", "D")
    gemischt = {t: _reihe(60, "2026-08-05") for t in tickers}
    gemischt["A"] = _mit_kaputter_letzter_zeile(("A",), "2026-08-05")["A"]
    m, pausen, _ = _baue(monkeypatch, gemischt, gemischt)
    assert pausen == []
    assert len(m["diag"]["fetch_attempts"]) == 1
    assert m["diag"]["dropped_last_row"] == 1


# ---------------------------------------------------------------------------
# 4 · Das Protokoll
# ---------------------------------------------------------------------------
def test_das_protokoll_nennt_je_versuch_die_kennzahlen(monkeypatch):
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    gut = {t: _reihe(60, "2026-08-05") for t in tickers}
    m, _, _ = _baue(monkeypatch, kaputt, gut)
    for zeile in m["diag"]["fetch_attempts"]:
        for feld in ("attempt", "pause_seconds", "last_bar_date", "tickers",
                     "tickers_at_last_bar", "dropped_last_row", "shape_digest"):
            assert feld in zeile, f"{feld} fehlt im Protokoll"
    a, b = m["diag"]["fetch_attempts"]
    assert a["pause_seconds"] == 0 and b["pause_seconds"] == config.RETRY_PAUSE_SECONDS
    assert a["shape_digest"] != b["shape_digest"], \
        "verschiedene Abrufe, verschiedene Reihenform — das ist der Beleg"
    assert a["tickers_at_last_bar"] == 4 and b["tickers_at_last_bar"] == 4


def test_die_lauf_status_zeile_zeigt_den_zweiten_versuch():
    html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert "function attemptsRow(d)" in html
    assert "${attemptsRow(d)}" in html
    start = html.index("      function attemptsRow(d) {")
    koerper = html[start:html.index("\n      }", start)]
    assert "d.fetch_attempts" in koerper
    # Bei genau EINEM Versuch bleibt die Zeile weg (kein Rauschen an normalen Tagen)
    assert "if (!Array.isArray(a) || a.length < 2) return '';" in koerper


# ---------------------------------------------------------------------------
# 5 · Grenzen: was dieser PR NICHT anfasst
# ---------------------------------------------------------------------------
def test_weder_gate_noch_waechter_noch_sammlung_kennen_den_wiederhol_abruf():
    for datei in ("scripts/forward_collection.py", "scripts/health_check.py",
                  "scripts/market_calendar.py"):
        quelle = (ROOT / datei).read_text(encoding="utf-8")
        for name in ("fetch_attempts", "wiederholung_noetig", "versuch_besser",
                     "RETRY_LAST_ROW_SHARE", "RETRY_PAUSE_SECONDS"):
            assert name not in quelle, f"{datei} greift auf {name} zu"


def test_die_cron_zeit_ist_unveraendert():
    wf = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert 'cron: "45 21 * * 1-5"' in wf


def test_es_gibt_keine_ersatzkurse_und_keine_interpolation():
    quelle = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    start = quelle.index("def _versuch(")
    ende = quelle.index("def _protokoll_zeile(")
    block = quelle[start:ende]
    for wort in ("interpol", "ffill", "fillna", "vorheriger_lauf", "cache"):
        assert wort not in block.lower(), f"{wort} im Wiederhol-Pfad"


# ---------------------------------------------------------------------------
# 6 · Wechselwirkung mit Wächter und Sammlungs-Gate (Auftragspunkt 5)
# ---------------------------------------------------------------------------
def test_ein_erfolgreicher_zweiter_abruf_macht_den_markt_frisch(monkeypatch):
    """Die gewollte Richtung, an einer Stelle nachgewiesen:

    Erster Abruf -> Markt auf dem 04.08. (Rückstand 1) -> Wächter meldet,
    Gate sperrt. Zweiter Abruf -> 05.08. (Rückstand 0) -> beide schweigen.
    Und genau DAS ist der Sinn: frischere Kurse heißt frischerer `entry_close`.
    """
    import forward_collection as fc
    import health_check as hc

    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    gut = {t: _reihe(60, "2026-08-05") for t in tickers}
    m, _, _ = _baue(monkeypatch, kaputt, gut)
    pipe._annotiere_bar_rueckstand(m, "2026-08-05T22:41:00Z")
    report = {"run_timestamp_utc": "2026-08-05T22:41:00Z", "markets": {"TEST": m}}

    assert m["diag"]["last_bar_date"] == "2026-08-05"
    assert m["diag"]["bar_lag_trading_days"] == 0
    assert sorted(fc.stale_markets(report)) == [], "das Gate sperrt einen frischen Markt nicht"
    assert hc.check_bar_freshness(report) == [], "und der Wächter schweigt zu Recht"

    # Gegenprobe OHNE gelungenen zweiten Abruf: beide schlagen an.
    _markt(monkeypatch, tickers)
    ohne = pipe.build_market("TEST", _fetcher_folge(kaputt), None, {}, {},
                             sleeper=lambda s: None)
    pipe._annotiere_bar_rueckstand(ohne, "2026-08-05T22:41:00Z")
    report2 = {"run_timestamp_utc": "2026-08-05T22:41:00Z", "markets": {"TEST": ohne}}
    assert ohne["diag"]["bar_lag_trading_days"] == 1
    assert sorted(fc.stale_markets(report2)) == ["TEST"]
    assert [f["severity"] for f in hc.check_bar_freshness(report2)] == ["warn"]


def test_die_sammlung_sieht_den_markt_GENAU_EINMAL(monkeypatch):
    """Keine Doppel-Anlage: der Wiederhol-Abruf läuft VOLLSTÄNDIG innerhalb von
    `build_market`. Die Sammlung wird erst danach und genau einmal je Lauf
    aufgerufen — sie sieht nur den Sieger, nie beide Versuche.

    Statisch belegt, weil genau das die Zusage ist: `update_forward_collection`
    kommt im Lauf exakt einmal vor, und zwar NACH der Markt-Schleife.
    """
    quelle = (ROOT / "scripts/elliott_pipeline.py").read_text(encoding="utf-8")
    assert quelle.count("fc.update_forward_collection(") == 1
    i_markt = quelle.index("markets[key] = build_market(")
    i_sammlung = quelle.index("fc.update_forward_collection(")
    assert i_markt < i_sammlung, "die Sammlung läuft nach den Märkten"
    # und der Wiederhol-Pfad selbst fasst die Sammlung nicht an
    start = quelle.index("def _versuch(")
    ende = quelle.index("def _annotiere_bar_rueckstand(")
    block = quelle[start:ende]
    assert "update_forward_collection" not in block
    assert "fc." not in block


def test_im_OFFLINE_modus_wird_NIE_wiederholt(monkeypatch):
    """Nachgezogen (Mutationsprobe 06.08.2026): mit einer auf 0 gesetzten
    Schwelle schlief die Suite echte Minuten, statt sauber rot zu werden —
    weil der Voll-Pipeline-Test den ECHTEN `time.sleep` benutzt.

    Synthetische Daten haben keine Quellen-Aussetzer. Der Offline-Modus
    wiederholt deshalb grundsätzlich nicht, egal wie die Schwelle steht.
    """
    monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
    monkeypatch.setattr(config, "RETRY_LAST_ROW_SHARE", 0.0)   # extremste Lage
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    m, pausen, _ = _baue(monkeypatch, kaputt, kaputt)
    assert pausen == [], "offline darf es keine Pause geben"
    assert len(m["diag"]["fetch_attempts"]) == 1


def test_auch_OHNE_umgebungsvariable_wiederholt_der_synthetische_fetcher_nicht(monkeypatch):
    """`build_report(fetch_synthetic, …)` setzt ELLIOTT_OFFLINE NICHT — genau
    dieser Pfad ließ die Suite bei der Schwellen-Mutation schlafen."""
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)
    monkeypatch.setattr(config, "RETRY_LAST_ROW_SHARE", 0.0)
    _markt(monkeypatch, ("A", "B"))
    pausen = []
    m = pipe.build_market("TEST", pipe.fetch_synthetic, None, {}, {},
                          sleeper=pausen.append)
    assert pausen == []
    assert len(m["diag"]["fetch_attempts"]) == 1


def test_ONLINE_wuerde_bei_derselben_lage_wiederholen(monkeypatch):
    """Gegenprobe, damit der Offline-Test nicht einfach alles abschaltet."""
    monkeypatch.delenv("ELLIOTT_OFFLINE", raising=False)
    tickers = ("A", "B", "C", "D")
    kaputt = _mit_kaputter_letzter_zeile(tickers, "2026-08-05")
    m, pausen, _ = _baue(monkeypatch, kaputt, dict(kaputt))
    assert pausen == [config.RETRY_PAUSE_SECONDS]
    assert len(m["diag"]["fetch_attempts"]) == 2


@pytest.mark.parametrize("grenze", [0.0, -0.1, 1.5, 2.0])
def test_eine_unbrauchbare_schwelle_schaltet_die_wiederholung_AB(grenze):
    """Nachgezogen (Mutationsprobe 06.08.2026): eine Schwelle von 0 heißt
    „immer wiederholen" — in der Suite legte das den Lauf schlafen, statt ihn
    rot zu machen. Unbrauchbare Werte gelten jetzt als „nicht wiederholen";
    dass der ECHTE Wert stimmt, prüft
    `test_die_schwelle_haengt_an_einer_benannten_konstante`.
    """
    assert pipe.wiederholung_noetig(117, 117, share=grenze) is False
    assert pipe.wiederholung_noetig(0, 117, share=grenze) is False
