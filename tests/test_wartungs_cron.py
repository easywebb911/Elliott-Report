"""Selbstwartung Stufe 2 — Wartungs-Cron und die achte Health-Regel.

WAS HIER FESTGENAGELT WIRD, in einem Satz: ein Wächter, der bei fehlendem Anker
schweigt, ist schlimmer als keiner — er sieht aus wie ein grüner Haken. Deshalb
prüft fast jeder Test hier ZWEI Dinge: dass der Befund kommt, wenn er soll, und
dass er AUSBLEIBT, wenn er nicht soll. Ein Wächter ohne Gegenprobe ist nur ein
Alarm, der immer geht.

Alle Soll-Werte sind von Hand nachgerechnet und im jeweiligen Test benannt.
Kein Test hängt an der Systemuhr: die Termin-Prüfungen bekommen eingefrorene
Stichtage, die Health-Regel rechnet gegen den Lauf-Zeitstempel des Reports.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import health_check as hc  # noqa: E402
import maintenance_check as mc  # noqa: E402
import market_calendar as cal  # noqa: E402
import notify  # noqa: E402

import conftest  # noqa: E402 — geteilte Sandbox-Helfer

NOW_ISO = "2026-07-27T21:45:00Z"


def _report(ts: str = NOW_ISO) -> dict:
    return {"schema_version": 1, "run_timestamp_utc": ts, "markets": {}}


def _sandbox(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(hc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mc, "REPO_ROOT", tmp_path)
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════
# BAUSTEIN 2 — die achte Health-Regel `maintenance_stale`
# ═══════════════════════════════════════════════════════════════════════════
# Von Hand nachgerechnet, Bezugspunkt ist IMMER der Lauf-Zeitstempel des
# Reports (2026-07-27T21:45:00Z), nicht die Systemuhr:
#
#   Lauf 2026-07-27 21:45Z  −  State 2026-07-26 21:45Z  =  1,0 Tage  -> still
#   Lauf 2026-07-27 21:45Z  −  State 2026-07-17 21:45Z  = 10,0 Tage  -> still
#                                                          (Grenze gehört zur
#                                                           gesunden Seite)
#   Lauf 2026-07-27 21:45Z  −  State 2026-07-17 21:44Z  = 10,0007 Tage -> warn
#   Lauf 2026-07-27 21:45Z  −  State 2026-07-13 21:45Z  = 14,0 Tage  -> warn
@pytest.mark.parametrize("state_ts, soll_befund, warum", [
    ("2026-07-26T21:45:00Z", False, "1 Tag alt — frisch"),
    ("2026-07-20T21:45:00Z", False, "7 Tage = ein ausgefallener Wochenlauf"),
    ("2026-07-17T21:45:00Z", False, "exakt 10,0 Tage — Grenze ist gesund"),
    ("2026-07-17T21:44:00Z", True, "10,0007 Tage — eine Minute drueber"),
    ("2026-07-13T21:45:00Z", True, "14 Tage = zwei ausgefallene Wochenlaeufe"),
])
def test_maintenance_stale_verdikt_je_alter(tmp_path, monkeypatch, state_ts,
                                            soll_befund, warum):
    _sandbox(tmp_path, monkeypatch)
    conftest.schreibe_wartungs_state(tmp_path, state_ts)
    befunde = hc.check_maintenance(_report())
    assert bool(befunde) is soll_befund, f"{warum}: {befunde}"
    if soll_befund:
        assert befunde[0]["rule"] == "maintenance_stale"
        assert befunde[0]["severity"] == hc.WARN
        assert befunde[0]["detail"]["max_age_days"] == 10


def test_die_sieben_tage_luecke_ist_der_grund_fuer_die_zehn(tmp_path,
                                                            monkeypatch):
    """Warum 10 und nicht 7: EIN ausgefallener Wochenlauf ist kein Befund.

    Der Cron laeuft woechentlich. Bei einer Grenze von 7 Tagen wuerde jede
    GitHub-Stoerung, jeder verschobene Cron-Start und jeder Feiertagsmontag
    einen Fehlalarm ausloesen. Bei 14 waere ein doppelter Ausfall gerade noch
    still. 10 liegt dazwischen — das ist die ganze Herleitung, und dieser Test
    haelt beide Seiten fest.
    """
    _sandbox(tmp_path, monkeypatch)
    conftest.schreibe_wartungs_state(tmp_path, "2026-07-20T21:45:00Z")   # 7 T.
    assert hc.check_maintenance(_report()) == []
    conftest.schreibe_wartungs_state(tmp_path, "2026-07-13T21:45:00Z")   # 14 T.
    assert len(hc.check_maintenance(_report())) == 1


def test_fehlender_state_ist_ein_befund(tmp_path, monkeypatch):
    """Keine Datei = niemand weiss, ob der Cron je lief. Das IST der Befund."""
    _sandbox(tmp_path, monkeypatch)
    befunde = hc.check_maintenance(_report())
    assert len(befunde) == 1
    assert befunde[0]["rule"] == "maintenance_stale"
    assert befunde[0]["detail"]["grund"] == "kein last_run_utc"


def test_state_ohne_last_run_utc_ist_ein_befund(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    (tmp_path / "data" / "maintenance_state.json").write_text(
        json.dumps({"schema_version": 1, "rules": {}}), encoding="utf-8")
    befunde = hc.check_maintenance(_report())
    assert len(befunde) == 1 and befunde[0]["detail"]["grund"] == "kein last_run_utc"


def test_unlesbarer_stempel_ist_ein_befund_nicht_stille(tmp_path, monkeypatch):
    """Ein kaputter Stempel darf nicht wie „alles frisch" aussehen."""
    _sandbox(tmp_path, monkeypatch)
    conftest.schreibe_wartungs_state(tmp_path, "gestern-so-gegen-halb")
    befunde = hc.check_maintenance(_report())
    assert len(befunde) == 1
    assert befunde[0]["detail"]["grund"] == "unlesbar"


