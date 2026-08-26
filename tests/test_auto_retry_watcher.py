"""Selbstwartung Stufe 3 — automatischer Retry bei Tageslauf-Fehlschlag.

ERSTE PRODUKTIVE SELBST-HANDLUNG im Repo (siehe scripts/auto_retry_watcher.py
Docstring). Besonders hohe Testschärfe, weil die Tagesgrenze (3) laut Auftrag
die EINZIGE Verteidigung gegen eine Endlosschleife ist — deshalb ein
dedizierter, benannter Grenzfall-Test für ``>=`` vs. ``>``
(``test_entscheidung_genau_drei_liefert_erschoepft_nicht_retry``), analog zur
Lehre aus dem historischen Score-Schwellen-Bug (eine Schwelle GENAU am
Maximum hat früher nie ausgelöst).

Kein Netz: ``dispatch_retry``/``notify.send_ntfy`` bekommen gefälschte
HTTP-Schichten (Muster wie ``notify._post`` in test_notify.py).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

import auto_retry_watcher as w
import notify

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/daily_retry_watcher.yml").read_text(encoding="utf-8")
DAILY_YML = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
EVALUATE_QUELLE = (ROOT / "scripts/evaluate.py").read_text(encoding="utf-8")


HEUTE = "2026-08-27"
GESTERN = "2026-08-26"
NOW = _dt.datetime(2026, 8, 27, 23, 5, 0, tzinfo=_dt.timezone.utc)
NOW_KURZ_NACH_MITTERNACHT = _dt.datetime(2026, 8, 27, 0, 3, 0,
                                          tzinfo=_dt.timezone.utc)


def _capture_ntfy(monkeypatch):
    sent = []
    monkeypatch.setattr(
        notify, "_post",
        lambda url, data, headers, timeout: sent.append(
            {"title": headers.get("Title"), "prio": headers.get("Priority"),
             "body": data.decode("utf-8")}))
    return sent


def _fake_post_immer_erfolgreich(url, headers, payload, timeout):
    return 204


# ---------------------------------------------------------------------------
# PURE Entscheidungslogik — der sicherheitskritische Kern
# ---------------------------------------------------------------------------
def test_max_retries_pro_tag_ist_hart_drei():
    """Kanarien-Test: bricht laut, sobald die harte Grenze im Code verändert
    wird — genau das, was GRENZEN verlangt ('darf nicht unauffällig
    verändert werden können')."""
    assert w.MAX_RETRIES_PRO_TAG == 3


@pytest.mark.parametrize("anzahl", [0, 1, 2])
def test_entscheidung_unter_drei_liefert_retry(anzahl):
    assert w.entscheidung(anzahl) == "retry"


def test_entscheidung_genau_drei_liefert_erschoepft_nicht_retry():
    """DER Grenzfall-Test (Leitplanke 1): >= 3, nicht > 3. Eine Mutation von
    `>=` zu `>` in entscheidung() muss GENAU hier auffliegen — bei 3 selbst,
    nicht erst bei 4."""
    assert w.entscheidung(3) == "erschoepft"


@pytest.mark.parametrize("anzahl", [4, 5, 100])
def test_entscheidung_ueber_drei_liefert_ebenfalls_erschoepft(anzahl):
    assert w.entscheidung(anzahl) == "erschoepft"


def test_anzahl_heute_zaehlt_nur_heutige_eintraege():
    state = {"retries": [
        {"date": GESTERN, "retry_number": 1},
        {"date": GESTERN, "retry_number": 2},
        {"date": GESTERN, "retry_number": 3},
        {"date": HEUTE, "retry_number": 1},
    ]}
    assert w.anzahl_heute(state, HEUTE) == 1
    assert w.anzahl_heute(state, GESTERN) == 3


def test_anzahl_heute_leerer_state_ist_null():
    assert w.anzahl_heute({}, HEUTE) == 0
    assert w.anzahl_heute({"retries": []}, HEUTE) == 0


def test_mitternachts_reset_gestern_voll_heute_null():
    """Grenzfall aus Auftrag Punkt 5: letzter Retry kurz vor Mitternacht,
    naechster Fehlschlag kurz nach Mitternacht -> Zaehler wieder bei 0. Kein
    separater Reset-Code noetig, der Filter auf `date == heute` IST der
    Reset."""
    state = {"retries": [
        {"date": GESTERN, "retry_number": 1, "utc_time": f"{GESTERN}T23:50:00Z"},
        {"date": GESTERN, "retry_number": 2, "utc_time": f"{GESTERN}T23:55:00Z"},
        {"date": GESTERN, "retry_number": 3, "utc_time": f"{GESTERN}T23:59:00Z"},
    ]}
    heute_neu = NOW_KURZ_NACH_MITTERNACHT.date().isoformat()
    assert heute_neu == HEUTE
    n = w.anzahl_heute(state, heute_neu)
    assert n == 0
    assert w.entscheidung(n) == "retry"


# ---------------------------------------------------------------------------
# dispatch_retry: Rate-Limit-Regel + Netzfehler-Backoff
# ---------------------------------------------------------------------------
def test_dispatch_erfolgreich_ruft_post_genau_einmal():
    aufrufe = []

    def post(url, headers, payload, timeout):
        aufrufe.append((url, headers, payload))
        return 204

    ergebnis = w.dispatch_retry("o", "r", "tok", post=post, schlaf=lambda s: None)
    assert ergebnis["ok"] is True
    assert len(aufrufe) == 1
    assert aufrufe[0][2] == {"ref": "main"}
    assert aufrufe[0][1]["Authorization"] == "Bearer tok"


def test_rate_limit_fuehrt_zu_sofortiger_meldung_ohne_retry_des_dispatch_calls():
    aufrufe = []

    def post(url, headers, payload, timeout):
        aufrufe.append(1)
        raise w.RateLimitFehler("HTTP 403: rate limit exceeded")

    geschlafen = []
    ergebnis = w.dispatch_retry("o", "r", "tok", post=post,
                                 schlaf=lambda s: geschlafen.append(s))
    assert ergebnis["ok"] is False
    assert ergebnis["art"] == "rate_limit"
    assert len(aufrufe) == 1, "Rate-Limit darf NIE automatisch wiederholt werden"
    assert geschlafen == []


def test_netzwerkfehler_wird_mit_kurzem_backoff_wiederholt():
    aufrufe = []

    def post(url, headers, payload, timeout):
        aufrufe.append(1)
        if len(aufrufe) < 3:
            raise w.NetzwerkFehler("Verbindungsabbruch")
        return 204

    geschlafen = []
    ergebnis = w.dispatch_retry("o", "r", "tok", post=post,
                                 schlaf=lambda s: geschlafen.append(s))
    assert ergebnis["ok"] is True
    assert len(aufrufe) == 3
    assert len(geschlafen) == 2, "zwischen den Versuchen wird kurz gewartet"


def test_netzwerkfehler_erschoepft_nach_versuchen_wird_gemeldet():
    def post(url, headers, payload, timeout):
        raise w.NetzwerkFehler("dauerhaft weg")

    ergebnis = w.dispatch_retry("o", "r", "tok", post=post,
                                 schlaf=lambda s: None, versuche=3)
    assert ergebnis["ok"] is False
    assert ergebnis["art"] == "netzwerk"


# ---------------------------------------------------------------------------
# _klassifiziere_http_fehler: die eigentliche Rate-Limit-Erkennung, ohne Netz
# (Guardian-Fund 27.08.2026: vorher nur indirekt ueber injizierte Fake-
# Exceptions getestet, nie ueber echte Status-/Header-Kombinationen).
# ---------------------------------------------------------------------------
def test_primaeres_rate_limit_403_mit_remaining_null():
    exc = w._klassifiziere_http_fehler(403, "Forbidden", rate_limit_remaining="0")
    assert isinstance(exc, w.RateLimitFehler)


def test_429_ist_immer_rate_limit():
    exc = w._klassifiziere_http_fehler(429, "Too Many Requests")
    assert isinstance(exc, w.RateLimitFehler)


def test_sekundaeres_rate_limit_403_mit_retry_after():
    exc = w._klassifiziere_http_fehler(403, "Forbidden", retry_after="60")
    assert isinstance(exc, w.RateLimitFehler)


def test_403_ohne_rate_limit_indiz_ist_kein_rate_limit():
    """Eine normale Berechtigungs-Ablehnung (kein Rate-Limit-Header) darf
    NICHT als Rate-Limit klassifiziert werden — sonst würde die Rate-Limit-
    Regel (kein Retry, sofort melden) einen Fall verdecken, bei dem das
    eigentliche Problem eine fehlende Berechtigung ist."""
    exc = w._klassifiziere_http_fehler(403, "Forbidden")
    assert not isinstance(exc, w.RateLimitFehler)
    assert isinstance(exc, RuntimeError)


def test_403_mit_remaining_ueber_null_ist_kein_rate_limit():
    exc = w._klassifiziere_http_fehler(403, "Forbidden", rate_limit_remaining="5")
    assert not isinstance(exc, w.RateLimitFehler)


def test_404_und_422_sind_kein_rate_limit():
    for status in (404, 422, 500):
        exc = w._klassifiziere_http_fehler(status, "x")
        assert not isinstance(exc, w.RateLimitFehler)
        assert isinstance(exc, RuntimeError)


def test_unbekannter_fehler_wird_nicht_blind_wiederholt():
    aufrufe = []

    def post(url, headers, payload, timeout):
        aufrufe.append(1)
        raise RuntimeError("HTTP 422: Unexpected inputs")

    ergebnis = w.dispatch_retry("o", "r", "tok", post=post, schlaf=lambda s: None)
    assert ergebnis["ok"] is False
    assert ergebnis["art"] == "sonstig"
    assert len(aufrufe) == 1


# ---------------------------------------------------------------------------
# run(): Orchestrierung — strukturelle Tests
# ---------------------------------------------------------------------------
def test_watcher_reagiert_nicht_auf_conclusion_success(tmp_path, monkeypatch):
    sent = _capture_ntfy(monkeypatch)

    def post_darf_nie_aufgerufen_werden(*a, **k):
        raise AssertionError("Dispatch darf bei conclusion=success nie aufgerufen werden")

    ergebnis = w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "success",
                      base=tmp_path, post=post_darf_nie_aufgerufen_werden)
    assert ergebnis["aktion"] == "ignoriert"
    assert sent == []
    assert not (tmp_path / w.STATE_PATH).exists()


