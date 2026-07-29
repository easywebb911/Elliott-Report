"""Selbsttests mit BEKANNTER ANTWORT für das Auswertungs-Programm v1.

Der Kern dieser Datei ist Punkt 6 des Auftrags: künstliche Datensätze, deren
richtige Antwort VORHER feststeht, werden durch das Programm geschickt — und es
muss das Richtige sagen. Ein Auswertungsprogramm, das man nur an echten Daten
ausprobiert, kann man nicht widerlegen; eines, das an Rauschen „Signal" ruft,
fällt hier durch.

Die echte Sammlung wird dabei nie angefasst (eigene Fixtures, kein Schreiben).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate as ev  # noqa: E402
import forward_collection as fc  # noqa: E402

# In den Tests kleinere Ziehungszahlen: die Auflösung des p-Werts liegt bei
# 1/(2000+1) ≈ 0,0005 und damit weit unter alpha — für ein Ja/Nein-Urteil
# vollkommen ausreichend, aber schnell genug für jeden PR-Lauf.
DRAWS = 2_000

RATIO_TARGET = 1.05     # Ziel 5 % über Einstieg
RATIO_INVAL = 0.95      # Ungültigkeitsmarke 5 % darunter


# ---------------------------------------------------------------------------
# Künstliche Welt: eine Kursreihe je Ticker + Records darauf
# ---------------------------------------------------------------------------
def _series(seed: int, bars: int = 400, start: float = 100.0, sigma: float = 0.02):
    rng = random.Random(seed)
    closes, c = [], start
    for _ in range(bars):
        closes.append(round(c, 4))
        c *= math.exp(rng.gauss(0.0, sigma))
    # Handelstage: fortlaufende Werktage ab 2026-01-05 (Montag)
    import datetime as dt
    d, dates = dt.date(2026, 1, 5), []
    while len(dates) < bars:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    return {"dates": dates, "closes": closes}


def _welt(n_ticker: int = 8, seed: int = 1):
    return {f"T{i}": _series(seed * 100 + i) for i in range(n_ticker)}


def _record(tid: str, ser, idx: int, score: float, hit: int, eid: str):
    entry = ser["closes"][idx]
    return {
        "episode_id": eid, "ticker": tid, "market": "US", "matured": True,
        "first_seen_date": ser["dates"][idx],
        "entry_close": entry,
        "invalidation_price": round(entry * RATIO_INVAL, 4),
        "target_zone": {"low": round(entry * RATIO_TARGET, 4),
                        "high": round(entry * RATIO_TARGET * 1.02, 4)},
        "target_zone_extended": {"low": round(entry * 1.10, 4),
                                 "high": round(entry * 1.12, 4)},
        "score_heuristic": score, "target_hit": hit,
        "pre_reached_target": False, "pre_reached_ext": False,
        "count_wave_labels": [{"wave": w} for w in range(5)],
    }


def _kandidaten(welt, von: int = 40, bis: int = 300):
    """Alle (ticker, index, wahres Ergebnis) im Ziehungsfenster."""
    out = []
    for tid, ser in welt.items():
        for i in range(von, bis):
            h = ev.simulate_hit(ser["closes"], i, RATIO_TARGET, RATIO_INVAL)
            if h is not None:
                out.append((tid, i, h))
    return out


def _sammlung(records):
    return {"schema_version": 1, "last_run_date": "2026-07-28",
            "records": records}


def _lauf(coll, welt, **kw):
    kw.setdefault("bench_draws", DRAWS)
    kw.setdefault("bootstrap_draws", DRAWS)
    kw.setdefault("perm_draws", DRAWS)
    kw.setdefault("now", "2026-07-28T00:00:00Z")
    return ev.run(coll, welt, **kw)


# ---------------------------------------------------------------------------
# SELBSTTEST 1 — REINES RAUSCHEN → KEIN SIGNAL
# Soll-Antwort: Die Fälle sind selbst zufällig gezogen; sie stammen also aus
# genau der Verteilung, gegen die verglichen wird. Ein Programm, das hier ein
# Signal meldet, würde später einen Zufallsbefund zur Bestätigung erklären.
# ---------------------------------------------------------------------------
def test_selbsttest_rauschen_kein_signal():
    welt = _welt(seed=1)
    rng = random.Random(4242)
    kand = _kandidaten(welt)
    rng.shuffle(kand)
    recs = [_record(t, welt[t], i, rng.uniform(40, 95), h, f"{t}@{n}")
            for n, (t, i, h) in enumerate(kand[:120])]
    res = _lauf(_sammlung(recs), welt)

    assert res["gueltig"] is True
    b = res["primaer"]["trefferquote_vs_zufall"]
    assert b["durchfuehrbar"] is True
    # Die beobachtete Quote liegt im Bereich der Zufalls-Quote ...
    assert b["p_wert"] > ev.EVAL_ALPHA, b
    # ... und Holm bestätigt: kein Befund.
    assert res["holm"]["trefferquote_vs_zufall"]["signifikant"] is False
    # Punktzahl war zufällig -> keine Trennschärfe
    assert res["holm"]["score_trennschaerfe"]["signifikant"] is False
    assert res["urteil"]["belegt"] is False
    assert "nicht bestanden" in " ".join(res["fazit_klartext"])


# ---------------------------------------------------------------------------
# SELBSTTEST 2 — EINGEBAUTER STARKER ZUSAMMENHANG → SIGNAL ERKANNT
# Soll-Antwort: Wir wählen bewusst überwiegend Fälle, die gut ausgingen, und
# geben ihnen die höheren Punktzahlen. Beide Primär-Tests MÜSSEN anschlagen —
# ein Programm, das ein derart plumpes Signal übersieht, ist blind.
# ---------------------------------------------------------------------------
def test_selbsttest_starker_zusammenhang_signal_erkannt():
    welt = _welt(seed=2)
    rng = random.Random(99)
    kand = _kandidaten(welt)
    treffer = [k for k in kand if k[2] == 1]
    nieten = [k for k in kand if k[2] == 0]
    rng.shuffle(treffer)
    rng.shuffle(nieten)
    gewaehlt = treffer[:85] + nieten[:35]          # 85 von 120 gehen gut aus
    recs = [_record(t, welt[t], i,
                    rng.uniform(70, 95) if h else rng.uniform(30, 55),
                    h, f"{t}@{n}")
            for n, (t, i, h) in enumerate(gewaehlt)]
    res = _lauf(_sammlung(recs), welt)

    b = res["primaer"]["trefferquote_vs_zufall"]
    assert b["beobachtete_quote"] > b["zufalls_quote_mittel"]
    assert b["p_wert"] < 0.01, b
    a = res["primaer"]["score_trennschaerfe"]
    assert a["auc"] > 0.9 and a["ci_untergrenze"] > 0.5, a
    assert res["holm"]["trefferquote_vs_zufall"]["signifikant"] is True
    assert res["holm"]["score_trennschaerfe"]["signifikant"] is True
    assert res["urteil"]["belegt"] is True
    assert "bestanden" in " ".join(res["fazit_klartext"])


# ---------------------------------------------------------------------------
# SELBSTTEST 3 — PUNKTZAHL OHNE TRENNSCHÄRFE → UNTERGRENZE UNTER 0,5
# Soll-Antwort: Die Punktzahl zeigt genau in die falsche Richtung. Die
# Untergrenze des Intervalls muss unter 0,5 liegen — sonst würde das Programm
# eine wertlose Punktzahl durchwinken.
# ---------------------------------------------------------------------------
def test_selbsttest_punktzahl_ohne_trennschaerfe():
    welt = _welt(seed=3)
    rng = random.Random(7)
    kand = _kandidaten(welt)
    rng.shuffle(kand)
    gewaehlt = kand[:120]
    # Punktzahl VERKEHRT herum: schlechte Ausgänge bekommen die hohen Werte.
    recs = [_record(t, welt[t], i,
                    30.0 + 5 * (1 - h) + rng.random(), h, f"{t}@{n}")
            for n, (t, i, h) in enumerate(gewaehlt)]
    res = _lauf(_sammlung(recs), welt)

    a = res["primaer"]["score_trennschaerfe"]
    assert a["durchfuehrbar"] is True
    assert a["auc"] < 0.5, a
    assert a["ci_untergrenze"] < 0.5, a
    assert res["urteil"]["belegt"] is False
    assert "nicht bestanden" in " ".join(res["fazit_klartext"])


# ---------------------------------------------------------------------------
# SELBSTTEST 4 — GRENZFALL AN DER FALLZAHL-SPERRE
# Soll-Antwort: 99 auswertbare Fälle -> KEIN offizielles Ergebnis, nur eine
# ausdrücklich ungültige Vorschau. 100 -> offiziell. Die Sperre ist die
# wichtigste Zahl im ganzen Register.
# ---------------------------------------------------------------------------
def _n_faelle(n: int, welt, seed: int = 11):
    rng = random.Random(seed)
    kand = _kandidaten(welt)
    rng.shuffle(kand)
    return _sammlung([_record(t, welt[t], i, rng.uniform(40, 95), h, f"{t}@{k}")
                      for k, (t, i, h) in enumerate(kand[:n])])


def test_selbsttest_grenzfall_sperre_99_verweigert():
    welt = _welt(seed=4)
    coll = _n_faelle(ev.EVAL_MIN_N - 1, welt)
    assert fc.eval_counts(coll)[2] == 99
    with pytest.raises(RuntimeError) as exc:
        _lauf(coll, welt)
    assert "99" in str(exc.value) and "vorschau" in str(exc.value).lower()

    res = _lauf(coll, welt, vorschau=True)
    assert res["gueltig"] is False and res["modus"] == "vorschau"
    assert res["urteil"]["belegt"] is False
    assert res["fazit_klartext"][0].startswith("VORSCHAU — NICHT GÜLTIG")


def test_selbsttest_grenzfall_sperre_zaehlt_auswertbar_nicht_gereift():
    """Der Fall, der real vorkommt: genug GEREIFTE, zu wenige AUSWERTBARE.

    104 gereift, 10 davon per PRU-Guard ausgeschlossen -> 94 auswertbar. Die
    Sperre muss greifen. Ohne diesen Test bliebe eine Sperre auf `gereift`
    unentdeckt (Guardian-Mutationsprobe 28.07.) — und die Registry nennt
    ausdrücklich `eval_counts(...)[2]`, weil PRU-Ausschlüsse (MET, D, PRU)
    genau diese Lücke im Bestand erzeugt haben.
    """
    welt = _welt(seed=4)
    coll = _n_faelle(ev.EVAL_MIN_N + 4, welt, seed=17)
    for r in coll["records"][:10]:
        r["pre_reached_target"] = True
    assert fc.eval_counts(coll)[1] == 104      # gereift: über der Schwelle
    assert fc.eval_counts(coll)[2] == 94       # auswertbar: darunter

    with pytest.raises(RuntimeError) as exc:
        _lauf(coll, welt)
    assert "94" in str(exc.value)

    res = _lauf(coll, welt, vorschau=True)
    assert res["gueltig"] is False
    assert res["zaehlwerk"]["gereift"] == 104
    assert res["zaehlwerk"]["auswertbar"] == 94
    assert res["urteil"]["belegt"] is False


def test_selbsttest_grenzfall_sperre_100_offiziell():
    welt = _welt(seed=4)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    assert fc.eval_counts(coll)[2] == 100
    res = _lauf(coll, welt)
    assert res["gueltig"] is True and res["modus"] == "offiziell"
    assert not res["fazit_klartext"][0].startswith("VORSCHAU")


# ---------------------------------------------------------------------------
# POPULATION: nur auswertbar, Ausgeschlossene separat ausgewiesen
# ---------------------------------------------------------------------------
def test_population_schliesst_pru_records_aus_und_weist_sie_aus():
    welt = _welt(seed=5)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    ausgeschlossen = copy.deepcopy(coll["records"][:4])
    for i, r in enumerate(ausgeschlossen):
        r["episode_id"] = f"X{i}"
        r[["pre_reached_target", "pre_reached_ext",
           "pre_guard_contaminated", "pre_reached_target"][i]] = True
    coll["records"].extend(ausgeschlossen)

    res = _lauf(coll, welt)
    z = res["zaehlwerk"]
    assert z["gereift"] == 104 and z["auswertbar"] == 100
    assert z["ausgeschlossen_pru_guard"] == 4
    assert z["ausgeschlossen_gruende"]["pre_reached_target"] == 2
    assert z["ausgeschlossen_gruende"]["pre_reached_ext"] == 1
    assert z["ausgeschlossen_gruende"]["pre_guard_contaminated"] == 1
    assert res["primaer"]["score_trennschaerfe"]["faelle"] == 100


def test_population_drift_bricht_ab(monkeypatch):
    """Weicht die eigene Auswahl je von eval_counts ab, wird abgebrochen."""
    welt = _welt(seed=5)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    monkeypatch.setattr(fc, "eval_counts", lambda c: (100, 100, 77))
    with pytest.raises(AssertionError, match="Populations-Drift"):
        _lauf(coll, welt)


# ---------------------------------------------------------------------------
# NUR EINGEFRORENE FELDER — Zugriffs-Protokoll
# ---------------------------------------------------------------------------
class _Wachhund(dict):
    """Dict, das jeden Feldzugriff mitschreibt."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.gelesen = set()

    def get(self, key, default=None):
        self.gelesen.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.gelesen.add(key)
        return super().__getitem__(key)