def test_ohne_lauf_zeitstempel_meldet_die_regel_NICHTS(tmp_path, monkeypatch):
    """Fail-soft in EINE Richtung: ohne Bezugspunkt kein Urteil.

    Sonst faerbte jeder alte Report-Stand und jede Testfixture ohne Zeitstempel
    grundlos rot — dieselbe Entscheidung wie bei `check_bar_freshness`.
    """
    _sandbox(tmp_path, monkeypatch)
    assert hc.check_maintenance({"run_timestamp_utc": None}) == []
    assert hc.check_maintenance({"run_timestamp_utc": "kaputt"}) == []


def test_die_regel_haengt_wirklich_im_lauf(tmp_path, monkeypatch):
    """`collect_findings` ruft sie auf — sonst waere sie totes Kapital."""
    _sandbox(tmp_path, monkeypatch)          # kein State -> Befund erwartet
    findings = hc.collect_findings(_report(), None, [], None, None,
                                   has_agent_key=False)
    assert any(f["rule"] == "maintenance_stale" for f in findings), \
        "die achte Regel laeuft im echten Durchlauf nicht mit"


def test_flanken_und_drossel_wie_bei_den_anderen_warn_regeln(tmp_path,
                                                             monkeypatch):
    """Kein Sonderweg: `maintenance_stale` geht durch dieselbe Drossel.

    Von Hand: neu -> Push. Unveraendert -> still, bis HEALTH_WARN_REPEAT_RUNS
    (3) Laeufe vergangen sind, dann wieder EIN Push.
    """
    _sandbox(tmp_path, monkeypatch)
    f = hc.check_maintenance(_report())
    assert len(f) == 1
    to_push, st = hc.evaluate_edges(f, {}, "2026-07-27")
    assert len(to_push) == 1, "der erste Befund muss pushen"
    for tag, soll in (("2026-07-28", 0), ("2026-07-29", 0), ("2026-07-30", 1)):
        to_push, st = hc.evaluate_edges(f, st, tag)
        assert len(to_push) == soll, f"{tag}: Drossel verhaelt sich anders"