@pytest.mark.parametrize("conclusion", ["cancelled", "skipped", "neutral", "timed_out"])
def test_watcher_reagiert_nicht_auf_andere_conclusions_als_failure(tmp_path,
                                                                    monkeypatch,
                                                                    conclusion):
    sent = _capture_ntfy(monkeypatch)
    ergebnis = w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", conclusion,
                      base=tmp_path,
                      post=lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert ergebnis["aktion"] == "ignoriert"
    assert sent == []


def test_erster_fehlschlag_des_tages_loest_retry_eins_aus(tmp_path, monkeypatch):
    sent = _capture_ntfy(monkeypatch)
    ergebnis = w.run(NOW, "o", "r", "tok", "topic", 42, "https://x/runs/42",
                      "failure", base=tmp_path,
                      post=_fake_post_immer_erfolgreich)
    assert ergebnis["aktion"] == "retry_ausgeloest"
    assert ergebnis["retry_number"] == 1
    state = json.loads((tmp_path / w.STATE_PATH).read_text(encoding="utf-8"))
    assert len(state["retries"]) == 1
    assert state["retries"][0]["date"] == HEUTE
    assert state["retries"][0]["retry_number"] == 1
    assert state["retries"][0]["source_run_id"] == 42


def test_zweiter_und_dritter_fehlschlag_erhoehen_den_zaehler_sequentiell(tmp_path,
                                                                          monkeypatch):
    _capture_ntfy(monkeypatch)
    for erwartete_nummer in (1, 2, 3):
        ergebnis = w.run(NOW, "o", "r", "tok", "topic", 1, "https://x",
                          "failure", base=tmp_path,
                          post=_fake_post_immer_erfolgreich)
        assert ergebnis["aktion"] == "retry_ausgeloest"
        assert ergebnis["retry_number"] == erwartete_nummer