def test_nur_eingefrorene_felder_gelesen():
    """Kein Zugriff ausserhalb der Liste — UND kein toter Eintrag darin.

    Die zweite Hälfte ist so wichtig wie die erste: eine Allowlist mit
    Feldern, die nie gelesen werden, gibt eine Sicherheit vor, die sie nicht
    hat (Guardian-Nit 28.07.).
    """
    welt = _welt(seed=6)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    for i, r in enumerate(coll["records"]):        # alle Sekundär-Felder füllen
        r["confluence"] = {"target": [], "invalidation": []}
        r["ambiguity_n"] = r["ambiguity_n_v2"] = 1 + (i % 2)
        r["agent_concern_level"] = ["none", "low", "high"][i % 3]
        r["alternation_observed"] = bool(i % 2)
        r["w5_momentum_divergence"] = bool(i % 2)
        r["vol_ratio_w3_w1"] = r["vol_ratio_w4_w3"] = r["vol_ratio_w2_w1"] = 1.1
        r["pre_guard_contaminated"] = False
    coll["records"] = [_Wachhund(r) for r in coll["records"]]
    _lauf(coll, welt)
    gelesen = set().union(*[r.gelesen for r in coll["records"]])
    unerlaubt = gelesen - set(ev.FROZEN_FIELDS)
    assert not unerlaubt, f"Feld ausserhalb der eingefrorenen Liste: {unerlaubt}"
    tot = set(ev.FROZEN_FIELDS) - gelesen
    assert not tot, f"Eintrag in FROZEN_FIELDS, der nie gelesen wird: {tot}"