def test_der_tageslauf_schreibt_den_wartungs_state_NICHT(tmp_path, monkeypatch):
    """Baustein-3-Grenze: nur der Wartungs-Cron pflegt seine Datei.

    Schriebe der Tageslauf sie mit, waere `last_run_utc` immer frisch und die
    Regel damit wirkungslos — der Waechter wuerde sich selbst bestaetigen.
    """
    _sandbox(tmp_path, monkeypatch)
    conftest.schreibe_wartungs_state(tmp_path, "2026-07-24T06:30:00Z")
    pfad = tmp_path / "data" / "maintenance_state.json"
    vorher = pfad.read_bytes()
    monkeypatch.setattr(notify, "_post",
                        lambda url, data, headers, timeout: None)
    hc.run(_report(), None, [], None, None, has_agent_key=False, topic="",
           run_date="2026-07-27", now_iso=NOW_ISO,
           now=_dt.datetime(2026, 7, 27, 21, 45, tzinfo=_dt.timezone.utc))
    assert pfad.read_bytes() == vorher, \
        "der Tageslauf hat den Wartungs-State angefasst"


def test_daily_yml_committet_den_wartungs_state_nicht(tmp_path, monkeypatch):
    """Dieselbe Grenze auf Workflow-Ebene, statisch geprueft."""
    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "maintenance_state.json" not in daily, \
        "daily.yml fasst den Wartungs-State an — er gehoert dem Wartungs-Cron"


# ═══════════════════════════════════════════════════════════════════════════
# BAUSTEIN 1a — Termin-Horizonte
# ═══════════════════════════════════════════════════════════════════════════
# Von Hand: FULL_CLOSURE endet heute mit 2027-12-25, also ist die Liste ab
# 2027-12-26 BLIND. Vorlauf 90 Tage -> Warnung ab 2027-09-27.
def test_blind_ab_wird_aus_der_liste_abgeleitet_nicht_geraten():
    blind = mc.blind_ab()
    letzter = max(_dt.date.fromisoformat(k) for k in cal.FULL_CLOSURE)
    assert blind == letzter + _dt.timedelta(days=1)
    # Der heutige Stand, ausgeschrieben — faellt er, ist die Liste verlaengert
    # worden und dieser Test erinnert daran, die Herleitung nachzulesen.
    assert letzter == _dt.date(2027, 12, 25)
    assert blind == _dt.date(2027, 12, 26)


@pytest.mark.parametrize("tag, soll_sev, warum", [
    ("2027-09-26", None, "91 Tage vorher — noch still"),
    ("2027-09-27", "warn", "genau 90 Tage vorher — erste Warnung"),
    ("2027-12-25", "warn", "letzter gedeckter Tag — immer noch warn"),
    ("2027-12-26", "crit", "ab hier ist die Liste BLIND"),
    ("2028-01-01", "crit", "Neujahr: erste konkret falsche Antwort"),
])
def test_feiertagsliste_an_eingefrorenen_stichtagen(tag, soll_sev, warum):
    befunde = mc.check_feiertagsliste(_dt.date.fromisoformat(tag))
    if soll_sev is None:
        assert befunde == [], warum
    else:
        assert len(befunde) == 1, warum
        assert befunde[0]["severity"] == soll_sev, warum
        assert befunde[0]["rule"] == "feiertagsliste"


def test_heute_meldet_die_feiertagsliste_NICHTS():
    """Gegenprobe gegen einen Wächter, der einfach immer meldet."""
    assert mc.check_feiertagsliste(_dt.date(2026, 8, 9)) == []


def test_leere_feiertagsliste_ist_ein_befund_kein_freifahrtschein(monkeypatch):
    """Waere die Liste leer, wuerde `blind_ab()` None liefern — und ein Wächter,
    der daraufhin schweigt, haette den gefaehrlichsten Fall stillgelegt."""
    monkeypatch.setattr(cal, "FULL_CLOSURE", {})
    befunde = mc.check_feiertagsliste(_dt.date(2026, 8, 9))
    assert len(befunde) == 1 and befunde[0]["rule"] == "feiertagsliste"