def test_vierter_fehlschlag_am_selben_tag_ist_erschoepft_kein_dispatch(tmp_path,
                                                                        monkeypatch):
    """Struktureller Test (Auftrag): die finale Meldung kommt NUR bei 3, nicht
    frueher — nach drei erfolgreichen Retries darf der vierte Versuch KEINEN
    Dispatch mehr ausloesen."""
    sent = _capture_ntfy(monkeypatch)
    for _ in range(3):
        w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "failure",
              base=tmp_path, post=_fake_post_immer_erfolgreich)
    sent.clear()

    ergebnis = w.run(NOW, "o", "r", "tok", "topic", 1, "https://x/vierter",
                      "failure", base=tmp_path,
                      post=lambda *a, **k: (_ for _ in ()).throw(
                          AssertionError("kein Dispatch mehr nach 3 Retries")))
    assert ergebnis["aktion"] == "erschoepft"
    assert ergebnis["anzahl_heute"] == 3
    state = json.loads((tmp_path / w.STATE_PATH).read_text(encoding="utf-8"))
    assert len(state["retries"]) == 3, "der vierte Versuch darf NICHT geloggt werden"
    assert len(sent) == 1
    assert "erschöpft" in sent[0]["body"]


def test_erschoepft_meldung_kommt_nicht_frueher_als_bei_drei(tmp_path, monkeypatch):
    sent = _capture_ntfy(monkeypatch)
    for i in range(2):
        w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "failure",
              base=tmp_path, post=_fake_post_immer_erfolgreich)
    assert all("erschöpft" not in s["body"] for s in sent), \
        "vor dem dritten Retry darf 'erschoepft' nicht auftauchen"


