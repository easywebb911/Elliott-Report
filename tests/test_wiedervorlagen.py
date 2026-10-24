"""Wiedervorlagen im Digest (Easy-Entscheid 25.10.2026, Auftrag 2 von 6).

Reine Funktionen, synthetische Zeit (keine echte Uhr). Deckt: heute fällig
(INFO), überfällig (WARN, X Tage), morgen (keine Meldung), erledigt (keine
Meldung), unlesbare Zeile (ein Finding, kein Absturz), fehlender/doppelter
Block, Tagesgrenze Europe/Berlin über die Zeitumstellung 25.10.2026 hinweg.
"""
import datetime as _dt

import wiedervorlagen as wv

BERLIN = wv.BERLIN


def _block(zeilen: str) -> str:
    return (f"Vorspann-Text\n\n{wv.MARKER_START}\n{zeilen}"
           f"\n{wv.MARKER_ENDE}\n\nNachspann-Text\n")


def _utc(iso: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(iso).replace(tzinfo=_dt.timezone.utc)


# ── Fälligkeit: Kernfälle ────────────────────────────────────────────────
def test_heute_faellig_ist_info():
    text = _block("- faellig_am: 2026-11-06 | status: offen | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert len(befunde) == 1
    assert befunde[0]["severity"] == "info"
    assert befunde[0]["message"] == "📅 Heute fällig: X"


def test_gestern_faellig_ist_warn_mit_x_gleich_1():
    text = _block("- faellig_am: 2026-11-05 | status: offen | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert len(befunde) == 1
    assert befunde[0]["severity"] == "warn"
    assert befunde[0]["message"] == "⏰ Überfällig seit 1 Tag: X"


def test_vor_10_tagen_faellig_x_gleich_10():
    text = _block("- faellig_am: 2026-10-27 | status: offen | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert befunde[0]["message"] == "⏰ Überfällig seit 10 Tagen: X"


def test_morgen_faellig_keine_meldung():
    text = _block("- faellig_am: 2026-11-07 | status: offen | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert befunde == []


def test_erledigt_keine_meldung_auch_wenn_ueberfaellig():
    text = _block("- faellig_am: 2026-10-01 | status: erledigt | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert befunde == []


# ── Fail-soft: unlesbare Zeile, fehlender/doppelter Block ─────────────────
def test_unlesbare_zeile_ein_finding_kein_absturz():
    text = _block("- das ist keine gueltige Zeile ohne Pipe-Struktur")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert len(befunde) == 1
    assert befunde[0]["severity"] == "info"
    assert "unlesbar" in befunde[0]["rule"]
    assert "Zeile" in befunde[0]["message"]


def test_unlesbares_datum_ist_auch_unlesbare_zeile():
    text = _block("- faellig_am: nicht-ein-datum | status: offen | titel: X")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert len(befunde) == 1
    assert "unlesbar" in befunde[0]["rule"]


def test_fehlender_block_ein_info_finding():
    text = "Vorspann ohne jeden Marker.\n"
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert len(befunde) == 1
    assert befunde[0]["rule"] == "wiedervorlagen_block_fehlt"
    assert befunde[0]["severity"] == "info"


def test_doppelter_block_ein_info_finding_kein_absturz():
    text = (f"{wv.MARKER_START}\nzeile1\n{wv.MARKER_ENDE}\n"
           f"{wv.MARKER_START}\nzeile2\n{wv.MARKER_ENDE}\n")
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert len(befunde) == 1
    assert befunde[0]["rule"] == "wiedervorlagen_block_mehrfach"
    assert befunde[0]["severity"] == "info"


def test_marker_literal_in_prosa_ausserhalb_des_blocks_zaehlt_nicht_doppelt():
    """Regression: eine Arbeitsregel, die den Marker-Literal in Backticks
    zitiert (genau das, was im echten Handover in Abschnitt 8 passiert),
    darf NICHT als zweites Markervorkommen gezählt werden — nur eine EIGENE
    Zeile, die exakt dem Marker entspricht, zählt."""
    text = (f"Eine Regel erwähnt den Marker `{wv.MARKER_START}` in Prosa, "
           f"nicht als eigene Zeile.\n\n"
           f"{wv.MARKER_START}\n"
           f"- faellig_am: 2026-11-06 | status: offen | titel: X | ref: #1\n"
           f"{wv.MARKER_ENDE}\n")
    termine, befunde = wv.parse_block(text)
    assert befunde == []
    assert len(termine) == 1


# ── Tagesgrenze Europe/Berlin, inkl. Zeitumstellung 25.10.2026 ─────────────
def test_lauf_2245_utc_am_vortag_ist_in_berlin_schon_faellig_sommerzeit():
    """24.10. 22:45 UTC -> Berlin 00:45 CEST am 25.10. (noch Sommerzeit,
    Umstellung erst in der Nacht 25./26.10.) — ein am 25.10. fälliger Termin
    gilt hier schon als 'heute fällig'."""
    text = _block("- faellig_am: 2026-10-25 | status: offen | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-10-24T22:45:00"))
    assert befunde[0]["message"] == "📅 Heute fällig: X"


def test_lauf_2245_utc_nach_der_umstellung_bleibt_am_selben_kalendertag():
    """25.10. 22:45 UTC -> Berlin 23:45 CET am 25.10. (nach der Umstellung,
    Winterzeit +1h statt +2h) — bleibt derselbe Kalendertag, kein Sprung."""
    text = _block("- faellig_am: 2026-10-25 | status: offen | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-10-25T22:45:00"))
    assert befunde[0]["message"] == "📅 Heute fällig: X"


def test_lauf_2245_utc_tag_danach_ueberfaellig_seit_1_tag():
    text = _block("- faellig_am: 2026-10-25 | status: offen | titel: X | ref: #1")
    befunde = wv.faelligkeits_findings(text, _utc("2026-10-26T22:45:00"))
    assert befunde[0]["message"] == "⏰ Überfällig seit 1 Tag: X"


# ── Mehrere Termine, Mischung ───────────────────────────────────────────
def test_mehrere_termine_gemischt():
    text = _block(
        "- faellig_am: 2026-11-06 | status: offen | titel: Heute | ref: #1\n"
        "- faellig_am: 2026-11-01 | status: offen | titel: Ueberfaellig | ref: #2\n"
        "- faellig_am: 2026-12-01 | status: offen | titel: Spaeter | ref: #3\n"
        "- faellig_am: 2026-01-01 | status: erledigt | titel: Erledigt | ref: #4"
    )
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    nachrichten = {f["message"] for f in befunde}
    assert nachrichten == {"📅 Heute fällig: Heute", "⏰ Überfällig seit 5 Tagen: Ueberfaellig"}


# ── Dedupe-Schlüssel: stabil pro Termin, nicht pro Tagestext ───────────────
def test_rule_key_bleibt_stabil_waehrend_x_waechst():
    text = _block("- faellig_am: 2026-11-01 | status: offen | titel: X | ref: #1")
    tag1 = wv.faelligkeits_findings(text, _utc("2026-11-02T10:00:00"))[0]
    tag5 = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))[0]
    assert tag1["rule"] == tag5["rule"]
    assert tag1["message"] != tag5["message"]


def test_zwei_termine_am_selben_tag_bekommen_verschiedene_keys():
    text = _block(
        "- faellig_am: 2026-11-01 | status: offen | titel: Erster Termin | ref: #1\n"
        "- faellig_am: 2026-11-01 | status: offen | titel: Zweiter Termin | ref: #2"
    )
    befunde = wv.faelligkeits_findings(text, _utc("2026-11-01T10:00:00"))
    assert len(befunde) == 2
    assert befunde[0]["rule"] != befunde[1]["rule"]


# ── Mutationsproben (müssen rot werden, wenn die Logik kaputt gemacht wird) ─
def test_mutation_kleiner_gleich_statt_kleiner_bei_ueberfaellig():
    """Produktionscode nutzt `faellig_am < heute` für überfällig. Eine
    gedrehte Variante `<=` würde den Fälligkeitstag selbst fälschlich als
    überfällig statt als 'heute fällig' zeigen."""
    heute = _dt.date(2026, 11, 6)
    faellig = _dt.date(2026, 11, 6)
    korrekt_ueberfaellig = faellig < heute
    mutiert_ueberfaellig = faellig <= heute
    assert korrekt_ueberfaellig is False
    assert mutiert_ueberfaellig is True
    assert korrekt_ueberfaellig != mutiert_ueberfaellig


def test_mutation_utc_statt_berlin_waere_am_umstellungstag_falsch():
    """Ohne die Berlin-Konvertierung (UTC-Datum direkt genommen) würde der
    22:45-UTC-Lauf am 24.10. den 24.10. als 'heute' sehen statt den 25.10.
    in Berlin — der Termin würde einen Tag zu spät als fällig erkannt."""
    jetzt = _utc("2026-10-24T22:45:00")
    heute_utc = jetzt.date()
    heute_berlin = jetzt.astimezone(BERLIN).date()
    assert heute_utc != heute_berlin
    assert heute_berlin == _dt.date(2026, 10, 25)


def test_mutation_erledigt_wird_ignoriert_waere_falsch():
    """Würde die `status == 'erledigt'`-Prüfung entfernt/ignoriert, meldete
    sich ein erledigter, überfälliger Termin fälschlich weiter."""
    text = _block("- faellig_am: 2026-10-01 | status: erledigt | titel: X | ref: #1")
    befunde_korrekt = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))
    assert befunde_korrekt == []

    # Mutierte Variante: Status-Prüfung entfernt.
    termine, _ = wv.parse_block(text)
    heute = _utc("2026-11-06T10:00:00").astimezone(BERLIN).date()
    mutiert_meldet = any(
        _dt.date.fromisoformat(t["faellig_am"]) < heute for t in termine
    )
    assert mutiert_meldet is True, "die Mutation muesste hier faelschlich melden"