# Von Hand: PROBE_END_DATE = 2026-08-21. Am Tag selbst noch still (`heute <=
# ende`), ab dem 22.08. genau EIN Hinweis.
@pytest.mark.parametrize("tag, soll", [
    ("2026-08-20", False), ("2026-08-21", False), ("2026-08-22", True),
    ("2026-12-31", True),
])
def test_sonde_abgelaufen_an_eingefrorenen_stichtagen(tag, soll):
    befunde = mc.check_sonde_abgelaufen(_dt.date.fromisoformat(tag))
    assert bool(befunde) is soll
    if soll:
        assert befunde[0]["rule"] == "sonde_abgelaufen"
        assert "Löschweg" in befunde[0]["message"]


def test_der_sonden_hinweis_kommt_GENAU_EINMAL():
    """Einmaligkeit ueber den State, nicht ueber die Warn-Drossel.

    Ueber die Drossel kaeme derselbe Hinweis alle drei Wochen bis in alle
    Ewigkeit — bei einer Sache, die nicht brennt, ist das Rauschen.
    """
    spaet = _dt.date(2026, 9, 1)
    erst = mc.sammle_befunde(spaet, base=ROOT, bereits_gemeldet=())
    assert any(f["rule"] == "sonde_abgelaufen" for f in erst)
    danach = mc.sammle_befunde(spaet, base=ROOT,
                               bereits_gemeldet=("sonde_abgelaufen",))
    assert not any(f["rule"] == "sonde_abgelaufen" for f in danach), \
        "der einmalige Hinweis wiederholt sich"


def test_score_review_by_wird_NICHT_gedoppelt():
    """`notify` weckt den Review bereits — zwei Wecker fuer denselben Termin
    waeren zwei Pushes und eine zweite Definition desselben Datums."""
    quelle = (ROOT / "scripts/maintenance_check.py").read_text(encoding="utf-8")
    assert "SCORE_REVIEW_BY" not in quelle


# ═══════════════════════════════════════════════════════════════════════════
# BAUSTEIN 1b — Konstanten-Drift
# ═══════════════════════════════════════════════════════════════════════════
def test_konstanten_drift_heute_still():
    assert mc.check_konstanten_drift() == []


def test_drift_wird_erkannt():
    """Fixture mit absichtlich verstelltem Wert: config sagt 30, HTML sagt 42."""
    html = "const STALENESS_HOURS = 42;\nconst WL_MAX = 30;\n"
    befunde = mc.check_konstanten_drift(html=html)
    assert len(befunde) == 1
    f = befunde[0]
    assert f["rule"] == "konstanten_drift"
    assert f["detail"]["config"] == "STALENESS_HOURS"
    assert f["detail"]["config_wert"] == "30" and f["detail"]["frontend_wert"] == "42"


def test_beide_paare_driften_gleichzeitig():
    html = "const STALENESS_HOURS = 42;\nconst WL_MAX = 7;\n"
    befunde = mc.check_konstanten_drift(html=html)
    assert {f["detail"]["config"] for f in befunde} == {"STALENESS_HOURS",
                                                        "WATCHLIST_MAX"}


def test_fehlender_ANKER_ist_ein_befund_kein_bestanden():
    """Der wichtigste Test dieser Gruppe.

    Benennt jemand `WL_MAX` um, findet die Regex nichts. Ein Waechter, der
    daraufhin „keine Drift" meldet, hat sich selbst abgeschaltet — und niemand
    merkt es, weil die Meldung wie ein Erfolg aussieht.
    """
    html = "const STALENESS_HOURS = 30;\n"      # WL_MAX fehlt
    befunde = mc.check_konstanten_drift(html=html)
    assert len(befunde) == 1
    assert befunde[0]["detail"]["anker_fehlt"] is True
    assert "WIRKUNGSLOS" in befunde[0]["message"]


def test_der_anker_ist_der_NAME_nicht_die_zahl():
    """Eine 30 an anderer Stelle darf die Pruefung weder retten noch stoeren."""
    html = ("const IRGENDWAS = 30;\nconst STALENESS_HOURS = 42;\n"
            "const WL_MAX = 30;\n")
    befunde = mc.check_konstanten_drift(html=html)
    assert len(befunde) == 1 and befunde[0]["detail"]["frontend_wert"] == "42"