def test_exakter_wortlaut_retry_ausgeloest_push(tmp_path, monkeypatch):
    sent = _capture_ntfy(monkeypatch)
    w.run(NOW, "o", "r", "tok", "topic", 1, "https://x/lauf-42", "failure",
          base=tmp_path, post=_fake_post_immer_erfolgreich)
    text = sent[0]["body"]
    assert "Automatischer Retry Nr. 1 von 3" in text
    assert "https://x/lauf-42" in text


def test_exakter_wortlaut_erschoepft_push(tmp_path, monkeypatch):
    sent = _capture_ntfy(monkeypatch)
    for _ in range(4):  # 3 Retries verbrauchen die Slots, der 4. ist erschoepft
        w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "failure",
              base=tmp_path, post=_fake_post_immer_erfolgreich)
    text = sent[-1]["body"]
    assert "3 automatische Retries erschöpft" in text
    assert "kein weiterer Versuch heute" in text
    assert "manuelle Prüfung nötig" in text


def test_write_state_fehlschlag_wird_laut_gemeldet_nicht_verschluckt(tmp_path,
                                                                      monkeypatch):
    """Guardian-Fund 27.08.2026: ein Dispatch, dessen Zaehler-Eintrag lokal
    NICHT geschrieben werden konnte, muss einen eigenen, sichtbaren Push
    ausloesen — sonst waere die Tagesgrenze beim naechsten Lauf unbemerkt zu
    hoch (der State auf Platte kennt den Slot nicht)."""
    sent = _capture_ntfy(monkeypatch)
    monkeypatch.setattr(w, "write_state", lambda *a, **k: False)
    ergebnis = w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "failure",
                      base=tmp_path, post=_fake_post_immer_erfolgreich)
    assert ergebnis["aktion"] == "retry_ausgeloest_state_fehler"
    # ZWEI Pushes: der normale Retry-Push UND der State-Fehler-Alarm.
    assert len(sent) == 2
    assert any("State-Fehler" in s["title"] or "NICHT geschrieben" in s["body"]
               for s in sent)


def test_rate_limit_beim_dispatch_verbraucht_keinen_retry_slot(tmp_path, monkeypatch):
    sent = _capture_ntfy(monkeypatch)

    def post_rate_limit(url, headers, payload, timeout):
        raise w.RateLimitFehler("HTTP 429")

    ergebnis = w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "failure",
                      base=tmp_path, post=post_rate_limit)
    assert ergebnis["aktion"] == "dispatch_fehlgeschlagen"
    assert ergebnis["art"] == "rate_limit"
    assert not (tmp_path / w.STATE_PATH).exists(), \
        "ein nie ausgeloester Retry darf keinen Slot verbrauchen"
    assert "Rate-Limit" in sent[0]["body"]


# ---------------------------------------------------------------------------
# Marker-Trennung: eigener Ort, keine Vermischung mit den drei bestehenden
# ---------------------------------------------------------------------------
def test_retry_marker_lebt_in_eigener_datei_nicht_in_forward_collection(tmp_path,
                                                                         monkeypatch):
    _capture_ntfy(monkeypatch)
    w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "failure",
          base=tmp_path, post=_fake_post_immer_erfolgreich)
    assert w.STATE_PATH == "data/auto_retry_state.json"
    assert w.STATE_PATH != "data/forward_collection.json"
    state = json.loads((tmp_path / w.STATE_PATH).read_text(encoding="utf-8"))
    for verbotenes_feld in ("episode_split_suspect", "stale_market_suspect",
                            "in_session_creation"):
        assert verbotenes_feld not in json.dumps(state), \
            "Retry-Marker darf sich nicht mit bestehenden Markern vermischen"


def test_state_hat_schema_version_wie_die_anderen_state_dateien(tmp_path,
                                                                  monkeypatch):
    _capture_ntfy(monkeypatch)
    w.run(NOW, "o", "r", "tok", "topic", 1, "https://x", "failure",
          base=tmp_path, post=_fake_post_immer_erfolgreich)
    state = json.loads((tmp_path / w.STATE_PATH).read_text(encoding="utf-8"))
    assert state["schema_version"] == 1