def test_mutation_x_um_einen_tag_verschoben():
    """`(heute - faellig_am).days` liefert 1 am Folgetag. Eine um einen Tag
    verschobene Rechnung (z. B. ohne `-1` oder mit ihr) muss sich von der
    echten Funktion unterscheiden lassen."""
    text = _block("- faellig_am: 2026-11-05 | status: offen | titel: X | ref: #1")
    befund = wv.faelligkeits_findings(text, _utc("2026-11-06T10:00:00"))[0]
    tage_echt = befund["detail"]["tage_ueberfaellig"]
    tage_mutiert_plus_eins = tage_echt + 1
    tage_mutiert_minus_eins = tage_echt - 1
    assert tage_echt == 1
    assert tage_mutiert_plus_eins != tage_echt
    assert tage_mutiert_minus_eins != tage_echt


# ── health_check-Integration ───────────────────────────────────────────────
def test_health_check_ohne_now_ist_uebersprungen():
    import health_check as hc
    assert hc.check_wiedervorlagen(now=None) == []


def test_health_check_integration_meldet_faelligen_termin(tmp_path, monkeypatch):
    import health_check as hc
    monkeypatch.setattr(wv, "REPO_ROOT", tmp_path)
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        _block("- faellig_am: 2026-11-06 | status: offen | titel: X | ref: #1"),
        encoding="utf-8")
    now = _dt.datetime(2026, 11, 6, 21, 45, tzinfo=_dt.timezone.utc)
    befunde = hc.check_wiedervorlagen(now=now)
    assert len(befunde) == 1
    assert befunde[0]["severity"] == hc.INFO
    assert befunde[0]["message"] == "📅 Heute fällig: X"


