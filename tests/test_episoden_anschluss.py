"""Episoden-Anschluss über KALENDERTAGE — der Mehrfach-Lauf-Defekt.

Warum es diese Datei gibt (01.08.2026): der Episoden-Anschluss hing an
``coll["last_run_date"]``, dem Datum des letzten LAUFS. Bei EINEM Lauf pro Tag
ist das dasselbe wie der Kalendertag — bei mehreren nicht: der erste Lauf des
Tages setzte das Datum bereits auf heute, und ein Record von gestern fand im
zweiten Lauf keinen Anschluss mehr. Er wurde zu einer zweiten Episode
zerschnitten, obwohl der Ticker an zwei konsekutiven Kalendertagen in den
Top 5 stand. Real beobachtet am 31.07.2026 (MTX.DE, G1A.DE, KKR nach drei
Hand-Dispatches am Vormittag) und an sechs weiteren Tagen.

Die Tests hier rechnen das SOLL von Hand aus und prüfen Werte, keine Aufrufe.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import forward_collection as fc  # noqa: E402


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------
W4_LABEL = "Impuls 1–5 · Long-Setup am Ende W4 (W5 erwartet)"


def kandidat(ticker, close=100.0, score=80.0, label=W4_LABEL):
    return {"ticker": ticker, "close": close, "score_heuristic": score,
            "count_label": label,
            "target_zone": {"low": 110.0, "high": 120.0},
            "target_zone_extended": {"low": 115.0, "high": 130.0},
            "invalidation_price": 90.0, "direction": "long",
            "chart_points": [], "count_wave_labels": [],
            "confluence": {"target": [], "invalidation": []}}


def report(*tickers, markt="DE", **kw):
    return {"markets": {markt: {"candidates": [kandidat(t, **kw)
                                               for t in tickers]}}}


def leere_sammlung():
    return {"schema_version": 1, "last_run_date": None,
            "prev_distinct_run_date": None, "updated_utc": None, "records": []}


def lauf(coll, tickers, run_date, now_iso, **kw):
    """Ein Lauf mit genau diesen Top-5-Tickern. Keine Kursdaten -> keine
    Reifung, damit die Tests ausschließlich den Anschluss messen."""
    fc.update_forward_collection(coll, report(*tickers, **kw), {},
                                 {"DE": "risk_on"}, run_date, now_iso)
    return coll


def records(coll, ticker):
    return [r for r in coll["records"] if r["ticker"] == ticker]


# ---------------------------------------------------------------------------
# 1) Die Anker selbst — Sollwerte von Hand
# ---------------------------------------------------------------------------
def test_ein_lauf_tag_ankert_auf_gestern_und_heute():
    coll = {"last_run_date": "2026-07-30", "prev_distinct_run_date": "2026-07-29"}
    assert fc.episode_anchor_dates(coll, "2026-07-31") == {
        "2026-07-31", "2026-07-30"}


def test_zweiter_lauf_desselben_tages_behaelt_den_gestrigen_anker():
    """Der Kern der Reparatur: nach dem ersten Lauf steht last_run_date bereits
    auf heute — der gestrige Anker muss aus prev_distinct_run_date kommen."""
    coll = {"last_run_date": "2026-07-31", "prev_distinct_run_date": "2026-07-30"}
    assert fc.episode_anchor_dates(coll, "2026-07-31") == {
        "2026-07-31", "2026-07-30"}


def test_allererster_lauf_hat_nur_heute():
    assert fc.episode_anchor_dates(leere_sammlung(), "2026-07-31") == {
        "2026-07-31"}


def test_migration_alter_stand_am_selben_tag_faellt_auf_das_alte_verhalten():
    """Sammlungs-Stand von VOR dem 01.08. (kein prev_distinct_run_date) und
    heute lief schon ein Lauf: das vorige distinct Datum ist unbekannt. Dann
    bleibt nur `run_date` — exakt das alte Verhalten, keine Verschlechterung."""
    coll = {"last_run_date": "2026-07-31"}          # Feld fehlt
    assert fc.episode_anchor_dates(coll, "2026-07-31") == {"2026-07-31"}
    # Beim ersten Lauf an einem NEUEN Kalendertag ist der Fall erledigt:
    assert fc.episode_anchor_dates(coll, "2026-08-03") == {
        "2026-08-03", "2026-07-31"}


def test_prev_distinct_wird_nur_beim_tageswechsel_fortgeschrieben():
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-30", "2026-07-30T22:45:00Z")
    assert coll["prev_distinct_run_date"] is None
    lauf(coll, ["AAA"], "2026-07-31", "2026-07-31T11:16:00Z")
    assert coll["prev_distinct_run_date"] == "2026-07-30"
    lauf(coll, ["AAA"], "2026-07-31", "2026-07-31T22:40:00Z")   # zweiter Lauf
    assert coll["prev_distinct_run_date"] == "2026-07-30"       # UNVERÄNDERT
    lauf(coll, ["AAA"], "2026-08-03", "2026-08-03T22:45:00Z")
    assert coll["prev_distinct_run_date"] == "2026-07-31"


# ---------------------------------------------------------------------------
# 2) Die realen Fälle — nachgestellt, mit von Hand nachgerechnetem Soll
# ---------------------------------------------------------------------------
def test_realer_31_07_fall_ergibt_je_EINEN_record():
    """MTX.DE, G1A.DE, KKR: am 30.07. Top-5, am 31.07. drei Hand-Dispatches
    am Vormittag OHNE sie, abends wieder dabei.

    Soll: je EIN Record mit last_seen 2026-07-31. Vor der Reparatur waren es
    je ZWEI (real nachweisbar in data/forward_collection.json, Stand 15aec42).
    """
    coll = leere_sammlung()
    lauf(coll, ["MTX.DE", "G1A.DE", "KKR"], "2026-07-30", "2026-07-30T22:45:00Z")
    # Drei Vormittags-Läufe am 31.07. mit anderen Tickern.
    for i, ts in enumerate(("11:15:36", "11:16:09", "11:20:44")):
        lauf(coll, ["HAG.DE", "GXI.DE"], "2026-07-31", f"2026-07-31T{ts}Z")
    # Abendlauf: die drei sind zurück.
    lauf(coll, ["MTX.DE", "G1A.DE", "KKR"], "2026-07-31", "2026-07-31T22:40:44Z")

    for t in ("MTX.DE", "G1A.DE", "KKR"):
        rs = records(coll, t)
        assert len(rs) == 1, f"{t}: {len(rs)} Records — Episode zerschnitten"
        assert rs[0]["last_seen_top5_date"] == "2026-07-31"
        assert rs[0]["created_utc"] == "2026-07-30T22:45:00Z"  # Anlage bleibt
    assert len(coll["records"]) == 5      # 3 + HAG.DE + GXI.DE, kein Doppel


def test_realer_30_07_fall_ADS_DE():
    """30.07.: ein Dispatch um 03:54, der Tageslauf um 22:45. ADS.DE war am
    29.07. Top-5, im Dispatch nicht, abends wieder."""
    coll = leere_sammlung()
    lauf(coll, ["ADS.DE"], "2026-07-29", "2026-07-29T22:37:21Z")
    lauf(coll, ["SAP.DE"], "2026-07-30", "2026-07-30T03:54:50Z")
    lauf(coll, ["ADS.DE"], "2026-07-30", "2026-07-30T22:45:00Z")
    assert len(records(coll, "ADS.DE")) == 1
    assert records(coll, "ADS.DE")[0]["last_seen_top5_date"] == "2026-07-30"


def test_realer_25_07_fall_ADS_DE_und_29_07_fall_EVK_DE():
    for ticker, tag_vorher, tag, ts1, ts2 in (
            ("ADS.DE", "2026-07-24", "2026-07-25", "04:38:00", "13:35:26"),
            ("EVK.DE", "2026-07-28", "2026-07-29", "18:14:26", "22:37:21")):
        coll = leere_sammlung()
        lauf(coll, [ticker], tag_vorher, f"{tag_vorher}T22:40:00Z")
        lauf(coll, ["ANDERS"], tag, f"{tag}T{ts1}Z")
        lauf(coll, [ticker], tag, f"{tag}T{ts2}Z")
        assert len(records(coll, ticker)) == 1, ticker
        assert records(coll, ticker)[0]["last_seen_top5_date"] == tag


# ---------------------------------------------------------------------------
# 3) Die Soll-Semantik in allen vier Lagen
# ---------------------------------------------------------------------------
def test_ein_lauf_tag_verlaengert_wie_bisher():
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-29", "2026-07-29T22:40:00Z")
    lauf(coll, ["AAA"], "2026-07-30", "2026-07-30T22:45:00Z")
    lauf(coll, ["AAA"], "2026-07-31", "2026-07-31T22:40:00Z")
    assert len(records(coll, "AAA")) == 1
    assert records(coll, "AAA")[0]["last_seen_top5_date"] == "2026-07-31"


@pytest.mark.parametrize("im_zwischenlauf_dabei", [True, False])
def test_mehrfach_lauf_tag_ist_idempotent_UND_friert_die_anlage_ein(
        im_zwischenlauf_dabei):
    """Mehrere Läufe am selben Tag mit ABWEICHENDEN Kandidaten-Werten.

    Soll: EIN Record; entry_close/score/Zonen stammen aus dem ERSTEN Lauf des
    Tages; nur last_seen_top5_date wandert mit. Von Hand: entry_close 100.0,
    score 80.0 — obwohl die späteren Läufe mit 999.0 / 1.0 hereinkommen.

    BEIDE Lagen: der Ticker ist im Zwischenlauf dabei (dann griff auch die
    alte Regel) ODER er fehlt (genau der geheilte Fall). Die Einfrier-
    Invariante muss in beiden gelten — sonst würde die Reparatur den zweiten
    Lauf des Tages die Anlage überschreiben lassen.
    """
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-30", "2026-07-30T22:45:00Z",
         close=100.0, score=80.0)
    vorher = copy.deepcopy(records(coll, "AAA")[0])
    for ts in ("06:00:00", "12:00:00"):
        lauf(coll, ["AAA"] if im_zwischenlauf_dabei else ["BBB"],
             "2026-07-31", f"2026-07-31T{ts}Z", close=999.0, score=1.0)
    lauf(coll, ["AAA"], "2026-07-31", "2026-07-31T22:40:00Z",
         close=999.0, score=1.0)
    rs = records(coll, "AAA")
    assert len(rs) == 1
    nachher = rs[0]
    assert nachher["entry_close"] == 100.0
    assert nachher["score_heuristic"] == 80.0
    assert nachher["created_utc"] == "2026-07-30T22:45:00Z"
    assert nachher["episode_id"] == vorher["episode_id"]
    # GENAU EIN Feld hat sich geändert:
    geaendert = {k for k in nachher if nachher[k] != vorher.get(k)}
    assert geaendert == {"last_seen_top5_date"}, geaendert
    assert nachher["last_seen_top5_date"] == "2026-07-31"


def test_luecken_tag_bleibt_eine_NEUE_episode():
    """Unterbrechung bleibt Unterbrechung: wer am letzten Lauf-Kalendertag
    nicht dabei war, bekommt eine neue Episode — auch mit der Reparatur."""
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-29", "2026-07-29T22:40:00Z")
    lauf(coll, ["BBB"], "2026-07-30", "2026-07-30T22:45:00Z")   # AAA fehlt
    lauf(coll, ["AAA"], "2026-07-31", "2026-07-31T22:40:00Z")   # AAA zurück
    rs = records(coll, "AAA")
    assert len(rs) == 2, "die Lücke muss eine zweite Episode erzeugen"
    assert [r["last_seen_top5_date"] for r in rs] == ["2026-07-29", "2026-07-31"]


def test_freitag_auf_montag_verlaengert():
    """Wochenende ist kein Lauf-Tag: der Anker trägt über die Lücke."""
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-31", "2026-07-31T22:40:00Z")   # Freitag
    lauf(coll, ["AAA"], "2026-08-03", "2026-08-03T22:45:00Z")   # Montag
    assert len(records(coll, "AAA")) == 1
    assert records(coll, "AAA")[0]["last_seen_top5_date"] == "2026-08-03"


def test_feiertags_bruecke_verlaengert_auch_ueber_mehrere_tage():
    """Vier Kalendertage ohne Lauf (Feiertag + Wochenende): der letzte LAUF-Tag
    ist der Anker, nicht 'gestern'."""
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-12-24", "2026-12-24T22:40:00Z")
    lauf(coll, ["AAA"], "2026-12-29", "2026-12-29T22:45:00Z")
    assert len(records(coll, "AAA")) == 1
    assert records(coll, "AAA")[0]["last_seen_top5_date"] == "2026-12-29"


def test_mehrfach_lauf_tag_verlaengert_auch_ueber_das_wochenende():
    """Kombination beider Lagen: Freitag Top-5, Montag zwei Läufe, im ersten
    fehlt der Ticker. Soll: EIN Record."""
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-31", "2026-07-31T22:40:00Z")   # Freitag
    lauf(coll, ["BBB"], "2026-08-03", "2026-08-03T04:00:00Z")   # Montag, Lauf 1
    lauf(coll, ["AAA"], "2026-08-03", "2026-08-03T22:45:00Z")   # Montag, Lauf 2
    assert len(records(coll, "AAA")) == 1
    assert records(coll, "AAA")[0]["last_seen_top5_date"] == "2026-08-03"


# ---------------------------------------------------------------------------
# 4) Wirkung auf den Score-Alarm — der Doppel-Alarm-Weg schließt sich
# ---------------------------------------------------------------------------
def test_alarm_feuert_in_lauf_1_und_schweigt_in_lauf_2_desselben_tages():
    """Der Kernbeweis aus dem Befund vom 31.07. — im DISKRIMINIERENDEN Fall.

    Der Doppel-Alarm entsteht NICHT, wenn der Ticker in jedem Lauf dabei ist
    (dann griff auch die alte Regel). Er entsteht, wenn die Flanke bereits
    gesetzt war und der Ticker in einem ZWISCHENLAUF desselben Tages fehlt:
    die alte Regel legte danach einen neuen Record mit
    ``score_alert_fired=None`` an — und pushte ein zweites Mal.

    QIA.DE liegt über der W4-Schwelle (88.20 bei end_of_w4). Der Zwischenstand
    läuft durch JSON, wie beim echten Commit zwischen zwei Läufen.
    """
    coll = leere_sammlung()
    rep = report("QIA.DE", score=88.69)

    # Tag 1: über der Schwelle -> genau EIN Alarm, Flanke gesetzt.
    fc.update_forward_collection(coll, rep, {}, {"DE": "risk_on"},
                                 "2026-07-30", "2026-07-30T22:45:00Z")
    edges1 = fc.score_alert_edges(coll, rep, "2026-07-30")
    assert [e["ticker"] for e in edges1] == ["QIA.DE"]
    assert edges1[0]["score"] == 88.69 and edges1[0]["setup"] == "end_of_w4"
    assert edges1[0]["threshold"] == 88.2
    assert records(coll, "QIA.DE")[0]["score_alert_fired"] == "2026-07-30"

    # Zwischenstand wird committet -> durch JSON und zurück.
    coll = json.loads(json.dumps(coll))

    # Tag 2, Lauf 1: QIA.DE ist NICHT in den Top 5.
    lauf(coll, ["ANDERS"], "2026-07-31", "2026-07-31T11:16:00Z")
    coll = json.loads(json.dumps(coll))          # auch dieser Stand ist committet

    # Tag 2, Lauf 2: QIA.DE zurück, immer noch über der Schwelle.
    # Soll: EIN Record, Flanke geerbt -> STILL.
    fc.update_forward_collection(coll, rep, {}, {"DE": "risk_on"},
                                 "2026-07-31", "2026-07-31T22:40:44Z")
    assert len(records(coll, "QIA.DE")) == 1, \
        "Episode zerschnitten -> die Flanke ginge verloren -> Doppel-Alarm"
    assert fc.score_alert_edges(coll, rep, "2026-07-31") == []
    assert records(coll, "QIA.DE")[0]["score_alert_fired"] == "2026-07-30"


def test_eine_ECHTE_neue_episode_darf_weiterhin_alarmieren():
    """Gegenprobe: die Flanke wird nicht generell erstickt. Nach einer Lücke
    ist es eine neue Episode — und die darf melden."""
    coll = leere_sammlung()
    rep = report("QIA.DE", score=88.69)
    lauf(coll, ["QIA.DE"], "2026-07-29", "2026-07-29T22:40:00Z", score=88.69)
    assert len(fc.score_alert_edges(coll, rep, "2026-07-29")) == 1
    lauf(coll, ["ANDERS"], "2026-07-30", "2026-07-30T22:45:00Z")   # Lücke
    fc.update_forward_collection(coll, rep, {}, {"DE": "risk_on"},
                                 "2026-07-31", "2026-07-31T22:40:00Z")
    assert len(records(coll, "QIA.DE")) == 2
    assert len(fc.score_alert_edges(coll, rep, "2026-07-31")) == 1


# ---------------------------------------------------------------------------
# 5) N×-Zähler zählt am Mehrfach-Lauf-Tag nicht doppelt
# ---------------------------------------------------------------------------
def test_appearance_count_am_mehrfach_lauf_tag():
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-30", "2026-07-30T22:45:00Z")
    lauf(coll, ["BBB"], "2026-07-31", "2026-07-31T11:16:00Z")   # AAA fehlt
    # Zweiter Lauf am 31.07.: AAA ist zurück und VERLÄNGERT -> weiterhin 1.
    assert fc.appearance_count(coll, "AAA", "2026-07-31") == 1
    # Ohne run_date bleibt es beim alten Anker (Rückwärtskompatibilität).
    assert fc.appearance_count(coll, "AAA") == 2
    # Ein Ticker, der noch nie da war, zählt als erste Erscheinung.
    assert fc.appearance_count(coll, "NEU", "2026-07-31") == 1


def test_annotate_appearance_counts_reicht_das_datum_durch():
    coll = leere_sammlung()
    lauf(coll, ["AAA"], "2026-07-30", "2026-07-30T22:45:00Z")
    lauf(coll, ["BBB"], "2026-07-31", "2026-07-31T11:16:00Z")
    rep = report("AAA")
    fc.annotate_appearance_counts(coll, rep, "2026-07-31")
    assert rep["markets"]["DE"]["candidates"][0]["appearance_count"] == 1


# ---------------------------------------------------------------------------
# 6) Determinismus des Anschlusses bei bereits zerschnittenen Alt-Episoden
# ---------------------------------------------------------------------------
def test_bei_zerschnittenen_alt_episoden_gewinnt_der_juengste_record():
    """Zwei offene Records desselben Tickers (Alt-Schaden). Der Anschluss muss
    den JÜNGEREN treffen — sonst würde der Schnitt fortgeschrieben."""
    coll = leere_sammlung()
    coll["last_run_date"] = "2026-07-31"
    coll["prev_distinct_run_date"] = "2026-07-30"
    coll["records"] = [
        {"ticker": "MTX.DE", "matured": False, "episode_id": "alt",
         "last_seen_top5_date": "2026-07-30"},
        {"ticker": "MTX.DE", "matured": False, "episode_id": "jung",
         "last_seen_top5_date": "2026-07-31"},
    ]
    anker = fc.episode_anchor_dates(coll, "2026-07-31")
    assert fc._open_episode(coll["records"], "MTX.DE", anker)["episode_id"] == "jung"
    # Reihenfolge in der Liste darf das Ergebnis nicht drehen.
    coll["records"].reverse()
    assert fc._open_episode(coll["records"], "MTX.DE", anker)["episode_id"] == "jung"


def test_gereifte_records_werden_nie_verlaengert():
    coll = leere_sammlung()
    coll["last_run_date"] = "2026-07-30"
    coll["records"] = [{"ticker": "AAA", "matured": True, "episode_id": "reif",
                        "last_seen_top5_date": "2026-07-30"}]
    anker = fc.episode_anchor_dates(coll, "2026-07-31")
    assert fc._open_episode(coll["records"], "AAA", anker) is None