# ---------------------------------------------------------------------------
# Struktureller Beleg: der Watcher ist ein EIGENES Modul, unabhaengig vom
# unter Handlungsverbot stehenden Wartungs-Waechter.
# ---------------------------------------------------------------------------
def test_auto_retry_watcher_ist_nicht_teil_von_maintenance_check():
    import inspect
    quelle_watcher = inspect.getsource(w)
    from pathlib import Path
    quelle_maintenance = (Path(__file__).resolve().parent.parent
                          / "scripts/maintenance_check.py").read_text(encoding="utf-8")
    assert "auto_retry_watcher" not in quelle_maintenance
    assert "MAX_RETRIES_PRO_TAG" not in quelle_maintenance
    # Und umgekehrt: das Handlungsverbot-Testmuster bleibt korrekt auf
    # maintenance_check.py beschraenkt (Gegenprobe, kein Duplikat des Tests
    # selbst — der lebt in tests/test_wartungs_cron.py).
    assert "workflow_dispatch" in quelle_watcher, \
        "dieser Watcher DARF workflow_dispatch nutzen (explizites GO, Stufe 3)"


# ---------------------------------------------------------------------------
# Struktureller Beleg: der Workflow selbst haelt die GRENZEN ein.
# ---------------------------------------------------------------------------
def test_workflow_reagiert_ausschliesslich_auf_daily_elliott_report():
    assert 'workflows: ["Daily Elliott Report"]' in WORKFLOW
    # Kein zweiter Workflow-Name im Filter (Wartungs-Cron, Staleness-Waechter
    # duerfen diesen Mechanismus nicht beruehren, GRENZEN).
    assert "Wartung" not in WORKFLOW
    assert "Staleness" not in WORKFLOW


def test_workflow_prueft_ausschliesslich_conclusion_failure():
    # Die `if:`-Bedingung des Jobs ist die einzige Stelle, die ueber
    # Ausloesen/Nicht-Ausloesen entscheidet — sie darf sich NICHT auf
    # health_check-Warnungen stuetzen (nur der Kommentar-Kopf DARF den Begriff
    # zur Abgrenzung erwaehnen, deshalb hier gezielt nur die `if:`-Zeile).
    if_zeile = next(z for z in WORKFLOW.splitlines() if z.strip().startswith("if:"))
    assert "github.event.workflow_run.conclusion == 'failure'" in if_zeile
    assert "health_check" not in if_zeile


def test_workflow_hat_die_bestaetigte_permissions_erweiterung():
    assert "actions: write" in WORKFLOW
    assert "contents: write" in WORKFLOW


def test_workflow_hat_eigene_concurrency_gruppe():
    assert "group: daily-retry-watcher" in WORKFLOW


def test_daily_yml_und_evaluate_py_unveraendert_von_diesem_mechanismus():
    """GRENZEN: keine Aenderung an daily.yml (Cron/Feiertags-Gate/Pipeline)
    oder evaluate.py. Gegenprobe: keiner der neuen Bausteine taucht dort auf
    — der Watcher ist vollstaendig aussenstehend."""
    for verboten in ("auto_retry_watcher", "daily_retry_watcher",
                     "MAX_RETRIES_PRO_TAG", "auto_retry_state"):
        assert verboten not in DAILY_YML
        assert verboten not in EVALUATE_QUELLE


def test_workflow_meldet_state_persistenz_fehlschlag_laut():
    """Guardian-Fund 27.08.2026: ein Git-Push-Fehlschlag des Zaehler-Commits
    (separat vom Python-Dispatch-Schritt) muss ebenfalls per Push sichtbar
    sein, nicht nur im Actions-Log."""
    assert "id: commit" in WORKFLOW
    assert "Push bei State-Persistenz-Fehlschlag" in WORKFLOW
    assert "if: failure() && steps.commit.outcome == 'failure'" in WORKFLOW


def test_daily_yml_deklariert_keinen_retry_input_dispatch_bleibt_ohne_inputs():
    """Dokumentiert die bewusste Abweichung von der Auftrags-Beispielidee
    ('triggered_by=auto-retry' als Input): daily.yml deklariert bislang nur
    `push_selftest` — ein Dispatch mit einem zusaetzlichen, dort nicht
    deklarierten Input wuerde von der GitHub-API abgelehnt. Deshalb dispatcht
    dispatch_retry() bewusst OHNE zusaetzliche Inputs (nur `ref`)."""
    assert "push_selftest" in DAILY_YML
    assert "triggered_by" not in DAILY_YML
    assert "retry_number" not in DAILY_YML