def test_kein_heutiger_kurs_im_ergebnis():
    """Der Ausgang kommt aus `target_hit` von damals, nicht aus einer Rechnung.

    Beleg: dreht man NUR die eingefrorenen Ausgänge um und lässt die Kurse
    unangetastet, dreht sich das Ergebnis mit. Würde das Programm heimlich
    nachrechnen, bliebe die Trefferquote gleich.
    """
    welt = _welt(seed=6)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    a = _lauf(coll, welt)["primaer"]["trefferquote_vs_zufall"]["beobachtete_quote"]
    for r in coll["records"]:
        r["target_hit"] = 1 - r["target_hit"]
    b = _lauf(coll, welt)["primaer"]["trefferquote_vs_zufall"]["beobachtete_quote"]
    assert abs((a + b) - 1.0) < 1e-9, (a, b)


# ---------------------------------------------------------------------------
# BENCHMARK-MECHANIK
# ---------------------------------------------------------------------------
def test_benchmark_ohne_kursbasis_nicht_durchfuehrbar():
    welt = _welt(seed=7)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    res = _lauf(coll, None)
    b = res["primaer"]["trefferquote_vs_zufall"]
    assert b["durchfuehrbar"] is False and "Kursbasis" in b["grund"]
    assert b["beobachtete_quote"] is not None      # die echte Quote bleibt sichtbar
    assert res["urteil"]["belegt"] is False        # ohne Vergleich nie „belegt"
    assert "nicht möglich" in " ".join(res["fazit_klartext"])