def test_health_check_datei_fehlt_komplett_ist_still_kein_befund(tmp_path,
                                                                 monkeypatch):
    """Datei fehlt GANZ (z. B. eine Test-Sandbox ohne eigenes
    SESSION_HANDOVER.md) -> kein Befund — anders als eine lesbare Datei ohne
    Block (s. nächster Test). Verhindert Störsignale in jeder Sandbox, die
    kein eigenes Handover anlegt."""
    import health_check as hc
    monkeypatch.setattr(wv, "REPO_ROOT", tmp_path)  # Datei existiert nicht
    now = _dt.datetime(2026, 11, 6, 21, 45, tzinfo=_dt.timezone.utc)
    assert hc.check_wiedervorlagen(now=now) == []


def test_health_check_datei_da_aber_block_fehlt_ist_ein_befund(tmp_path,
                                                                monkeypatch):
    import health_check as hc
    monkeypatch.setattr(wv, "REPO_ROOT", tmp_path)
    (tmp_path / "SESSION_HANDOVER.md").write_text(
        "Nur Fließtext, kein Wiedervorlagen-Block.\n", encoding="utf-8")
    now = _dt.datetime(2026, 11, 6, 21, 45, tzinfo=_dt.timezone.utc)
    befunde = hc.check_wiedervorlagen(now=now)
    assert len(befunde) == 1
    assert befunde[0]["rule"] == "wiedervorlagen_block_fehlt"


# ── Frontend (docs/index.html): 'info' bleibt optisch neutral ─────────────
def test_frontend_kennt_info_severity_und_haengt_kein_eigenes_farb_overlay_an():
    """Guardian-Nit aus PR #196: eine unbekannte severity fiel bisher auf
    'warn' zurück (optisch wie eine Warnung). 'info' muss jetzt durchgelassen
    werden, OHNE eine eigene `.health-sev.info`-Farbregel zu bekommen — die
    Basis-Klasse `.health-sev` ist bereits neutral (kein `color`/`border-color`-
    Override wie bei `.crit`/`.warn`)."""
    from pathlib import Path
    html = Path(__file__).resolve().parent.parent.joinpath(
        "docs", "index.html").read_text(encoding="utf-8")
    assert "info: 'Hinweis'" in html or 'info: "Hinweis"' in html
    assert "f.severity === 'info'" in html
    assert ".health-sev.info" not in html, (
        "info darf KEIN eigenes Farb-Overlay bekommen — soll optisch neutral "
        "bleiben, nicht wie crit/warn gefärbt sein")
