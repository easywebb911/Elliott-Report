"""Auswertungsskript für den 07.12.2026 (Easy-Entscheid, PR 4 von 4).

Synthetische Sammlungen mit bekannter AUC — keine echten Daten, keine
Netzabhängigkeit. Deckt: Kohorten-Grenze am Stichtag (created_utc, nicht
first_seen_date), Schatten-Vergleich (identisch/besser/schlechter),
Modus-Schutz (--zaehlung/--auswerten/--vorzeitig), Schreibschutz
(data/docs), Mutationsproben.
"""
import datetime as _dt
import sys

import auswertung_stichtage as az
import evaluate as ev
import forward_collection as fc

ZAEHLREGEL_STICHTAG = az.ZAEHLREGEL_STICHTAG_UTC  # "2026-10-15T00:51:53Z"


def _rec(ticker, score, hit, *, matured=True, created_utc="2026-07-01T00:00:00Z",
        first_seen_date="2026-07-01", markiert=False, schatten=None,
        pre_reached_target=False, pre_reached_ext=False):
    return {
        "episode_id": f"{ticker}@{first_seen_date}", "ticker": ticker,
        "market": "US", "matured": matured, "first_seen_date": first_seen_date,
        "created_utc": created_utc,
        "pre_reached_target": pre_reached_target,
        "pre_reached_ext": pre_reached_ext, "pre_guard_contaminated": False,
        "score_heuristic": score, "target_hit": hit,
        "entry_close": 100.0, "invalidation_price": 90.0,
        "target_zone": {"low": 110.0, "high": 120.0},
        "invertiertes_risiko_bei_anlage": markiert,
        "score_shadow_inval_cap20": schatten,
    }


def _coll(records):
    return {"schema_version": 1, "records": records}


# ── AUC-Grundfälle (bekannte Konstruktion) ─────────────────────────────────
def test_perfekt_trennender_score_auc_eins():
    recs = ([_rec(f"H{i}", 90.0, 1) for i in range(20)]
           + [_rec(f"L{i}", 10.0, 0) for i in range(20)])
    cases, _ = ev.build_population(_coll(recs))
    assert ev.auc([c["score"] for c in cases], [c["hit"] for c in cases]) == 1.0


def test_zufallsscore_auc_um_0_5():
    # Scores alternierend unabhängig vom Treffer -> AUC nahe 0,5.
    recs = []
    for i in range(40):
        hit = i % 2
        score = 50.0 + (i % 5)  # score-Muster unabhängig von hit (i%2)
        recs.append(_rec(f"T{i}", score, hit))
    cases, _ = ev.build_population(_coll(recs))
    a = ev.auc([c["score"] for c in cases], [c["hit"] for c in cases])
    assert 0.3 <= a <= 0.7


# ── Kohorten-Grenze am Stichtag (created_utc, belegt) ──────────────────────
def test_record_genau_am_stichtag_gehoert_dazu():
    recs = [_rec("A", 50.0, 1, created_utc=ZAEHLREGEL_STICHTAG)]
    cases, _ = ev.build_population(_coll(recs))
    pred = az._kohorte_ab(ZAEHLREGEL_STICHTAG)
    fz = az.fallzahlen(recs, cases, pred)
    assert fz["n_gesamt"] == 1 and fz["n_reif"] == 1


def test_record_eine_sekunde_davor_gehoert_nicht_dazu():
    davor = "2026-10-15T00:51:52Z"  # eine Sekunde vor dem Stichtag
    recs = [_rec("A", 50.0, 1, created_utc=davor)]
    cases, _ = ev.build_population(_coll(recs))
    pred = az._kohorte_ab(ZAEHLREGEL_STICHTAG)
    fz = az.fallzahlen(recs, cases, pred)
    assert fz["n_gesamt"] == 0 and fz["n_reif"] == 0


