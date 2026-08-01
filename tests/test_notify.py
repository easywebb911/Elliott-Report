"""Push-Paket Stufe 1: jeden Anlass offline durchgespielt + Stumm-Beweis +
Drosseln + Topic-Handhabung (kein Leak) + Fail-soft.

Kein Netz: `notify._post` wird ersetzt und die Pushes werden mitgeschnitten.
"""
import datetime as _dt
import json

import pytest

import notify


TOPIC = "easy-elliott-report"
MON = _dt.datetime(2026, 7, 27, 21, 45, tzinfo=_dt.timezone.utc)   # Montag
TUE = _dt.datetime(2026, 7, 28, 21, 45, tzinfo=_dt.timezone.utc)   # Dienstag


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notify, "_post",
        lambda url, data, headers, timeout: sent.append(
            {"url": url, "title": headers.get("Title"),
             "prio": headers.get("Priority"), "body": data.decode("utf-8")}))
    return sent


def _fixture_repo(tmp_path, monkeypatch, *, report_ts=None, matured=0, marker=False,
                  excluded=0):
    """``matured`` = gereifte Records insgesamt, davon ``excluded`` per PRU-Guard
    ausgeschlossen. AUSWERTBAR ist damit ``matured - excluded`` — genau die
    Unterscheidung, an der die Meilenstein-Zählung hängt."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    if report_ts is not None:
        (tmp_path / "data/report.json").write_text(
            json.dumps({"run_timestamp_utc": report_ts, "markets": {}}), encoding="utf-8")
    recs = [{"matured": True} for _ in range(matured)]
    for rec in recs[:excluded]:
        rec["pre_reached_target"] = True
    (tmp_path / "data/forward_collection.json").write_text(
        json.dumps({"records": recs}), encoding="utf-8")
    if marker:
        (tmp_path / "data/validation_milestone_fired.flag").write_text("x", encoding="utf-8")
    monkeypatch.setattr(notify, "REPO_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Pure Checks
# ---------------------------------------------------------------------------
def test_milestone_check():
    assert notify.milestone_reached(100, False) is True
    assert notify.milestone_reached(150, False) is True
    assert notify.milestone_reached(99, False) is False
    assert notify.milestone_reached(100, True) is False   # Marker -> schon gemeldet


def test_review_due_check():
    assert notify.review_due("2026-01-01", MON) is True        # überfällig + Montag
    assert notify.review_due("2027-01-01", MON) is False       # Zukunft
    assert notify.review_due("2026-01-01", TUE) is False       # nicht Montag
    assert notify.review_due(None, MON) is False               # abgeschaltet
    assert notify.review_due("nonsense", MON) is False         # fail-soft


# ---------------------------------------------------------------------------
# Anlass 1: Staleness (separater Cron)
# ---------------------------------------------------------------------------
def test_staleness_push_on_old_report(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-01T00:00:00Z")
    sent = _capture(monkeypatch)
    assert notify.run_staleness(TOPIC, MON) is True
    assert len(sent) == 1 and "veraltet" in sent[0]["title"].lower()


def test_staleness_silent_on_fresh_report(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z")
    sent = _capture(monkeypatch)
    assert notify.run_staleness(TOPIC, MON) is False
    assert sent == []


def test_staleness_push_when_report_missing(tmp_path, monkeypatch):
    # „Lauf fand gar nicht statt" / report.json fehlt -> Staleness-Signal.
    _fixture_repo(tmp_path, monkeypatch, report_ts=None)  # keine report.json
    sent = _capture(monkeypatch)
    assert notify.run_staleness(TOPIC, MON) is True
    assert len(sent) == 1


# ---------------------------------------------------------------------------
# Anlass 2: Meilenstein n>=100 (einmalig, Marker gegen Wiederholung)
# ---------------------------------------------------------------------------
def test_milestone_push_and_marker_written(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=100)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-01-01")  # Review aus
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)
    assert out["milestone"] is True and len(sent) == 1
    assert "Auswertung" in sent[0]["title"]
    assert (tmp_path / "data/validation_milestone_fired.flag").exists()  # Marker gesetzt


def test_milestone_throttled_by_marker(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z",
                  matured=120, marker=True)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-01-01")
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)
    assert out["milestone"] is False and sent == []   # Marker -> kein Doppel-Push


# --- ZÄHLWEISE: auswertbar, NICHT gereift -----------------------------------
# Registry und Frontend beziehen n>=EVAL_MIN_N auf AUSWERTBAR (gereift UND nicht
# per PRU-Guard ausgeschlossen). Die frühere Zählung nahm `gereift` — die
# größere Menge — und hätte zu früh gefeuert. Der Marker macht den Push
# einmalig, ein Fehlstart wäre also nicht nachholbar.
def test_milestone_zaehlt_auswertbar_nicht_gereift(tmp_path, monkeypatch):
    # 100 gereift, davon 5 ausgeschlossen -> 95 auswertbar -> Schwelle NICHT erreicht
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z",
                  matured=100, excluded=5)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-01-01")   # Review aus
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)
    assert out["milestone"] is False and sent == []
    # und der Marker darf NICHT gesetzt sein, sonst ginge der echte Meilenstein
    # später verloren
    assert not (tmp_path / "data/validation_milestone_fired.flag").exists()


def test_milestone_feuert_bei_100_auswertbar_trotz_ausschluessen(tmp_path, monkeypatch):
    # 105 gereift, davon 5 ausgeschlossen -> genau 100 auswertbar -> Push
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z",
                  matured=105, excluded=5)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-01-01")
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)
    assert out["milestone"] is True and len(sent) == 1
    # die gemeldete Zahl ist die auswertbare (100), nicht die gereifte (105)
    assert "100" in sent[0]["body"] and "105" not in sent[0]["body"]
    assert "auswertbar" in sent[0]["body"]
    assert "auswertbar" in (tmp_path / "data/validation_milestone_fired.flag"
                            ).read_text(encoding="utf-8")


def test_evaluable_count_ohne_forward_collection_zaehlt_null(tmp_path, monkeypatch):
    """Ohne forward_collection lieber kein Push als ein zu früher."""
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z",
                  matured=200)
    monkeypatch.setattr(notify, "_fc", None)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-01-01")
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)
    assert out["milestone"] is False and sent == []


def test_evaluable_count_nutzt_eval_counts_der_registry_quelle():
    """Kein zweiter Zähl-Pfad: notify zählt über forward_collection.eval_counts."""
    import forward_collection as fc
    coll = {"records": [{"matured": True} for _ in range(7)]
                       + [{"matured": True, "pre_guard_contaminated": True}]
                       + [{"matured": False}]}
    assert fc.eval_counts(coll) == (9, 8, 7)
    assert notify._evaluable_count(coll) == 7


# ---------------------------------------------------------------------------
# Anlass 3: Review-Wecker (überfällig, ~1x/Woche)
# ---------------------------------------------------------------------------
def test_review_push_on_monday_when_overdue(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=5)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2026-01-01")   # überfällig
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, MON)                             # Montag
    assert out["review"] is True and len(sent) == 1
    assert "Review" in sent[0]["title"]


def test_review_silent_midweek(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=5)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2026-01-01")
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)                             # Dienstag
    assert out["review"] is False and sent == []                  # Drossel greift


# ---------------------------------------------------------------------------
# STUMM-BEWEIS: Normal-Lauf erzeugt NULL Pushes
# ---------------------------------------------------------------------------
def test_normal_run_is_silent(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=12)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2027-12-31")   # Review in Zukunft
    sent = _capture(monkeypatch)
    out = notify.run_daily(TOPIC, TUE)     # kein Meilenstein, kein Review, Dienstag
    assert out == {"milestone": False, "review": False}
    # und der Staleness-Cron ist bei frischem Report ebenfalls stumm:
    assert notify.run_staleness(TOPIC, TUE) is False
    assert sent == []                       # NULL Pushes im Normalbetrieb


# ---------------------------------------------------------------------------
# Topic-Handhabung (kein Leak) + Fail-soft
# ---------------------------------------------------------------------------
def test_empty_topic_never_posts(tmp_path, monkeypatch):
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-01T00:00:00Z", matured=100)
    monkeypatch.setattr(notify, "SCORE_REVIEW_BY", "2026-01-01")
    sent = _capture(monkeypatch)
    # Trotz aller Anlässe: leeres Topic -> KEIN Netzaufruf.
    assert notify.send_ntfy("", "t", "b") is False
    notify.run_staleness("", MON)
    notify.run_daily("", MON)
    assert sent == []


def test_send_is_failsoft(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ntfy down")
    monkeypatch.setattr(notify, "_post", boom)
    # Fehler beim Senden -> False, kein Crash.
    assert notify.send_ntfy(TOPIC, "t", "b") is False


# ---------------------------------------------------------------------------
# Score-Alert-Push (>Schwelle): Bündelung, Ehrlichkeit, kein Leak, Fail-soft
# ---------------------------------------------------------------------------
# Seit 31.07.2026 tragen die Edges Setup-Typ und die KONKRETE Schwelle —
# die Schwelle ist typ-relativ, eine nackte Zahl waere ohne Bezug irrefuehrend.
_EDGES = [{"ticker": "XYZ", "market": "US", "score": 93.2,
           "setup": "end_of_w4", "threshold": 88.2},
          {"ticker": "ABC", "market": "DE", "score": 91.0,
           "setup": "end_of_w2", "threshold": 78.4}]


def test_score_alert_body_bundles_and_is_honest():
    body = notify.score_alert_body(_EDGES)
    assert "XYZ" in body and "ABC" in body           # beide Ticker im EINEN Text
    assert "93.2" in body and "91.0" in body         # Scores mit EINER Dezimale
    assert "heuristisch · unvalidiert" in body       # Ehrlichkeit: kein Signal
    assert "🇺🇸" in body and "🇩🇪" in body            # Markt im Text


def test_score_alert_body_nennt_setup_typ_und_schwelle():
    """Ohne Bezug ist die Zahl irrefuehrend: 89 ist an der W4-Schwelle knapp,
    an der W2-Schwelle weit darueber.

    EXAKT geprueft, nicht per Teilstring (Guardian-Nit 31.07.): `"Schwelle
    88.2" in body` matcht auch `Schwelle 88.20` — eine Formatierungs-Aenderung
    waere unbemerkt durchgerutscht. Der ganze Baustein steht hier woertlich.

    Seit 01.08.2026 traegt der SCORE eine Dezimale (vorher ganzzahlig) — siehe
    test_score_alert_body_widerspricht_dem_alarm_nicht.
    """
    body = notify.score_alert_body(_EDGES)
    assert body == ("XYZ (🇺🇸) 93.2 · Ende W4 (Schwelle 88.2)"
                    " · ABC (🇩🇪) 91.0 · Ende W2 (Schwelle 78.4)"
                    " — heuristisch · unvalidiert (kein Signal)")


def test_score_alert_body_widerspricht_dem_alarm_nicht():
    """Der Grund fuer die Dezimale (Befund 31.07.2026).

    Ganzzahlig gerundet ergaben sich Texte, die dem Alarm WIDERSPRACHEN: ein
    Score von 88,34 liegt UEBER der W4-Schwelle 88,20 — der Alarm feuert zu
    Recht. Als `88` neben `Schwelle 88.2` gelesen, sah der Push aus, als laege
    der Wert DARUNTER. Von Hand nachgerechnet: 88,34 -> "88.3", und 88.3 > 88.2
    ist auch im Text wahr.

    Der Fall ist real erreichbar: 88,20 <= score < 88,50 ist genau das Fenster
    direkt ueber der Schwelle, also der HAEUFIGSTE Alarm-Fall, nicht der
    seltenste. Am 31.07. blieb er folgenlos, weil QIA.DE bei 88,69 lag.
    """
    body = notify.score_alert_body(
        [{"ticker": "QIA.DE", "market": "DE", "score": 88.34,
          "setup": "end_of_w4", "threshold": 88.2}])
    assert body == ("QIA.DE (🇩🇪) 88.3 · Ende W4 (Schwelle 88.2)"
                    " — heuristisch · unvalidiert (kein Signal)")
    # Und die Kern-Eigenschaft explizit: die gezeigte Zahl liegt ueber der
    # gezeigten Schwelle. Mit `.0f` waere hier "88" gestanden -> 88 < 88.2.
    gezeigt = float(body.split(") ")[1].split(" ·")[0])
    schwelle = float(body.split("Schwelle ")[1].split(")")[0])
    assert gezeigt >= schwelle, f"Text zeigt {gezeigt} unter Schwelle {schwelle}"


@pytest.mark.parametrize("score, erwartet", [
    (88.20, "88.2"), (88.25, "88.2"), (88.34, "88.3"), (88.49, "88.5"),
    (88.69, "88.7"), (93.0, "93.0"),
])
def test_score_dezimale_von_hand_nachgerechnet(score, erwartet):
    """Sollwerte ausgeschrieben, nicht aus dem Formatstring abgeleitet.

    88,25 -> "88.2" ist Pythons Bankers Rounding (haelftig auf die gerade
    Ziffer) und KEIN Tippfehler; 88,49 -> "88.5" rundet auf. Beides ist fuer
    den Alarm unschaedlich, weil die Schwelle selbst nur eine Dezimale hat und
    der Vergleich im Code auf den ROHWERTEN laeuft, nicht auf dem Text.
    """
    body = notify.score_alert_body(
        [{"ticker": "T", "market": "US", "score": score,
          "setup": "end_of_w4", "threshold": 88.2}])
    assert f"T (🇺🇸) {erwartet} · Ende W4" in body


def test_score_alert_body_vertraegt_unbekannten_typ():
    """Rueckfall-Fall (Label nicht lesbar): Text bleibt lesbar, kein Crash."""
    body = notify.score_alert_body(
        [{"ticker": "Q", "market": "US", "score": 89.0,
          "setup": None, "threshold": 88.2}])
    assert "Q" in body and "Typ offen" in body and "Schwelle 88.2" in body


def test_score_alert_single_push_for_multiple_tickers(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    assert notify.send_score_alert(TOPIC, _EDGES) is True
    assert len(sent) == 1                             # EIN Push, egal wie viele Ticker
    assert "XYZ" in sent[0]["body"] and "ABC" in sent[0]["body"]
    assert "Typ-Schwelle" in sent[0]["title"]


def test_score_alert_empty_edges_is_silent(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    assert notify.send_score_alert(TOPIC, []) is False
    assert sent == []                                 # keine Flanke -> kein Push


def test_score_alert_empty_topic_never_posts(tmp_path, monkeypatch):
    sent = _capture(monkeypatch)
    assert notify.send_score_alert("", _EDGES) is False
    assert sent == []                                 # leeres Topic -> kein Netzaufruf


def test_score_alert_is_failsoft(monkeypatch):
    monkeypatch.setattr(notify, "_post",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    # Push-Fehler -> False, kein Crash (Lauf darf nie brechen).
    assert notify.send_score_alert(TOPIC, _EDGES) is False


def test_main_always_returns_zero(tmp_path, monkeypatch):
    # Selbstüberwachung darf den Workflow NIE rot färben.
    _fixture_repo(tmp_path, monkeypatch, report_ts="2026-07-27T18:00:00Z", matured=5)
    monkeypatch.setattr(notify, "_post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    assert notify.main(["--mode", "daily"]) == 0
    assert notify.main(["--mode", "staleness"]) == 0