def test_benchmark_bei_luecken_in_der_kursbasis_nicht_durchfuehrbar():
    welt = _welt(seed=7)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    unvollstaendig = {k: v for k, v in welt.items() if k != "T3"}
    b = _lauf(coll, unvollstaendig)["primaer"]["trefferquote_vs_zufall"]
    assert b["durchfuehrbar"] is False and "unvollständig" in b["grund"]
    assert "T3" in b["fehlende_ticker"]


def test_simulate_hit_ist_die_reifungs_definition():
    """Gleichstand am selben Tag zählt als Ungültigkeit — nie als Treffer.

    Ein ECHTER Gleichstand (ein Bar erfüllt BEIDE Bedingungen) braucht bei
    Schlusskurs-Daten eine künstliche Konstellation — Ziel unterhalb der
    Ungültigkeitsmarke. In der echten Population kann das nicht auftreten
    (Ziel liegt immer über dem Einstieg, die Marke darunter). Trotzdem wird
    der Zweig hier geprüft: er ist die konservative Absicherung, und eine
    frühere Fassung dieses Tests prüfte in Wahrheit nur zwei aufeinander
    folgende Tage — die umgedrehte Gleichstands-Regel wäre unbemerkt
    durchgegangen (Guardian-Mutationsprobe 28.07.).
    """
    ein_bar = [100.0] + [90.0] * 12
    # 90 ist ≥ Ziel (85) UND ≤ Marke (95) — derselbe Bar, beide Bedingungen.
    assert ev.simulate_hit(ein_bar, 0, 0.85, 0.95) == 0
    # Gegenprobe: derselbe Bar, aber die Marke tiefer -> kein Gleichstand mehr
    assert ev.simulate_hit(ein_bar, 0, 0.85, 0.80) == 1

    closes = [100.0] + [95.0] + [110.0] * 12       # Marke einen Tag VOR dem Ziel
    assert ev.simulate_hit(closes, 0, 1.05, 0.95) == 0
    closes = [100.0] + [106.0] * 12                 # Ziel zuerst
    assert ev.simulate_hit(closes, 0, 1.05, 0.95) == 1
    assert ev.simulate_hit([100.0, 101.0], 0, 1.05, 0.95) is None   # zu kurz


# ---------------------------------------------------------------------------
# STATISTIK-BAUSTEINE
# ---------------------------------------------------------------------------
def test_auc_bekannte_werte():
    assert ev.auc([9, 8, 2, 1], [1, 1, 0, 0]) == 1.0        # perfekt
    assert ev.auc([1, 2, 8, 9], [1, 1, 0, 0]) == 0.0        # perfekt verkehrt
    assert ev.auc([5, 5, 5, 5], [1, 1, 0, 0]) == 0.5        # nur Gleichstände
    assert ev.auc([1, 2], [1, 1]) is None                    # eine Gruppe leer


def test_holm_reihenfolge_und_stopp():
    out = ev.holm({"a": 0.001, "b": 0.04}, alpha=0.05)
    assert out["a"]["signifikant"] is True                   # 0,001 <= 0,025
    assert out["b"]["signifikant"] is True                   # 0,04  <= 0,05
    out = ev.holm({"a": 0.03, "b": 0.04}, alpha=0.05)
    assert out["a"]["signifikant"] is False                  # 0,03 > 0,025 -> Stopp
    assert out["b"]["signifikant"] is False                  # Holm stoppt komplett
    assert out["a"]["p_korrigiert"] == pytest.approx(0.06)