def test_frontend_konstante_liest_den_echten_wert():
    html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert mc.frontend_konstante(html, "STALENESS_HOURS") == "30"
    assert mc.frontend_konstante(html, "WL_MAX") == "30"
    assert mc.frontend_konstante(html, "GIBT_ES_NICHT") is None


# ═══════════════════════════════════════════════════════════════════════════
# BAUSTEIN 1b — Spiegel-Gleichheit
# ═══════════════════════════════════════════════════════════════════════════
def test_spiegel_im_echten_repo_ist_gleich():
    assert mc.check_spiegel() == []


def _spiegel_sandbox(tmp_path, links=b'{"a":1}', rechts=b'{"a":1}'):
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "report.json").write_bytes(links)
    (tmp_path / "docs" / "data" / "report.json").write_bytes(rechts)
    return (("data/report.json", "docs/data/report.json"),)


def test_spiegel_ungleichheit_wird_erkannt(tmp_path):
    paare = _spiegel_sandbox(tmp_path, b'{"a":1}', b'{"a":2}')
    befunde = mc.check_spiegel(paare=paare, base=tmp_path)
    assert len(befunde) == 1 and befunde[0]["rule"] == "spiegel_ungleich"


def test_spiegel_gleichheit_ist_BYTE_gleichheit(tmp_path):
    """Inhaltsgleich, aber anders formatiert = trotzdem Befund.

    Nicht Pedanterie: verschiedene Bytes beweisen, dass die beiden Dateien
    NICHT aus demselben Schreibvorgang stammen — und genau das ist die Frage.
    """
    paare = _spiegel_sandbox(tmp_path, b'{"a": 1}', b'{"a":1}')
    assert len(mc.check_spiegel(paare=paare, base=tmp_path)) == 1


def test_fehlende_spiegel_datei_wird_erkannt(tmp_path):
    paare = _spiegel_sandbox(tmp_path)
    (tmp_path / "docs" / "data" / "report.json").unlink()
    befunde = mc.check_spiegel(paare=paare, base=tmp_path)
    assert len(befunde) == 1
    assert befunde[0]["detail"]["fehlt"] == ["docs/data/report.json"]


# ═══════════════════════════════════════════════════════════════════════════
# BAUSTEIN 1b — Workflow-Struktur
# ═══════════════════════════════════════════════════════════════════════════
def test_workflow_struktur_im_echten_repo_sauber():
    assert mc.check_workflow_struktur() == []
    assert mc.check_secret_referenzen() == []


def test_alle_workflows_haben_einen_deckel():
    """Die Zusage aus #89, hier als laufende Pruefung statt als Momentaufnahme."""
    for pfad in mc.workflow_dateien():
        text = pfad.read_text(encoding="utf-8")
        jobs = mc._job_namen(text)
        assert jobs, f"{pfad.name}: kein Job erkannt"
        n = len(re.findall(r"^\s+timeout-minutes:\s*\d+\s*$", text, re.M))
        assert n >= len(jobs), f"{pfad.name}: {n} Deckel fuer {len(jobs)} Job(s)"


def _wf_sandbox(tmp_path, dateien: dict):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    for name, text in dateien.items():
        (d / name).write_text(text, encoding="utf-8")
    return tmp_path


WF_OK = ("name: X\n\nconcurrency:\n  group: gruppe-a\n"
         "  cancel-in-progress: false\n\njobs:\n  bau:\n"
         "    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"
         "      - name: Schritt\n        run: echo hi\n")


def test_fehlendes_timeout_wird_erkannt(tmp_path):
    _wf_sandbox(tmp_path, {"a.yml": WF_OK.replace(
        "    timeout-minutes: 5\n", "")})
    befunde = mc.check_workflow_struktur(tmp_path)
    assert len(befunde) == 1
    assert befunde[0]["detail"]["timeouts"] == 0