def test_record_danach_gehoert_dazu():
    danach = "2026-10-15T00:51:54Z"
    recs = [_rec("A", 50.0, 1, created_utc=danach)]
    cases, _ = ev.build_population(_coll(recs))
    pred = az._kohorte_ab(ZAEHLREGEL_STICHTAG)
    fz = az.fallzahlen(recs, cases, pred)
    assert fz["n_gesamt"] == 1 and fz["n_reif"] == 1


def test_schatten_null_nicht_in_schatten_kohorte():
    recs = [_rec("A", 50.0, 1, schatten=None), _rec("B", 50.0, 1, schatten=55.0)]
    cases, _ = ev.build_population(_coll(recs))
    fz = az.fallzahlen(recs, cases, az._kohorte_schatten)
    assert fz["n_reif"] == 1
    assert fz["cases"][0]["rec"]["ticker"] == "B"


def test_unreife_records_zaehlen_nicht_in_n_reif():
    recs = [_rec("A", 50.0, 1, matured=False), _rec("B", 50.0, 1, matured=True)]
    cases, _ = ev.build_population(_coll(recs))
    fz = az.fallzahlen(recs, cases, az._kohorte_alle)
    assert fz["n_gesamt"] == 2 and fz["n_reif"] == 1


# ── Schatten-Vergleich: Verdikt-Fälle ──────────────────────────────────────
def _schatten_coll(live_scores, schatten_scores, hits, tickers=None):
    tickers = tickers or [f"T{i}" for i in range(len(live_scores))]
    recs = [_rec(t, s, h, schatten=sh) for t, s, sh, h in
           zip(tickers, live_scores, schatten_scores, hits)]
    return _coll(recs)


def test_schatten_identisch_zu_live_differenz_null_nicht_entscheidbar():
    n = 40
    live = [float(i % 10) for i in range(n)]
    hits = [1 if i % 2 == 0 else 0 for i in range(n)]
    coll = _schatten_coll(live, live, hits)  # Schatten == Live
    cases, _ = ev.build_population(coll)
    mit = az._mit_schatten_score(cases)
    d = az.differenz_mit_gepaartem_bootstrap(mit, "ticker", seed=42,
                                             bootstrap=200)
    assert d["differenz"] == 0.0
    assert az.verdikt(d["ci_untergrenze"], d["differenz"]) == "nicht entscheidbar"


def test_schatten_klar_besser_auf_konstruierten_daten_schatten_besser():
    n = 60
    hits = [1 if i < 30 else 0 for i in range(n)]
    # Live: fast keine Trennung. Schatten: perfekte Trennung.
    live = [50.0 + (i % 3) for i in range(n)]
    schatten = [90.0 if h == 1 else 10.0 for h in hits]
    coll = _schatten_coll(live, schatten, hits)
    cases, _ = ev.build_population(coll)
    mit = az._mit_schatten_score(cases)
    d = az.differenz_mit_gepaartem_bootstrap(mit, "ticker", seed=42,
                                             bootstrap=500)
    assert d["differenz"] > 0
    assert az.verdikt(d["ci_untergrenze"], d["differenz"]) == "Schatten besser"


def test_schatten_klar_schlechter_nicht_entscheidbar_nie_live_besser():
    n = 60
    hits = [1 if i < 30 else 0 for i in range(n)]
    schatten = [50.0 + (i % 3) for i in range(n)]  # Schatten: fast keine Trennung
    live = [90.0 if h == 1 else 10.0 for h in hits]  # Live: perfekt
    coll = _schatten_coll(live, schatten, hits)
    cases, _ = ev.build_population(coll)
    mit = az._mit_schatten_score(cases)
    d = az.differenz_mit_gepaartem_bootstrap(mit, "ticker", seed=42,
                                             bootstrap=500)
    assert d["differenz"] < 0
    v = az.verdikt(d["ci_untergrenze"], d["differenz"])
    assert v == "nicht entscheidbar"
    assert v != "Live besser", "es gibt laut Registry-Regel keinen solchen Stempel"
    assert v in ("Schatten besser", "nicht entscheidbar")