def test_auc_intervall_nutzt_holm_niveau():
    welt = _welt(seed=8)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    res = _lauf(coll, welt)
    # zwei Primär-Tests -> Intervall auf 1 - alpha/2 = 97,5 %
    assert res["primaer"]["score_trennschaerfe"]["ci_niveau"] == pytest.approx(0.975)


# ---------------------------------------------------------------------------
# SEKUNDÄR — explorativ, Mindest-Fallzahl
# ---------------------------------------------------------------------------
def test_sekundaer_meldet_zu_wenige_faelle_statt_einer_zahl():
    welt = _welt(seed=9)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    # eine Gruppe künstlich klein halten: nur 5 Records mit Konfluenz
    for i, r in enumerate(coll["records"]):
        r["confluence"] = ({"target": ["52W-Hoch"], "invalidation": []}
                           if i < 5 else None)
    sek = _lauf(coll, welt)["sekundaer_explorativ"]
    assert sek["konfluenz"]["gruppen"]["mit"]["faelle"] == 5
    assert sek["konfluenz"]["gruppen"]["mit"]["quote"] is None
    assert sek["konfluenz"]["gruppen"]["mit"]["hinweis"] == "zu wenige Fälle"


def test_sekundaer_meldet_quote_ab_mindestfallzahl():
    welt = _welt(seed=9)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    for i, r in enumerate(coll["records"]):
        r["confluence"] = ({"target": ["52W-Hoch"], "invalidation": []}
                           if i < ev.SECONDARY_MIN_N else {"target": [],
                                                           "invalidation": []})
    sek = _lauf(coll, welt)["sekundaer_explorativ"]
    assert sek["konfluenz"]["gruppen"]["mit"]["faelle"] == ev.SECONDARY_MIN_N
    assert sek["konfluenz"]["gruppen"]["mit"]["quote"] is not None
    assert sek["konfluenz"]["gruppen"]["mit"]["hinweis"] is None


def test_sekundaer_deckt_die_beauftragten_dimensionen_ab():
    welt = _welt(seed=9)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    for i, r in enumerate(coll["records"]):
        r["confluence"] = {"target": [], "invalidation": []}
        r["ambiguity_n"] = 1 + (i % 2)
        r["ambiguity_n_v2"] = 1 + (i % 2)
        r["agent_concern_level"] = ["none", "low", "high"][i % 3]
        r["alternation_observed"] = bool(i % 2)
        r["w5_momentum_divergence"] = bool(i % 2)
        r["vol_ratio_w3_w1"] = 0.9 + 0.4 * (i % 2)
        r["vol_ratio_w4_w3"] = 0.9 + 0.4 * (i % 2)
        r["vol_ratio_w2_w1"] = 0.9 + 0.4 * (i % 2)
    sek = _lauf(coll, welt)["sekundaer_explorativ"]
    assert sorted(sek) == DIMENSIONEN_LAUT_AUFTRAG


# ---------------------------------------------------------------------------
# REPRODUZIERBARKEIT + GRENZEN
# ---------------------------------------------------------------------------
def test_zweimal_laufen_ergibt_identisches_ergebnis():
    welt = _welt(seed=10)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    a = _lauf(copy.deepcopy(coll), welt)
    b = _lauf(copy.deepcopy(coll), welt)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_anderer_seed_aendert_nur_die_ziehungen_nicht_die_daten():
    welt = _welt(seed=10)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    a = _lauf(coll, welt, seed=1)
    b = _lauf(coll, welt, seed=2)
    assert a["reproduzierbarkeit"]["seed"] != b["reproduzierbarkeit"]["seed"]
    # Die BEOBACHTETEN Daten hängen nie am Seed:
    for k in ("zaehlwerk", "sekundaer_explorativ"):
        assert a[k] == b[k]
    assert (a["primaer"]["trefferquote_vs_zufall"]["beobachtete_quote"]
            == b["primaer"]["trefferquote_vs_zufall"]["beobachtete_quote"])
    assert (a["primaer"]["score_trennschaerfe"]["auc"]
            == b["primaer"]["score_trennschaerfe"]["auc"])


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_sammlung_und_report_bleiben_unangetastet(tmp_path, capsys):
    """Nach einem echten Lauf sind Sammlung und Report byte-identisch."""
    coll_p = ROOT / "data/forward_collection.json"
    rep_p = ROOT / "data/report.json"
    vorher = (_hash(coll_p), _hash(rep_p))
    out = tmp_path / "ergebnis.json"
    rc = ev.main(["--sammlung", "data/forward_collection.json",
                  "--kurse", str(tmp_path / "gibt-es-nicht.json"),
                  "--out", str(out), "--vorschau",
                  "--now", "2026-07-28T00:00:00Z"])
    capsys.readouterr()
    assert rc == 0 and out.exists()
    assert (_hash(coll_p), _hash(rep_p)) == vorher