def test_doppelte_concurrency_gruppe_wird_erkannt(tmp_path):
    _wf_sandbox(tmp_path, {"a.yml": WF_OK, "b.yml": WF_OK})
    befunde = mc.check_workflow_struktur(tmp_path)
    assert len(befunde) == 1
    assert befunde[0]["detail"]["gruppe"] == "gruppe-a"
    assert befunde[0]["detail"]["dateien"] == ["a.yml", "b.yml"]


def test_verschiedene_gruppen_sind_still(tmp_path):
    _wf_sandbox(tmp_path, {"a.yml": WF_OK,
                           "b.yml": WF_OK.replace("gruppe-a", "gruppe-b")})
    assert mc.check_workflow_struktur(tmp_path) == []


def test_fehlende_concurrency_wird_erkannt(tmp_path):
    ohne = WF_OK.replace("concurrency:\n  group: gruppe-a\n"
                         "  cancel-in-progress: false\n\n", "")
    _wf_sandbox(tmp_path, {"a.yml": ohne})
    befunde = mc.check_workflow_struktur(tmp_path)
    assert len(befunde) == 1 and befunde[0]["detail"]["parser"] == "concurrency"


def test_ein_parser_der_nichts_findet_MELDET_das(tmp_path):
    """Der Kern der ganzen Datei: kein stilles Bestanden bei kaputtem Anker."""
    kaputt = WF_OK.replace("jobs:\n", "JOBS:\n")     # Hausstil verlassen
    _wf_sandbox(tmp_path, {"a.yml": kaputt})
    befunde = mc.check_workflow_struktur(tmp_path)
    assert any(f["detail"].get("parser") == "jobs" for f in befunde), \
        "der Parser greift nicht mehr und schweigt — genau das darf nicht sein"