# ── Verdikt-Funktion isoliert ───────────────────────────────────────────
def test_verdikt_differenz_negativ_nicht_entscheidbar():
    assert az.verdikt(ci_untergrenze=0.1, differenz=-0.05) == "nicht entscheidbar"


def test_verdikt_differenz_positiv_aber_intervall_schliesst_null_ein():
    assert az.verdikt(ci_untergrenze=-0.01, differenz=0.05) == "nicht entscheidbar"


def test_verdikt_differenz_positiv_und_intervall_schliesst_null_aus():
    assert az.verdikt(ci_untergrenze=0.01, differenz=0.05) == "Schatten besser"


def test_verdikt_auc_nicht_definiert_none():
    assert az.verdikt(ci_untergrenze=float("nan"), differenz=None) == "nicht entscheidbar"


# ── Modus-Schutz ─────────────────────────────────────────────────────────
def test_auswerten_vor_dem_07_12_2026_wird_verweigert(capsys):
    rc = az.main(["--auswerten", "--jetzt", "2026-12-06T20:00:00+00:00"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "VERWEIGERT" in err


def test_auswerten_am_07_12_2026_selbst_ist_erlaubt(tmp_path, monkeypatch):
    monkeypatch.setattr(az, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    recs = [_rec(f"T{i}", float(i), i % 2) for i in range(40)]
    (tmp_path / "data" / "mini.json").write_text(
        __import__("json").dumps(_coll(recs)), encoding="utf-8")
    rc = az.main(["--auswerten", "--sammlung", "data/mini.json",
                 "--jetzt", "2026-12-07T00:00:01+01:00"])  # Berlin: 07.12. 00:00
    assert rc == 0


def test_vorzeitig_jede_zeile_traegt_explorativ_zusatz(capsys):
    rc = az.main(["--auswerten", "--vorzeitig",
                 "--jetzt", "2026-10-24T12:00:00+00:00"])
    assert rc == 0
    out = capsys.readouterr().out
    nicht_leere_zeilen = [z for z in out.splitlines() if z.strip()]
    for zeile in nicht_leere_zeilen:
        assert az.EXPLORATIV_ZUSATZ in zeile, f"Zeile ohne Zusatz: {zeile!r}"


def test_zaehlung_zeigt_nie_trefferquote_auc_verdikt(capsys):
    rc = az.main(["--zaehlung"])
    assert rc == 0
    out = capsys.readouterr().out
    for verbotenes_wort in ("Trefferquote", "AUC", "Schatten besser",
                            "nicht entscheidbar"):
        assert verbotenes_wort not in out


# ── Schreibschutz (data/docs) ───────────────────────────────────────────
def test_out_unter_data_wird_abgelehnt(capsys):
    rc = az.main(["--zaehlung", "--out", "data/sollte_nicht_entstehen.txt"])
    assert rc == 2
    assert "VERWEIGERT" in capsys.readouterr().err


def test_out_unter_docs_wird_abgelehnt(capsys):
    rc = az.main(["--zaehlung", "--out", "docs/sollte_nicht_entstehen.txt"])
    assert rc == 2


def test_out_ausserhalb_data_docs_ist_erlaubt(tmp_path, capsys):
    ziel = tmp_path / "bericht.txt"
    rc = az.main(["--zaehlung", "--out", str(ziel)])
    assert rc == 0
    assert ziel.exists()


# ── Mutationsproben (müssen rot werden) ────────────────────────────────
def test_mutation_schatten_und_live_vertauscht():
    """Würden Live- und Schatten-Score vertauscht, kippte das Vorzeichen
    der Differenz — ein 'Schatten besser'-Fall würde fälschlich
    'nicht entscheidbar' (oder umgekehrt)."""
    n = 60
    hits = [1 if i < 30 else 0 for i in range(n)]
    live = [50.0 + (i % 3) for i in range(n)]
    schatten = [90.0 if h == 1 else 10.0 for h in hits]
    coll = _schatten_coll(live, schatten, hits)
    cases, _ = ev.build_population(coll)
    mit = az._mit_schatten_score(cases)
    d_korrekt = az.differenz_mit_gepaartem_bootstrap(mit, "ticker", seed=42,
                                                      bootstrap=500)
    # Mutation: Felder vertauscht.
    mit_vertauscht = [dict(c, score=c["score_schatten"],
                           score_schatten=c["score"]) for c in mit]
    d_mutiert = az.differenz_mit_gepaartem_bootstrap(mit_vertauscht, "ticker",
                                                      seed=42, bootstrap=500)
    assert d_korrekt["differenz"] > 0
    assert d_mutiert["differenz"] < 0
    assert az.verdikt(d_korrekt["ci_untergrenze"], d_korrekt["differenz"]) == "Schatten besser"
    assert az.verdikt(d_mutiert["ci_untergrenze"], d_mutiert["differenz"]) != "Schatten besser"


def test_mutation_stichtag_vergleich_groessergleich_auf_groesser_gedreht():
    """Produktionscode nutzt `>=` (s. _kohorte_ab) — der Stichtag-Lauf
    selbst gehört dazu (belegt auf #186/#190). Eine gedrehte Variante `>`
    würde ihn fälschlich ausschließen."""
    pred_korrekt = az._kohorte_ab(ZAEHLREGEL_STICHTAG)
    rec_am_stichtag = _rec("A", 50.0, 1, created_utc=ZAEHLREGEL_STICHTAG)
    assert pred_korrekt(rec_am_stichtag) is True

    def pred_mutiert(rec):
        c = rec.get("created_utc")
        return bool(c) and c > ZAEHLREGEL_STICHTAG  # Mutation: > statt >=
    assert pred_mutiert(rec_am_stichtag) is False
    assert pred_korrekt(rec_am_stichtag) != pred_mutiert(rec_am_stichtag)


def test_mutation_verdikt_ohne_intervall_pruefung():
    """Würde die Intervall-Prüfung weggelassen (nur `differenz > 0`), gälte
    ein Fall mit positiver Differenz, aber einem Intervall, das 0 einschließt,
    fälschlich als 'Schatten besser'."""
    differenz = 0.05
    ci_untergrenze = -0.02  # schließt 0 EIN
    korrekt = az.verdikt(ci_untergrenze, differenz)
    assert korrekt == "nicht entscheidbar"

    def verdikt_mutiert(ci_untergrenze, differenz):
        if differenz is not None and differenz > 0:  # OHNE Intervall-Prüfung
            return "Schatten besser"
        return "nicht entscheidbar"
    mutiert = verdikt_mutiert(ci_untergrenze, differenz)
    assert mutiert == "Schatten besser"
    assert korrekt != mutiert


def test_mutation_kohorte_nach_first_seen_date_statt_created_utc():
    """Production nutzt `created_utc` (Lauf-Zeitstempel) — `first_seen_date`
    (Kursdatum) hat den dokumentierten Ein-Tage-Versatz und würde die
    Kohorten-Grenze verschieben."""
    # Record: first_seen_date liegt VOR dem Stichtag-Tag, created_utc DANACH
    # (realistischer Versatz: Kandidat erscheint am Vortag, Record entsteht
    # erst im Lauf des nächsten Tages).
    rec = _rec("A", 50.0, 1, created_utc="2026-10-15T00:51:53Z",
              first_seen_date="2026-10-14")
    pred_korrekt = az._kohorte_ab(ZAEHLREGEL_STICHTAG)
    assert pred_korrekt(rec) is True  # created_utc >= Stichtag -> dabei

    def pred_mutiert(r):
        d = r.get("first_seen_date")
        return bool(d) and d >= "2026-10-15"  # Mutation: first_seen_date statt created_utc
    assert pred_mutiert(rec) is False  # first_seen_date "2026-10-14" < "2026-10-15"
    assert pred_korrekt(rec) != pred_mutiert(rec)


def test_mutation_bootstrap_ungepaart_statt_gepaart():
    """Ungepaarte Ziehungen (Live und Schatten unabhängig voneinander
    resampelt) verzerren das Intervall — hier belegt, dass die gepaarte
    Rechnung bei identischen Scores IMMER Differenz 0 pro Ziehung liefert
    (korrekt), eine ungepaarte Variante das nicht garantiert."""
    n = 40
    live = [float(i % 10) for i in range(n)]
    hits = [1 if i % 2 == 0 else 0 for i in range(n)]
    coll = _schatten_coll(live, live, hits)
    cases, _ = ev.build_population(coll)
    mit = az._mit_schatten_score(cases)

    d_gepaart = az.differenz_mit_gepaartem_bootstrap(mit, None, seed=1,
                                                      bootstrap=300)
    assert d_gepaart["ci_untergrenze"] == 0.0 and d_gepaart["ci_obergrenze"] == 0.0

    # Mutation: Live und Schatten UNABHÄNGIG resampled (ungepaart).
    import random as _random
    rng_live = _random.Random(1)
    rng_schatten = _random.Random(2)  # anderer Seed -> andere Ziehung
    live_scores = [c["score"] for c in mit]
    schatten_scores = [c["score_schatten"] for c in mit]
    labels = [c["hit"] for c in mit]
    diffs = []
    for _ in range(300):
        idx_live = [rng_live.randrange(n) for _ in range(n)]
        idx_schatten = [rng_schatten.randrange(n) for _ in range(n)]
        a_l = ev.auc([live_scores[i] for i in idx_live],
                    [labels[i] for i in idx_live])
        a_s = ev.auc([schatten_scores[i] for i in idx_schatten],
                    [labels[i] for i in idx_schatten])
        if a_l is not None and a_s is not None:
            diffs.append(a_s - a_l)
    diffs.sort()
    # Bei identischen Score-Werten, aber UNABHÄNGIGEN Ziehungen, ist die
    # Differenz NICHT mehr garantiert exakt 0 in jeder Ziehung.
    assert any(d != 0.0 for d in diffs), (
        "Ungepaarte Ziehung müsste gelegentlich eine Differenz != 0 "
        "liefern, obwohl die Scores identisch sind — sonst taugt dieser "
        "Mutationstest nicht als Unterscheidungsmerkmal")


# ── Keine Schreibwirkung / harte Grenzen ────────────────────────────────
def test_evaluate_py_sha256_unveraendert():
    import hashlib
    from pathlib import Path
    pfad = Path(__file__).resolve().parent.parent / "scripts" / "evaluate.py"
    h = hashlib.sha256(pfad.read_bytes()).hexdigest()
    assert h == "bc697df91235732c6c386abe38c79a98248488b9f30a239d9c26c3cbb3b513fc"


def test_skript_nirgends_in_workflows_oder_produktionscode_referenziert():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    treffer = []
    for p in (root / ".github" / "workflows").glob("*.yml"):
        if "auswertung_stichtage" in p.read_text(encoding="utf-8"):
            treffer.append(p.name)
    for name in ("elliott_pipeline.py", "health_check.py", "notify.py"):
        if "auswertung_stichtage" in (root / "scripts" / name).read_text(encoding="utf-8"):
            treffer.append(name)
    assert treffer == [], f"Skript wird referenziert in: {treffer}"


def test_main_schreibt_nie_automatisch_ohne_modus_flag():
    import pytest
    with pytest.raises(SystemExit) as exc:
        az.main([])
    assert exc.value.code == 2  # argparse: mutually_exclusive_group required, fehlt -> Fehler


def test_fallzahlen_struktur_unveraendert_bei_doppeltem_aufruf():
    """Reine Funktion — zweimaliger Aufruf mit denselben Eingaben liefert
    byte-identisches Ergebnis (Determinismus, keine versteckte Zufallsuhr)."""
    recs = [_rec(f"T{i}", float(i), i % 2) for i in range(10)]
    cases, _ = ev.build_population(_coll(recs))
    a = az.fallzahlen(recs, cases, az._kohorte_alle)
    b = az.fallzahlen(recs, cases, az._kohorte_alle)
    assert {k: v for k, v in a.items() if k != "cases"} == \
          {k: v for k, v in b.items() if k != "cases"}


# ---------------------------------------------------------------------------
# Schatten-Stichtag belegt (NACHTRAG 30.10.2026, Easy-Entscheid): dieselbe
# >=-Grenze wie bei ZAEHLREGEL_STICHTAG/FILTER_STICHTAG oben, hier für
# SCHATTEN_STICHTAG_UTC — auch wenn die Schatten-Kohorte selbst feld-
# definiert bleibt (s. Moduldoc), ist der Zeitstempel jetzt ein normaler
# `_kohorte_ab`-Grenzwert wie die anderen beiden belegten Stichtage.
# ---------------------------------------------------------------------------
SCHATTEN_STICHTAG = az.SCHATTEN_STICHTAG_UTC  # "2026-10-27T01:37:06Z"


def test_schatten_stichtag_ist_belegt_nicht_mehr_none():
    assert SCHATTEN_STICHTAG is not None
    assert SCHATTEN_STICHTAG == "2026-10-27T01:37:06Z"


def test_schatten_stichtag_record_genau_am_stichtag_gehoert_dazu():
    recs = [_rec("A", 50.0, 1, created_utc=SCHATTEN_STICHTAG)]
    cases, _ = ev.build_population(_coll(recs))
    pred = az._kohorte_ab(SCHATTEN_STICHTAG)
    fz = az.fallzahlen(recs, cases, pred)
    assert fz["n_gesamt"] == 1 and fz["n_reif"] == 1


def test_schatten_stichtag_record_eine_sekunde_davor_gehoert_nicht_dazu():
    davor = "2026-10-27T01:37:05Z"
    recs = [_rec("A", 50.0, 1, created_utc=davor)]
    cases, _ = ev.build_population(_coll(recs))
    pred = az._kohorte_ab(SCHATTEN_STICHTAG)
    fz = az.fallzahlen(recs, cases, pred)
    assert fz["n_gesamt"] == 0 and fz["n_reif"] == 0


def test_schatten_stichtag_record_eine_sekunde_danach_gehoert_dazu():
    danach = "2026-10-27T01:37:07Z"
    recs = [_rec("A", 50.0, 1, created_utc=danach)]
    cases, _ = ev.build_population(_coll(recs))
    pred = az._kohorte_ab(SCHATTEN_STICHTAG)
    fz = az.fallzahlen(recs, cases, pred)
    assert fz["n_gesamt"] == 1 and fz["n_reif"] == 1


def test_bericht_zaehlung_zeigt_jetzt_den_belegten_schatten_stichtag():
    """Die Zeile zeigt nach dem Nachtrag den echten Zeitstempel statt
    'noch nicht belegt' (Auftrags-Vorgabe wörtlich)."""
    recs = [_rec("A", 50.0, 1)]
    cases, _ = ev.build_population(_coll(recs))
    text = az.bericht_zaehlung(recs, cases)
    assert f"Schatten-Stichtag (#194): {SCHATTEN_STICHTAG}" in text
    assert "noch nicht belegt" not in text


def test_mutationsprobe_schatten_stichtag_auf_none_zeigt_wieder_unbelegt():
    """Mutationsprobe (ohne Produktionscode zu verändern): wäre der Stichtag
    weiterhin None, stünde in der Zeile wieder 'noch nicht belegt' — belegt
    den Unterschied zum jetzt gesetzten Wert direkt."""
    recs = [_rec("A", 50.0, 1)]
    cases, _ = ev.build_population(_coll(recs))
    simuliert_unbelegt = f"Schatten-Stichtag (#194): {None or 'noch nicht belegt'}"
    assert simuliert_unbelegt == "Schatten-Stichtag (#194): noch nicht belegt"
    text = az.bericht_zaehlung(recs, cases)
    assert simuliert_unbelegt not in text