def test_ohne_vorschau_verweigert_das_programm_am_echten_stand(tmp_path, capsys):
    out = tmp_path / "ergebnis.json"
    rc = ev.main(["--out", str(out),
                  "--kurse", str(tmp_path / "gibt-es-nicht.json")])
    text = capsys.readouterr().out
    assert rc == 2 and not out.exists()
    assert "offizielles Ergebnis" in text and "--vorschau" in text


def test_laeuft_nicht_im_tageslauf():
    """Kein Workflow ruft es auf, kein Lauf-Modul importiert es."""
    for wf in (ROOT / ".github/workflows").glob("*.yml"):
        assert "evaluate" not in wf.read_text(encoding="utf-8"), wf.name
    for mod in ("elliott_pipeline.py", "notify.py", "health_check.py",
                "forward_collection.py"):
        src = (ROOT / "scripts" / mod).read_text(encoding="utf-8")
        assert not re.search(r"^\s*import evaluate|from evaluate", src, re.M), mod


def test_evaluate_holt_im_auswertungs_modus_nie_kurse(monkeypatch):
    """Die Auswertung selbst geht nie ins Netz — nur `--kurse-holen` tut das."""
    import builtins
    echt = builtins.__import__

    def wachhund(name, *a, **k):
        assert name != "yfinance", "Auswertung darf keine Kurse holen"
        return echt(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", wachhund)
    welt = _welt(seed=12)
    _lauf(_n_faelle(ev.EVAL_MIN_N, welt), welt)


def test_kurse_holen_vertraegt_die_multiindex_spalten(tmp_path, monkeypatch, capsys):
    """yfinance liefert bei manchen Aufrufen MultiIndex-Spalten.

    Das ist die teuerste Lektion des Repos (`parse_download_df`). Der
    Kursbasis-Modus muss sie vertragen, sonst steht der Zufalls-Vergleich
    später ohne Daten da — genau dann, wenn er gebraucht wird.
    """
    import types

    import pandas as pd

    idx = pd.date_range("2026-01-05", periods=4, freq="B")
    df = pd.DataFrame({("Close", "AAA"): [10.0, 11.0, 12.0, 13.0]}, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    fake = types.SimpleNamespace(download=lambda *a, **k: df)
    monkeypatch.setitem(sys.modules, "yfinance", fake)

    out = tmp_path / "kurse.json"
    payload = ev.fetch_prices({"records": [{"ticker": "AAA"}]}, out)
    capsys.readouterr()
    assert payload["kurse"]["AAA"]["closes"] == [10.0, 11.0, 12.0, 13.0]
    assert payload["kurse"]["AAA"]["dates"][0] == "2026-01-05"
    assert json.loads(out.read_text(encoding="utf-8"))["ticker"] == 1


def test_kurse_holen_ist_fail_soft_je_ticker(tmp_path, monkeypatch, capsys):
    import types

    def kaputt(*a, **k):
        raise RuntimeError("Netz weg")

    monkeypatch.setitem(sys.modules, "yfinance",
                        types.SimpleNamespace(download=kaputt))
    payload = ev.fetch_prices({"records": [{"ticker": "AAA"}]},
                              tmp_path / "kurse.json")
    capsys.readouterr()
    assert payload["kurse"] == {}          # kein Absturz, nur keine Daten
    assert payload["ticker_ohne_kurse"] == ["AAA"]


# ---------------------------------------------------------------------------
# EIN GESCHEITERTER ABRUF MUSS SICHTBAR SCHEITERN (29.07.2026)
# Der Trockenlauf zeigte: yfinance meldet einen Fehlschlag als LEEREN
# DataFrame, nicht als Ausnahme. Der landete als Schein-Eintrag mit 0 Bars in
# der Datei, das Log meldete Erfolg, der Rückgabewert war 0.
# ---------------------------------------------------------------------------
def _yf_mit(antworten):
    """Fake-yfinance: Ticker -> DataFrame (oder leer)."""
    import types

    import pandas as pd

    def download(t, *a, **k):
        n = antworten.get(t, 0)
        if not n:
            return pd.DataFrame()                      # genau der reale Fehlschlag
        idx = pd.date_range("2026-01-05", periods=n, freq="B")
        return pd.DataFrame({"Close": [100.0 + i for i in range(n)]}, index=idx)

    return types.SimpleNamespace(download=download)


def test_kurse_holen_schreibt_keine_scheineintraege(tmp_path, monkeypatch, capsys):
    """ALLE Abrufe leer → keine Datei mit Schein-Tickern, Rückgabewert ≠ 0."""
    monkeypatch.setitem(sys.modules, "yfinance", _yf_mit({}))
    monkeypatch.setattr(ev, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data/forward_collection.json").write_text(
        json.dumps({"records": [{"ticker": "AAA"}, {"ticker": "BBB.DE"}]}),
        encoding="utf-8")

    rc = ev.main(["--kurse-holen", "--kurse", "data/kurse.json"])
    text = capsys.readouterr().out
    assert rc != 0, "ein komplett gescheiterter Abruf darf nicht mit 0 enden"

    snap = json.loads((tmp_path / "data/kurse.json").read_text(encoding="utf-8"))
    assert snap["kurse"] == {}, "kein Schein-Eintrag mit 0 Bars"
    assert snap["ticker"] == 0 and snap["ticker_angefragt"] == 2
    assert sorted(snap["ticker_ohne_kurse"]) == ["AAA", "BBB.DE"]
    assert "OHNE KURSE: 2 von 2" in text and "UNVOLLSTÄNDIG" in text


def test_kurse_holen_meldet_den_einen_fehlenden_ticker_namentlich(
        tmp_path, monkeypatch, capsys):
    """Ein Ticker leer, Rest voll → Fehlliste namentlich, Rückgabewert ≠ 0."""
    monkeypatch.setitem(sys.modules, "yfinance",
                        _yf_mit({"AAA": 300, "BBB.DE": 300, "CCC": 0}))
    monkeypatch.setattr(ev, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data/forward_collection.json").write_text(
        json.dumps({"records": [{"ticker": t} for t in ("AAA", "BBB.DE", "CCC")]}),
        encoding="utf-8")

    rc = ev.main(["--kurse-holen", "--kurse", "data/kurse.json"])
    text = capsys.readouterr().out
    assert rc != 0
    snap = json.loads((tmp_path / "data/kurse.json").read_text(encoding="utf-8"))
    assert snap["ticker_ohne_kurse"] == ["CCC"]
    assert set(snap["kurse"]) == {"AAA", "BBB.DE"}      # die guten bleiben drin
    assert "CCC" in text and "OHNE KURSE: 1 von 3" in text


def test_kurse_holen_endet_mit_null_wenn_alles_da_ist(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "yfinance",
                        _yf_mit({"AAA": 300, "BBB.DE": 300}))
    monkeypatch.setattr(ev, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data/forward_collection.json").write_text(
        json.dumps({"records": [{"ticker": "AAA"}, {"ticker": "BBB.DE"}]}),
        encoding="utf-8")

    rc = ev.main(["--kurse-holen", "--kurse", "data/kurse.json"])
    capsys.readouterr()
    assert rc == 0
    snap = json.loads((tmp_path / "data/kurse.json").read_text(encoding="utf-8"))
    assert snap["ticker_ohne_kurse"] == [] and snap["ticker"] == 2


def test_kurse_holen_verwirft_versatz_zwischen_datum_und_kurs(
        tmp_path, monkeypatch, capsys):
    """Datum/Kurs unterschiedlich lang — der Defekt aus #53 kommt nicht rein."""
    import types

    import pandas as pd

    class Schief(pd.DataFrame):
        @property
        def index(self):                                # zu wenige Daten
            return pd.date_range("2026-01-05", periods=2, freq="B")

    df = Schief({"Close": [1.0, 2.0, 3.0, 4.0]})
    monkeypatch.setitem(sys.modules, "yfinance",
                        types.SimpleNamespace(download=lambda *a, **k: df))
    payload = ev.fetch_prices({"records": [{"ticker": "AAA"}]},
                              tmp_path / "kurse.json")
    text = capsys.readouterr().out
    assert payload["kurse"] == {} and payload["ticker_ohne_kurse"] == ["AAA"]
    assert "verworfen" in text


# ---------------------------------------------------------------------------
# ABWESENHEIT IST KEINE AUSSAGE — jede beauftragte Dimension erscheint
# ---------------------------------------------------------------------------
# UNABHÄNGIGE Referenzliste — bewusst ausgeschrieben, NICHT aus
# ev.SECONDARY_DIMS abgeleitet. Ein Vergleich der Konstante mit sich selbst ist
# tautologisch: er hätte ein stilles Entfernen nicht bemerkt (Guardian-Nit
# 29.07.). Wer hier eine Dimension streicht oder ergänzt, muss es zweimal tun —
# und merkt es dabei.
DIMENSIONEN_LAUT_AUFTRAG = [
    "agent_einwand", "alternation", "ambiguitaet_v1", "ambiguitaet_v2",
    "konfluenz", "momentum_divergenz", "setup_typ",
    "volumen_w2_zu_w1", "volumen_w3_zu_w1", "volumen_w4_zu_w3",
]


def test_dimensionsliste_deckt_sich_mit_dem_auftrag():
    assert sorted(ev.SECONDARY_DIMS) == DIMENSIONEN_LAUT_AUFTRAG
    assert len(ev.SECONDARY_DIMS) == 10


def test_alle_dimensionen_erscheinen_auch_ohne_faelle():
    welt = _welt(seed=16)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)      # nur count_wave_labels vorhanden
    sek = _lauf(coll, welt)["sekundaer_explorativ"]

    assert sorted(sek) == DIMENSIONEN_LAUT_AUFTRAG
    # setup_typ hat Daten, alles andere nicht — und sagt das auch
    assert sek["setup_typ"]["faelle_gesamt"] == ev.EVAL_MIN_N
    assert sek["setup_typ"]["hinweis"] is None
    for dim in ev.SECONDARY_DIMS:
        if dim == "setup_typ":
            continue
        assert sek[dim]["faelle_gesamt"] == 0, dim
        assert sek[dim]["hinweis"] == "keine Fälle", dim
        assert sek[dim]["gruppen"] == {}, dim
    # der Fall aus dem Trockenlauf, namentlich
    assert sek["momentum_divergenz"]["hinweis"] == "keine Fälle"


def test_dimension_mit_daten_traegt_keinen_keine_faelle_hinweis():
    welt = _welt(seed=16)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    for i, r in enumerate(coll["records"]):
        r["w5_momentum_divergence"] = bool(i % 2)
    sek = _lauf(coll, welt)["sekundaer_explorativ"]
    assert sek["momentum_divergenz"]["hinweis"] is None
    assert sek["momentum_divergenz"]["faelle_gesamt"] == ev.EVAL_MIN_N
    assert set(sek["momentum_divergenz"]["gruppen"]) == {"ja", "nein"}


# ---------------------------------------------------------------------------
# NENNUNGEN ≠ FÄLLE
# ---------------------------------------------------------------------------
def test_ausschluss_gruende_sind_als_nennungen_beschriftet():
    """Ein Record kann mehrere Gründe tragen — die Summe ist größer als die
    Fallzahl. Im Trockenlauf standen 13 Nennungen für 5 Fälle."""
    welt = _welt(seed=17)
    coll = _n_faelle(ev.EVAL_MIN_N, welt)
    doppelt = copy.deepcopy(coll["records"][:3])
    for i, r in enumerate(doppelt):
        r["episode_id"] = f"D{i}"
        r["pre_reached_target"] = True
        r["pre_reached_ext"] = True            # ZWEI Gründe, EIN Fall
    coll["records"].extend(doppelt)

    z = _lauf(coll, welt, vorschau=True)["zaehlwerk"]
    assert z["ausgeschlossen_pru_guard"] == 3                     # FÄLLE
    assert sum(z["ausgeschlossen_gruende"].values()) == 6         # NENNUNGEN
    assert z["ausgeschlossen_gruende_hinweis"] == (
        "Nennungen, Mehrfachnennung möglich — 3 betroffene Fälle")


# ---------------------------------------------------------------------------
# KLARTEXT
# ---------------------------------------------------------------------------
# Abkürzungen werden GROSS geprüft — „AUC" ohne Rücksicht auf Gross-/
# Kleinschreibung würde in jedem harmlosen „auch" anschlagen.
FACHBEGRIFFE_EXAKT = ["AUC", "CI", "ROC", "PRU"]
FACHBEGRIFFE = [
    "p-Wert", "p_wert", "Bootstrap", "Holm", "Konfidenz", "Signifikanz",
    "signifikant", "Population", "Perzentil", "Quantil", "Permutation",
    "Null-Verteilung", "Benchmark", "Seed", "korrigiert", "Intervall",
    "Trennschärfe", "Alpha", "Hypothese", "Verteilung", "Stichprobe",
    "point-in-time", "Record", "Episode", "gereift", "auswertbar",
]


@pytest.mark.parametrize("bauart", ["rauschen", "signal", "vorschau"])
def test_klartext_ohne_fachbegriffe(bauart):
    welt = _welt(seed=13)
    if bauart == "vorschau":
        res = _lauf(_n_faelle(50, welt), welt, vorschau=True)
    elif bauart == "signal":
        rng = random.Random(5)
        kand = _kandidaten(welt)
        tr = [k for k in kand if k[2] == 1]
        ni = [k for k in kand if k[2] == 0]
        rng.shuffle(tr), rng.shuffle(ni)
        recs = [_record(t, welt[t], i,
                        90.0 if h else 40.0, h, f"{t}@{n}")
                for n, (t, i, h) in enumerate(tr[:85] + ni[:35])]
        res = _lauf(_sammlung(recs), welt)
    else:
        res = _lauf(_n_faelle(ev.EVAL_MIN_N, welt), welt)

    text = " ".join(res["fazit_klartext"])
    treffer = [w for w in FACHBEGRIFFE if re.search(re.escape(w), text, re.I)]
    treffer += [w for w in FACHBEGRIFFE_EXAKT
                if re.search(rf"\b{re.escape(w)}\b", text)]
    assert not treffer, f"Fachbegriff im Klartext: {treffer}\n{text}"
    assert len(res["fazit_klartext"]) <= 7          # „wenige Sätze"


def test_klartext_sagt_ein_nein_genauso_deutlich():
    welt = _welt(seed=14)
    res = _lauf(_n_faelle(ev.EVAL_MIN_N, welt), welt)
    if not res["urteil"]["belegt"]:
        assert "nicht bestanden" in " ".join(res["fazit_klartext"])


def test_ausgabe_ist_zweiteilig():
    welt = _welt(seed=15)
    res = _lauf(_n_faelle(ev.EVAL_MIN_N, welt), welt)
    text = ev.render_text(res)
    assert "ZAHLEN ZUM NACHSCHLAGEN" in text
    for pflicht in ("zaehlwerk", "seed", "erstellt_utc", "definitionen"):
        assert pflicht in text