def test_gar_keine_workflows_ist_ein_befund(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    befunde = mc.check_workflow_struktur(tmp_path)
    assert len(befunde) == 1 and "wirkungslos" in befunde[0]["message"]


def test_nicht_durchgereichtes_secret_wird_erkannt(tmp_path):
    """Der Defekt vom 27.07.2026: Step startet notify.py ohne NTFY_TOPIC."""
    wf = ("name: X\n\nconcurrency:\n  group: g\n\njobs:\n  bau:\n"
          "    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"
          "      - name: Push\n        run: python scripts/notify.py --mode daily\n")
    _wf_sandbox(tmp_path, {"a.yml": wf})
    befunde = mc.check_secret_referenzen(tmp_path, erwartet=set())
    assert any(f["rule"] == "secret_durchreichung" for f in befunde)


def test_durchgereichtes_secret_ist_still(tmp_path):
    wf = ("name: X\n\nconcurrency:\n  group: g\n\njobs:\n  bau:\n"
          "    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    steps:\n"
          "      - name: Push\n        env:\n"
          "          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}\n"
          "        run: python scripts/notify.py --mode daily\n")
    _wf_sandbox(tmp_path, {"a.yml": wf})
    assert mc.check_secret_referenzen(tmp_path,
                                      erwartet={"NTFY_TOPIC"}) == []


def test_verschwundene_secret_referenz_wird_erkannt(tmp_path):
    _wf_sandbox(tmp_path, {"a.yml": WF_OK})
    befunde = mc.check_secret_referenzen(tmp_path, erwartet={"NTFY_TOPIC"})
    assert any(f["detail"].get("fehlend") == ["NTFY_TOPIC"] for f in befunde)


def test_neue_secret_referenz_wird_erkannt(tmp_path):
    wf = WF_OK.replace("        run: echo hi\n",
                       "        env:\n          X: ${{ secrets.GEHEIM }}\n"
                       "        run: echo hi\n")
    _wf_sandbox(tmp_path, {"a.yml": wf})
    befunde = mc.check_secret_referenzen(tmp_path, erwartet=set())
    assert any(f["detail"].get("unerwartet") == ["GEHEIM"] for f in befunde)


# ═══════════════════════════════════════════════════════════════════════════
# BAUSTEIN 1c — Meldeweg: Flanke, Puls, Einmaligkeit
# ═══════════════════════════════════════════════════════════════════════════
def _kein_netz(monkeypatch):
    gesendet = []
    monkeypatch.setattr(
        notify, "_post",
        lambda url, data, headers, timeout: gesendet.append(
            {"titel": headers.get("Title"), "prio": headers.get("Priority"),
             "text": data.decode("utf-8")}))
    return gesendet


JETZT = _dt.datetime(2026, 8, 10, 6, 30, tzinfo=_dt.timezone.utc)


def test_puls_kommt_einmal_pro_monat(tmp_path, monkeypatch):
    """Ohne Puls waere Stille doppeldeutig: „nichts gefunden" saehe genauso aus
    wie „Cron seit Wochen tot"."""
    _sandbox(tmp_path, monkeypatch)
    gesendet = _kein_netz(monkeypatch)
    monkeypatch.setattr(mc, "sammle_befunde", lambda *a, **k: [])
    erg = mc.run("topic", JETZT, base=tmp_path)
    assert erg["puls"] is True and len(gesendet) == 1
    assert gesendet[0]["prio"] == "low"
    # Zweiter Lauf im selben Monat: still.
    erg2 = mc.run("topic", JETZT + _dt.timedelta(days=7), base=tmp_path)
    assert erg2["puls"] is False and len(gesendet) == 1
    # Naechster Monat: wieder ein Lebenszeichen.
    erg3 = mc.run("topic", JETZT + _dt.timedelta(days=30), base=tmp_path)
    assert erg3["puls"] is True and len(gesendet) == 2


def test_bei_befund_gibt_es_KEINEN_puls(tmp_path, monkeypatch):
    """Genau ein Push pro Lauf — wie beim Herzschlag. Zwei Pushes fuer denselben
    Lauf machen den leisen wertlos."""
    _sandbox(tmp_path, monkeypatch)
    gesendet = _kein_netz(monkeypatch)
    monkeypatch.setattr(mc, "sammle_befunde", lambda *a, **k: [
        mc._finding("testregel", mc.WARN, "etwas stimmt nicht")])
    erg = mc.run("topic", JETZT, base=tmp_path)
    assert erg["gepusht"] is True and erg["puls"] is False
    assert len(gesendet) == 1 and gesendet[0]["prio"] == "default"


def test_crit_hebt_die_prioritaet(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    gesendet = _kein_netz(monkeypatch)
    monkeypatch.setattr(mc, "sammle_befunde", lambda *a, **k: [
        mc._finding("testregel", mc.CRIT, "die Liste ist blind")])
    mc.run("topic", JETZT, base=tmp_path)
    assert gesendet[0]["prio"] == "high"


def test_unveraenderter_befund_pusht_nicht_erneut(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    gesendet = _kein_netz(monkeypatch)
    monkeypatch.setattr(mc, "sammle_befunde", lambda *a, **k: [
        mc._finding("testregel", mc.WARN, "unveraendert")])
    mc.run("topic", JETZT, base=tmp_path)
    mc.run("topic", JETZT + _dt.timedelta(days=7), base=tmp_path)
    assert len(gesendet) == 1, "die Flanken-Drossel greift nicht"


def test_ein_stehender_befund_verhindert_das_alles_sauber(tmp_path,
                                                          monkeypatch):
    """BEFUND DIESES PRs, von diesem Test gefunden.

    Erster Entwurf haengte den Puls an ``not to_push``. Ein stehender
    warn-Befund wird von der Drossel aber zwei Laeufe lang NICHT gepusht — in
    genau diesen Laeufen waere ein „alles sauber" rausgegangen, waehrend der
    Befund stand. Ein Lebenszeichen, das ueber einen offenen Befund
    hinwegmeldet, ist schlimmer als keins. Bedingung ist jetzt ``not befunde``.
    """
    _sandbox(tmp_path, monkeypatch)
    gesendet = _kein_netz(monkeypatch)
    monkeypatch.setattr(mc, "sammle_befunde", lambda *a, **k: [
        mc._finding("testregel", mc.WARN, "steht weiterhin")])
    mc.run("topic", JETZT, base=tmp_path)                       # Push
    erg = mc.run("topic", JETZT + _dt.timedelta(days=7), base=tmp_path)
    assert erg["puls"] is False
    assert not any("sauber" in g["titel"] for g in gesendet), \
        'ein „alles sauber" ging raus, obwohl ein Befund stand'


def test_der_lauf_schreibt_last_run_utc(tmp_path, monkeypatch):
    """Baustein 3: genau dieses Feld liest die Health-Regel."""
    _sandbox(tmp_path, monkeypatch)
    _kein_netz(monkeypatch)
    monkeypatch.setattr(mc, "sammle_befunde", lambda *a, **k: [])
    mc.run("topic", JETZT, base=tmp_path)
    st = json.loads((tmp_path / "data" / "maintenance_state.json")
                    .read_text(encoding="utf-8"))
    assert st["last_run_utc"] == "2026-08-10T06:30:00Z"
    # ... und der Tageslauf haelt ihn danach fuer frisch.
    monkeypatch.setattr(hc, "REPO_ROOT", tmp_path)
    assert hc.check_maintenance(_report("2026-08-11T21:45:00Z")) == []


def test_dry_run_schreibt_nichts(tmp_path, monkeypatch):
    _sandbox(tmp_path, monkeypatch)
    _kein_netz(monkeypatch)
    monkeypatch.setattr(mc, "sammle_befunde", lambda *a, **k: [])
    mc.run("topic", JETZT, base=tmp_path, schreiben=False)
    assert not (tmp_path / "data" / "maintenance_state.json").exists()


def test_der_wartungslauf_HANDELT_nie():
    """Leitplanke, statisch geprueft: kein Loeschen, kein Reparieren, kein
    Selbst-Dispatch. Der Waechter meldet — mehr nicht."""
    quelle = (ROOT / "scripts/maintenance_check.py").read_text(encoding="utf-8")
    for verboten in ("unlink(", "rmtree", "shutil", "subprocess",
                     "workflow_dispatch", "git commit", "os.remove"):
        assert verboten not in quelle, \
            f"der Wartungs-Waechter enthaelt `{verboten}` — er soll nur melden"


def test_eine_flanken_logik_kein_nachbau():
    """`evaluate_edges` wird importiert, nicht nachgebaut — zwei Fassungen
    derselben Push-Drossel liefen auseinander, ohne dass es auffiele."""
    assert mc.hc.evaluate_edges is hc.evaluate_edges
    quelle = (ROOT / "scripts/maintenance_check.py").read_text(encoding="utf-8")
    assert "def evaluate_edges" not in quelle


def _wf_ohne_kommentare(name: str) -> str:
    """Workflow-Text OHNE Kommentarzeilen.

    BERICHTIGUNG 09.08.2026, gefunden von einer ueberlebenden Mutationsprobe:
    die Zusicherungen unten suchten Zeichenfolgen im ROHTEXT. `if: failure()`
    und `curl` stehen in dieser Datei aber auch in ERKLAERENDEN KOMMENTAREN —
    ein Test, der den echten Step loescht, blieb dadurch gruen. Dieselbe Klasse
    wie der #88-Fund: eine Zusicherung muss an etwas haengen, das NUR die
    geprueffte Stelle erzeugen kann. Kommentare koennen es nicht.
    """
    text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    return "\n".join(z for z in text.splitlines()
                     if not z.lstrip().startswith("#"))


def test_der_workflow_faehrt_die_volle_historie():
    """Ein flacher Klon liesse die forensischen Tests still ueberspringen —
    ein Wartungslauf waere dann gruen, ohne sie gefahren zu haben."""
    code = _wf_ohne_kommentare("maintenance.yml")
    assert "fetch-depth: 0" in code
    assert "python -m pytest -q" in code


def test_der_waechter_darf_nicht_still_sterben():
    """Der `if: failure()`-Push, geprueft am CODE statt am Kommentar."""
    code = _wf_ohne_kommentare("maintenance.yml")
    assert "if: failure()" in code, "der Waechter darf nicht still sterben"
    assert "curl" in code, \
        "der Fehlschlag-Push muss als reiner curl ausserhalb des Python-Pfads " \
        "liegen — ein gebrochener Python-/Pip-Schritt darf den Alarm nicht " \
        "mitreissen"
    assert "ntfy.sh" in code
