"""In-Session-Marker — Kriterium, Backfill, laufende Markierung, Beweissicherung.

ANLASS (07.08.2026): 34 von 69 Bestands-Records entstanden in Läufen, deren
Report-Stempel INNERHALB der Sitzung des eigenen Markts lag. Alles, was die
Anlage einfriert, ist dort ein Zwischenstand — `entry_close`, Score,
`confluence`, `vol_*`, `ambiguity_n*`, `agent_concern_level` und die AUSWAHL
selbst. Beschluss Easy: EIN Marker, kein Ausschluss, nichts heilen.

DAS KRITERIUM (K2, nach Rückfrage entschieden): Stempel im Sitzungsfenster des
eigenen Markts UND Ortszeit-Kalendertag des Stempels == Bar-Datum. Die zweite
Bedingung ist nicht Zierrat: ohne sie markiert das Verfahren 35 statt 34 —
`ADS.DE @ 2026-07-25T13:35:26Z`, ein Dispatch am **Samstag** 15:35 CEST auf die
FERTIGE Freitags-Bar. Ein eigener Test nagelt genau diesen Fall fest.

Alle Soll-Werte sind von Hand hergeleitet und im Docstring ausgeschrieben.
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import in_session as ins  # noqa: E402
import market_calendar as cal  # noqa: E402
import collect_in_session_evidence as ev  # noqa: E402
import mark_in_session_creation as mark  # noqa: E402

COLL = ROOT / "data" / "forward_collection.json"
EVIDENCE = ROOT / "data" / "in_session_evidence.json"


def _coll():
    return json.loads(COLL.read_text(encoding="utf-8"))


def _utc(markt: str, lokal: str) -> str:
    """Ortszeit -> UTC-Stempel. Die Soll-Zeiten stehen damit LESBAR im Test."""
    tz = ZoneInfo(cal.MARKET_SESSIONS[markt]["tz"])
    naiv = _dt.datetime.strptime(lokal, "%Y-%m-%d %H:%M:%S")
    return (naiv.replace(tzinfo=tz).astimezone(ZoneInfo("UTC"))
            .strftime("%Y-%m-%dT%H:%M:%SZ"))


def _hat_historie() -> bool:
    """Flacher Klon? Dann kein Replay — mit GRUND überspringen statt leer grün.

    Die #68-Lehre: `actions/checkout` klont per Default flach, und ein Replay
    findet dann EINEN Stand statt siebzig. Ein Test, der das nicht merkt,
    behauptet Grün, wo nichts geprüft wurde.
    """
    n = len(subprocess.run(["git", "log", "--format=%H", "--", "data/report.json"],
                           cwd=ROOT, capture_output=True, text=True).stdout.split())
    return n >= 40


braucht_historie = pytest.mark.skipif(
    not _hat_historie(),
    reason="flacher Klon — `git fetch --unshallow` für den Historien-Beleg nötig")


# ===========================================================================
# 1 · DAS FENSTER — Soll von Hand, Sommer UND Winter, je Markt
# ===========================================================================
# US: NYSE 09:30–16:00 America/New_York. Sommer 2026-08-07 (EDT, UTC−4),
#     Winter 2026-01-15 (EST, UTC−5).
# DE: Xetra 09:00–17:30 Europe/Berlin. Sommer 2026-08-07 (CEST, UTC+2),
#     Winter 2026-01-15 (CET, UTC+1).
# Grenzen laut Auftrag: exklusiv Eröffnung, exklusiv Schluss.
@pytest.mark.parametrize("markt,tag,zeit,soll", [
    # --- US, Sommer -------------------------------------------------------
    ("US", "2026-08-07", "09:29:59", False),   # eine Sekunde VOR Eröffnung
    ("US", "2026-08-07", "09:30:00", False),   # EXAKT Eröffnung -> exklusiv
    ("US", "2026-08-07", "09:30:01", True),    # eine Sekunde danach
    ("US", "2026-08-07", "09:30:30", True),    # (Stunde,Minute)-Tupel fiele hier durch
    ("US", "2026-08-07", "15:59:59", True),    # eine Sekunde VOR Schluss
    ("US", "2026-08-07", "16:00:00", False),   # EXAKT Schlussminute -> nicht in-session
    ("US", "2026-08-07", "16:00:01", False),   # danach
    # --- US, Winter -------------------------------------------------------
    ("US", "2026-01-15", "09:30:00", False),
    ("US", "2026-01-15", "09:30:01", True),
    ("US", "2026-01-15", "15:59:59", True),
    ("US", "2026-01-15", "16:00:00", False),
    # --- DE, Sommer -------------------------------------------------------
    ("DE", "2026-08-07", "08:59:59", False),
    ("DE", "2026-08-07", "09:00:00", False),
    ("DE", "2026-08-07", "09:00:01", True),
    ("DE", "2026-08-07", "17:29:59", True),
    ("DE", "2026-08-07", "17:30:00", False),
    ("DE", "2026-08-07", "17:30:01", False),
    # --- DE, Winter -------------------------------------------------------
    ("DE", "2026-01-15", "09:00:00", False),
    ("DE", "2026-01-15", "09:00:01", True),
    ("DE", "2026-01-15", "17:29:59", True),
    ("DE", "2026-01-15", "17:30:00", False),
])
def test_sitzungsfenster_grenzen(markt, tag, zeit, soll):
    assert ins.im_sitzungsfenster(markt, _utc(markt, f"{tag} {zeit}")) is soll


def test_dst_zwischenwochen_us_und_eu_sind_verschieden():
    """USA und EU stellen an verschiedenen Terminen um — 2026: US 08.03.,
    EU 29.03. In der Zwischenwoche (z. B. 2026-03-20) beträgt der Abstand
    NY↔Berlin 5 statt 6 Stunden. Ein fester UTC-Offset wäre dort falsch.

    Soll von Hand: 2026-03-20 ist US bereits EDT (UTC−4), EU noch CET (UTC+1).
    14:00 UTC = 10:00 New York (in Sitzung) = 15:00 Berlin (in Sitzung).
    12:30 UTC = 08:30 New York (VOR Eröffnung) = 13:30 Berlin (in Sitzung).
    """
    assert ins.im_sitzungsfenster("US", "2026-03-20T14:00:00Z") is True
    assert ins.im_sitzungsfenster("DE", "2026-03-20T14:00:00Z") is True
    assert ins.im_sitzungsfenster("US", "2026-03-20T12:30:00Z") is False
    assert ins.im_sitzungsfenster("DE", "2026-03-20T12:30:00Z") is True


def test_schluss_deckt_sich_mit_dem_waechter_begriff():
    """Kein zweiter Begriff von „Schluss": genau auf der Marke gilt die Sitzung
    bei `cal.sitzung_beendet` als beendet — hier also NICHT als in-session."""
    for markt, lokal in (("US", "2026-08-07 16:00:00"), ("DE", "2026-08-07 17:30:00")):
        stempel = _utc(markt, lokal)
        dt = _dt.datetime.strptime(stempel, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=ZoneInfo("UTC"))
        assert cal.sitzung_beendet(markt, dt) is True
        assert ins.im_sitzungsfenster(markt, stempel) is False


def test_schlusszeit_kommt_aus_market_sessions_nicht_aus_einer_kopie():
    """EINE Quelle: wird der Schluss im Kalender verschoben, wandert der Marker
    mit. Beleg per Monkeypatch statt per Quelltext-Nähe."""
    original = dict(cal.MARKET_SESSIONS["US"])
    try:
        cal.MARKET_SESSIONS["US"] = {"tz": "America/New_York", "close": (12, 0)}
        assert ins.im_sitzungsfenster("US", _utc("US", "2026-08-07 13:00:00")) is False
        assert ins.im_sitzungsfenster("US", _utc("US", "2026-08-07 11:00:00")) is True
    finally:
        cal.MARKET_SESSIONS["US"] = original
    # Und wieder wie vorher — sonst hätte der Test die Suite vergiftet.
    assert ins.im_sitzungsfenster("US", _utc("US", "2026-08-07 13:00:00")) is True


# ===========================================================================
# 2 · NICHT BERECHENBAR IST NICHT „NEIN"
# ===========================================================================
@pytest.mark.parametrize("markt,stempel", [
    ("XX", "2026-08-07T14:00:00Z"),       # unbekannter Markt
    ("US", "2026-08-07 14:00:00"),        # naiv, ohne Zone
    ("US", "kein datum"),
    ("US", ""),
    ("US", None),
    (None, "2026-08-07T14:00:00Z"),
])
def test_nicht_berechenbar_liefert_none(markt, stempel):
    assert ins.im_sitzungsfenster(markt, stempel) is None
    assert ins.ist_in_session_anlage(markt, stempel, "2026-08-07") is None


def test_fehlendes_bar_datum_ist_nicht_berechenbar():
    """Ohne Bar-Datum ist die zweite Bedingung nicht prüfbar — None, nicht False.
    Sonst verschwände ein Marker geräuschlos."""
    stempel = _utc("US", "2026-08-07 14:00:00")
    assert ins.im_sitzungsfenster("US", stempel) is True
    for bar in (None, "", "   ", 20260807):
        assert ins.ist_in_session_anlage("US", stempel, bar) is None


# ===========================================================================
# 3 · K2 — DIE ZWEITE BEDINGUNG, UND WARUM ES SIE GIBT
# ===========================================================================
def test_der_samstags_fall_wird_nicht_markiert():
    """`ADS.DE @ 2026-07-25T13:35:26Z` = Samstag 15:35 CEST.

    Im Uhrzeit-Fenster 09:00–17:30 — aber der 25.07.2026 ist ein Samstag, es
    gab keine Sitzung, und eingefroren wurde die FERTIGE Freitags-Bar vom
    24.07. Ohne die Tages-Bedingung markierte das Verfahren 35 statt 34.
    """
    stempel = "2026-07-25T13:35:26Z"
    assert ins.im_sitzungsfenster("DE", stempel) is True          # Uhrzeit passt
    assert cal.is_trading_day(_dt.date(2026, 7, 25)) is False     # Sitzung gab es nicht
    assert ins.ist_in_session_anlage("DE", stempel, "2026-07-24") is False


def test_tagesvergleich_schlaegt_is_trading_day():
    """Warum der Tagesvergleich und nicht `is_trading_day`: ein Lauf an einem
    HANDELSTAG, der wegen des Ein-Tag-Versatzes (Registry 30.07.) noch die
    fertige Bar von T−1 einfriert, wäre mit `is_trading_day` fälschlich
    markiert. Soll von Hand: Freitag 2026-08-07, 10:46 New York — Handelstag
    und in Sitzung, aber die eingefrorene Bar ist die vom 06.08.
    """
    stempel = _utc("US", "2026-08-07 10:46:00")
    assert cal.is_trading_day(_dt.date(2026, 8, 7)) is True
    assert ins.im_sitzungsfenster("US", stempel) is True
    assert ins.ist_in_session_anlage("US", stempel, "2026-08-07") is True   # eigene Bar
    assert ins.ist_in_session_anlage("US", stempel, "2026-08-06") is False  # fertige Bar


@pytest.mark.parametrize("markt,feiertag,lokal,bar,was", [
    # NYSE zu, Xetra offen: Thanksgiving (4. Donnerstag im November) 2026.
    ("US", "2026-11-26", "2026-11-26 11:00:00", "2026-11-25", "Thanksgiving"),
    # NYSE zu, Xetra offen: Independence Day, hier der Freitag 03.07.2026.
    ("US", "2026-07-03", "2026-07-03 11:00:00", "2026-07-02", "July 4 (beobachtet)"),
    # Xetra zu, NYSE offen: 1. Mai 2026 (Freitag).
    ("DE", "2026-05-01", "2026-05-01 12:00:00", "2026-04-30", "1. Mai"),
    # Xetra zu, NYSE offen: Ostermontag 2026 (06.04.).
    ("DE", "2026-04-06", "2026-04-06 12:00:00", "2026-04-02", "Ostermontag"),
])
def test_einzelmarkt_feiertage_erzeugen_KEINEN_false_positive(markt, feiertag,
                                                              lokal, bar, was):
    """GUARDIAN-NIT: der Fall war korrekt, aber nirgends als Test benannt.

    An einem Einzelmarkt-Feiertag (nur EIN Markt zu — `FULL_CLOSURE` kennt nur
    die gemeinsamen Schließtage, s. #71) liegt ein Lauf zur Mittagszeit im
    Uhrzeit-Fenster, die eingefrorene Bar ist aber die FERTIGE des letzten
    Handelstags. Das Kriterium fängt das **strukturell** über den
    Tagesvergleich ab — es braucht dafür KEINE Feiertagsliste, und genau das
    ist der Grund, warum es dem `is_trading_day`-Ansatz überlegen ist.
    """
    stempel = _utc(markt, lokal)
    assert ins.im_sitzungsfenster(markt, stempel) is True, f"{was}: Vorbedingung"
    assert ins.ist_in_session_anlage(markt, stempel, bar) is False, was
    # Gegenprobe: derselbe Lauf auf die BAR DES TAGES wäre sehr wohl in-session.
    assert ins.ist_in_session_anlage(markt, stempel, feiertag) is True


def test_tagesvergleich_rechnet_in_ortszeit_nicht_in_utc():
    """Der Freitags-Abend-Cron (22:40 UTC) liegt für DE im NÄCHSTEN Ortstag
    (00:40 CEST Samstag). In UTC gerechnet wäre der Tagesvergleich schief.
    Hier fällt er ohnehin aus dem Fenster — der Test hält die Rechenart fest.

    EHRLICH ZUR BEWEISKRAFT: die Mutation „Tagesvergleich in UTC statt
    Ortszeit" ÜBERLEBT die Suite — und zwar zu Recht, sie ist ein
    ÄQUIVALENTER MUTANT, keine Testlücke. Beide Sitzungsfenster liegen
    vollständig innerhalb EINES UTC-Tages (US 13:30–21:00 UTC, DE 07:00–16:30
    UTC über beide Zeitzonen-Stände), Ortszeit- und UTC-Datum können dort also
    nicht auseinanderfallen. Nachgemessen über alle 3592 In-Sitzung-Minuten an
    Sommer-, Winter- und beiden DST-Zwischenwochen-Tagen: **null** Abweichungen.
    Der Test steht trotzdem — er hält die ABSICHT fest, damit niemand die
    Ortszeit-Rechnung später als Umstand wegoptimiert; sie trägt, sobald ein
    Markt mit über Mitternacht UTC laufender Sitzung dazukäme.
    """
    assert ins._lokal("DE", "2026-07-31T22:40:44Z").date() == _dt.date(2026, 8, 1)
    assert ins._lokal("US", "2026-07-31T22:40:44Z").date() == _dt.date(2026, 7, 31)
    assert ins.ist_in_session_anlage("DE", "2026-07-31T22:40:44Z", "2026-07-31") is False


# ===========================================================================
# 4 · BACKFILL — die 34 namentlich (abgeschlossener historischer Fakt)
# ===========================================================================
# Kein Zählerstand, sondern eine feste Liste: diese Records SIND in einer
# laufenden Sitzung entstanden, daran ändert kein künftiger Lauf etwas.
# Quelle: data/forward_collection.json, Backfill vom 07.08.2026.
BACKFILL_34 = [
    ("G1A.DE", "2026-07-23T12:18:27Z"), ("HAG.DE", "2026-07-23T12:18:27Z"),
    ("PBB.DE", "2026-07-23T12:18:27Z"), ("TKA.DE", "2026-07-23T12:18:27Z"),
    ("WAC.DE", "2026-07-23T12:18:27Z"), ("RTX", "2026-07-23T17:35:27Z"),
    ("ADS.DE", "2026-07-24T14:36:19Z"), ("HAG.DE", "2026-07-24T14:36:19Z"),
    ("RWE.DE", "2026-07-24T14:36:19Z"), ("XEL", "2026-07-24T14:36:19Z"),
    ("NVDA", "2026-07-24T16:11:02Z"), ("SPG", "2026-07-24T16:29:23Z"),
    ("MTX.DE", "2026-07-27T07:35:28Z"), ("VBK.DE", "2026-07-27T07:35:28Z"),
    ("SYY", "2026-07-27T15:58:44Z"), ("HD", "2026-07-28T16:07:56Z"),
    ("LLY", "2026-07-28T16:07:56Z"), ("A", "2026-07-28T18:56:01Z"),
    ("GE", "2026-07-29T15:45:36Z"), ("HUM", "2026-07-29T18:14:26Z"),
    ("KKR", "2026-07-29T19:53:25Z"), ("GXI.DE", "2026-07-31T11:16:07Z"),
    ("HAG.DE", "2026-07-31T11:16:07Z"), ("BAYN.DE", "2026-08-05T13:06:41Z"),
    ("SZG.DE", "2026-08-05T13:06:41Z"), ("APD", "2026-08-05T18:05:09Z"),
    ("LULU", "2026-08-05T18:05:09Z"), ("MCO", "2026-08-05T18:05:09Z"),
    ("COF", "2026-08-06T19:52:00Z"), ("DOW", "2026-08-06T19:52:00Z"),
    ("NWSA", "2026-08-06T19:52:00Z"), ("DUE.DE", "2026-08-07T14:46:04Z"),
    ("SYK", "2026-08-07T14:46:04Z"), ("TKA.DE", "2026-08-07T14:46:04Z"),
]
# ADS.DE @ 2026-07-25T13:35:26Z steht bewusst NICHT auf der Liste (Samstag).


def test_das_kriterium_liefert_genau_die_34():
    treffer, unklar = ins.betroffene_records(_coll()["records"])
    assert unklar == [], "kein Record darf unberechenbar sein"
    assert sorted(ins.record_key(r) for r in treffer) == sorted(BACKFILL_34)


def test_die_ausgelieferte_sammlung_traegt_genau_diese_34_marker():
    """Nicht nur die Rechnung — die DATEI muss die Marker wirklich tragen."""
    markiert = [(r["ticker"], r["created_utc"]) for r in _coll()["records"]
                if r.get(ins.MARKER) is True]
    assert sorted(markiert) == sorted(BACKFILL_34)


def test_der_samstags_record_ist_in_der_datei_unmarkiert():
    rec = [r for r in _coll()["records"]
           if ins.record_key(r) == ("ADS.DE", "2026-07-25T13:35:26Z")]
    assert len(rec) == 1
    assert ins.MARKER not in rec[0] and ins.MARKER_UTC not in rec[0]


def test_false_wird_nie_geschrieben():
    """Abwesenheit = sauber. Sonst hinge an 35 unbeteiligten Records ein Feld."""
    for r in _coll()["records"]:
        assert r.get(ins.MARKER) in (True, None)
        if ins.MARKER not in r:
            assert ins.MARKER_UTC not in r


def test_markiere_haengt_nicht_getroffenen_records_kein_feld_an():
    """WERTE-Test auf Funktionsebene, nicht auf der erzeugten Datei.

    `test_false_wird_nie_geschrieben` prüft das Artefakt — eine Code-Mutation,
    die `False` schreibt, bliebe dort unsichtbar, weil die Datei sich nicht
    ändert. Dieser Test prüft die Funktion selbst.
    """
    records = [
        {"ticker": "IN", "market": "US", "first_seen_date": "2026-08-07",
         "created_utc": _utc("US", "2026-08-07 10:46:00")},
        {"ticker": "AUS", "market": "US", "first_seen_date": "2026-08-07",
         "created_utc": _utc("US", "2026-08-07 17:00:00")},
    ]
    gesetzt, unklar = ins.markiere(records, "2026-08-07T00:00:00Z")
    assert (gesetzt, unklar) == (1, [])
    assert records[0][ins.MARKER] is True
    assert ins.MARKER not in records[1] and ins.MARKER_UTC not in records[1]


def test_marker_datum_ist_gesetzt_und_einheitlich():
    stempel = {r[ins.MARKER_UTC] for r in _coll()["records"] if r.get(ins.MARKER)}
    assert stempel == {"2026-08-07T00:00:00Z"}


def test_backfill_ist_idempotent_und_datiert_nicht_um():
    """Ein zweiter Lauf mit ANDEREM --marked-utc darf nichts umschreiben — die
    Markierung ist ein Ereignis, das einmal stattgefunden hat."""
    records = _coll()["records"]
    vorher = [dict(r) for r in records]
    gesetzt, unklar = ins.markiere(records, "2099-01-01T00:00:00Z")
    assert gesetzt == 0 and unklar == []
    assert records == vorher


def test_ruckweg_entfernt_beide_felder_restlos():
    records = _coll()["records"]
    entfernt = ins.entferne_marker(records)
    assert entfernt == 34
    for r in records:
        assert ins.MARKER not in r and ins.MARKER_UTC not in r


def test_marker_aendert_kein_bestehendes_feld():
    """Der Marker ist additiv: aus einem unmarkierten Bestand entsteht durch
    Markieren + Entmarkieren wieder GENAU der Ausgangszustand."""
    records = _coll()["records"]
    ins.entferne_marker(records)
    basis = json.dumps(records, sort_keys=True)
    ins.markiere(records, "2026-08-07T00:00:00Z")
    ins.entferne_marker(records)
    assert json.dumps(records, sort_keys=True) == basis


# ===========================================================================
# 5 · TEIL B — LAUFENDE MARKIERUNG (Verhalten, keine Mengen)
# ===========================================================================
def _kunst_coll(created, markt="US", bar="2026-08-07"):
    return {"records": [{"ticker": "TEST", "market": markt,
                         "first_seen_date": bar, "created_utc": created,
                         "entry_close": 100.0}]}


def test_ein_heute_angelegter_in_session_record_traegt_den_marker_im_selben_lauf():
    """DIE ZIEL-MECHANIK, nachgewiesen statt behauptet."""
    ts = _utc("US", "2026-08-07 10:46:00")          # NYSE offen
    coll = _kunst_coll(ts)
    gesetzt, unklar = ins.markiere_neue_records(coll, ts)
    assert (gesetzt, unklar) == (1, [])
    rec = coll["records"][0]
    assert rec[ins.MARKER] is True
    assert rec[ins.MARKER_UTC] == ts       # Lauf-Stempel, nicht Systemuhr


def test_ein_abendlauf_bleibt_unmarkiert():
    ts = _utc("US", "2026-08-07 17:30:00")          # NYSE zu
    coll = _kunst_coll(ts)
    assert ins.markiere_neue_records(coll, ts) == (0, [])
    assert ins.MARKER not in coll["records"][0]


def test_nur_records_DIESES_laufs_werden_angefasst():
    """Ein Altbestand-Record aus einem früheren Lauf bleibt unberührt — sonst
    datierte jeder Lauf die Historie neu."""
    alt = _utc("US", "2026-08-06 10:00:00")
    neu = _utc("US", "2026-08-07 10:46:00")
    coll = {"records": [
        {"ticker": "ALT", "market": "US", "first_seen_date": "2026-08-06",
         "created_utc": alt},
        {"ticker": "NEU", "market": "US", "first_seen_date": "2026-08-07",
         "created_utc": neu},
    ]}
    gesetzt, _ = ins.markiere_neue_records(coll, neu)
    assert gesetzt == 1
    assert ins.MARKER not in coll["records"][0]
    assert coll["records"][1][ins.MARKER] is True


def test_unberechenbarer_fall_blockiert_die_anlage_nicht_und_wird_laut(caplog):
    """Fail-soft, aber LAUT: Record bleibt stehen, Warnung im Log."""
    coll = _kunst_coll("2026-08-07T14:46:04Z", markt="XX")
    with caplog.at_level("WARNING", logger="in_session"):
        gesetzt, unklar = ins.markiere_neue_records(coll, "2026-08-07T14:46:04Z")
    assert gesetzt == 0 and len(unklar) == 1
    assert len(coll["records"]) == 1          # Anlage NICHT blockiert
    assert ins.MARKER not in coll["records"][0]
    laut = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("nicht berechenbar" in m for m in laut), laut
    assert any("XX" in m for m in laut), "die Warnung muss den Fall benennen"


def test_pipeline_markiert_nach_dem_update_und_vor_dem_schreiben():
    """Quelltext-Reihenfolge — die BILLIGE Absicherung. Der eigentliche Beweis
    steht darunter als echter Voll-Lauf (`test_ein_echter_lauf_…`); dieser Test
    bleibt, weil er die Absicht an der Stelle festnagelt, an der sie steht."""
    q = (ROOT / "scripts" / "elliott_pipeline.py").read_text(encoding="utf-8")
    i_update = q.index("fc.update_forward_collection(coll, report")
    i_mark = q.index("ins.markiere_neue_records(coll, ts)")
    i_write = q.index("fc.write_collection(coll)")
    assert i_update < i_mark < i_write


def _voll_lauf(tmp_path, monkeypatch, stempel: str, bar_ende: str):
    """Echter `elliott_pipeline.main()` im Offline-Modus, mit eingefrorener Uhr
    und einer synthetischen Kursreihe, die auf ``bar_ende`` endet.

    Der synthetische Fetcher ankert sonst auf 2024 (`_synthetic_dates`:
    „kein 'today'"), dann läge das Bar-Datum nie auf dem Lauf-Tag und der
    In-Session-Fall wäre end-to-end gar nicht herstellbar.

    REPO_ROOT wird auf `tmp_path` gebogen — auch für `health_check`, sonst
    schreibt der Lauf in die ECHTE `data/health_state.json` (die Lehre steht in
    `test_one_count_source`).
    """
    import elliott_pipeline as pipe
    import forward_collection as fc
    import health_check as hc

    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "docs/data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/forward_collection.json").write_text(
        json.dumps({"schema_version": 1, "records": []}), encoding="utf-8")

    class _FesteUhr(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime.strptime(stempel, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=_dt.timezone.utc)

    def _reihe(n):
        ende = _dt.date.fromisoformat(bar_ende)
        return [(ende - _dt.timedelta(days=n - 1 - i)).isoformat() for i in range(n)]

    monkeypatch.setenv("ELLIOTT_OFFLINE", "1")
    monkeypatch.setattr(pipe, "datetime", _FesteUhr)
    monkeypatch.setattr(pipe, "_synthetic_dates", _reihe)
    for modul in (pipe, fc, hc):
        monkeypatch.setattr(modul, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pipe.config, "MARKETS", {
        "US": {"label": "USA", "universe": ["AAPL", "MSFT"]},
        "DE": {"label": "Deutschland", "universe": ["SAP.DE"]},
    })
    monkeypatch.setattr(pipe, "load_watchlist", lambda: [])
    assert pipe.main() == 0
    return json.loads((tmp_path / "data/forward_collection.json")
                      .read_text(encoding="utf-8"))


def test_ein_echter_lauf_schreibt_den_marker_MIT_der_datei(tmp_path, monkeypatch):
    """DIE ZIEL-MECHANIK, end-to-end nachgewiesen statt behauptet.

    Lauf-Stempel 2026-08-07T14:46:04Z = 10:46 New York und 16:46 Berlin — beide
    Sitzungen laufen. Die Kursreihe endet am selben Tag, der Record friert also
    eine unfertige Bar ein. Geprüft wird die GESCHRIEBENE Datei: der Marker muss
    auf der Platte stehen, nicht nur im Speicher. Damit ist die Reihenfolge
    (Markierung vor `write_collection`) mitbewiesen.
    """
    coll = _voll_lauf(tmp_path, monkeypatch,
                      "2026-08-07T14:46:04Z", "2026-08-07")
    recs = coll["records"]
    assert recs, "der Lauf hat gar keine Episode angelegt — Test wertlos"
    for r in recs:
        assert r["first_seen_date"] == "2026-08-07"
        assert r[ins.MARKER] is True, r["ticker"]
        assert r[ins.MARKER_UTC] == "2026-08-07T14:46:04Z"


def test_ein_abendlauf_schreibt_den_marker_NICHT(tmp_path, monkeypatch):
    """Gegenprobe mit identischer Kursreihe, nur später am Tag: 22:40 UTC ist
    18:40 New York (Sitzung vorbei) und 00:40 Berlin des Folgetags. Kein Marker.
    Ohne diese Gegenprobe bewiese der Positiv-Test nur, dass IRGENDWAS markiert.
    """
    coll = _voll_lauf(tmp_path, monkeypatch,
                      "2026-08-07T22:40:00Z", "2026-08-07")
    recs = coll["records"]
    assert recs, "der Lauf hat gar keine Episode angelegt — Test wertlos"
    for r in recs:
        assert ins.MARKER not in r and ins.MARKER_UTC not in r


def test_die_sammlung_kennt_die_sitzungs_logik_weiterhin_nicht():
    """Der #75-Wächter bleibt scharf — der Marker sitzt NICHT in der Sammlung.
    (Spiegelt tests/test_sitzungs_ende.py, damit dieser PR sein eigenes
    Versprechen hält, statt sich auf den fremden Test zu verlassen.)"""
    q = (ROOT / "scripts" / "forward_collection.py").read_text(encoding="utf-8")
    for name in ("MARKET_SESSIONS", "zoneinfo", "in_session",
                 ins.MARKER, "sitzung_beendet"):
        assert name not in q


def test_der_marker_gatet_nichts():
    """Kein Verhalten: die Markier-Funktionen dürfen nirgends über Anlage,
    Verlängerung oder Reifung entscheiden."""
    q = (ROOT / "scripts" / "elliott_pipeline.py").read_text(encoding="utf-8")
    block = q[q.index("ins.markiere_neue_records"):]
    block = block[:block.index("fc.write_collection")]
    for verboten in ("return", "continue", "raise", "del ", "pop("):
        assert verboten not in block


# ===========================================================================
# 6 · DIE BRÜCKE — belegt, nicht angenommen
# ===========================================================================
@braucht_historie
def test_bruecke_stimmt_wo_beide_angaben_existieren():
    """`first_seen_date` == `diag.last_bar_date` des Markts im anlegenden Lauf.

    Darauf steht sowohl das Kriterium als auch die Vergleichs-Suche für Läufe
    vor #63. Geprüft über die echte Historie; ein Gegenbeispiel kippt den Test.
    """
    coll = _coll()
    historie = {h["ts"]: h for h in ev.report_historie(ROOT)}
    geprueft = 0
    for rec in coll["records"]:
        h = historie.get(rec["created_utc"])
        if not h:
            continue
        m = h["markets"].get(rec["market"]) or {}
        if m.get("last_bar_date") is None:
            continue
        assert m["last_bar_date"] == rec["first_seen_date"], rec["ticker"]
        geprueft += 1
    assert geprueft >= 29


def test_bruecke_ist_bei_mehrdeutigkeit_none_statt_raten():
    coll = {"records": [
        {"ticker": "A", "market": "US", "created_utc": "T", "first_seen_date": "2026-08-06"},
        {"ticker": "B", "market": "US", "created_utc": "T", "first_seen_date": "2026-08-07"},
    ]}
    assert ev.bar_datum_bruecke(coll)[("T", "US")] is None


@braucht_historie
def test_bruecke_ist_im_bestand_nirgends_mehrdeutig():
    for schl, wert in ev.bar_datum_bruecke(_coll()).items():
        assert wert is not None, schl


@braucht_historie
def test_alle_created_utc_sind_committete_report_stempel():
    """Die Gleichsetzung created_utc == Report-Stempel, auf der das Kriterium
    steht — belegt statt angenommen."""
    stempel = mark.committete_report_stempel(ROOT)
    assert len(stempel) >= 40
    assert mark.pruefe_stempel_identitaet(_coll()["records"], stempel) == []


# ===========================================================================
# 7 · TEIL C — BEWEISSICHERUNG
# ===========================================================================
def test_evidence_datei_ist_vollstaendig_und_konsistent():
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema_version"] == 1
    markiert = {ins.record_key(r) for r in _coll()["records"] if r.get(ins.MARKER)}
    for e in d["records"]:
        assert (e["ticker"], e["created_utc"]) in markiert, e["ticker"]
        soll = round((e["entry_close_frozen"] - e["close_after_session"])
                     / e["close_after_session"] * 100.0, 4)
        assert e["deviation_pct"] == soll
        assert e["bar_date_source"] in ("diag", "bruecke")
        assert e["source_run_utc"] > e["created_utc"]


def test_evidence_vergleichslauf_lag_nie_selbst_in_der_sitzung_dieser_bar():
    """Sonst stünde Zwischenstand gegen Zwischenstand."""
    for e in json.loads(EVIDENCE.read_text(encoding="utf-8"))["records"]:
        assert ins.ist_in_session_anlage(
            e["market"], e["source_run_utc"], e["bar_date"]) is False


def test_belege_verwirft_einen_vergleichslauf_der_selbst_in_der_sitzung_lag():
    """WERTE-Test auf Funktionsebene, nicht auf der erzeugten Datei.

    `test_evidence_vergleichslauf_lag_nie_selbst_in_der_sitzung_dieser_bar`
    prüft das Artefakt — eine Code-Mutation, die den Guard entfernt, bliebe
    dort unsichtbar. Hier steht die Wahl zwischen zwei Läufen derselben Bar:
    der spätere liegt NOCH in der Sitzung (11:00 New York), der frühere ist es
    nicht (Vortag 20:00). Gewinnen muss der Nicht-in-Sitzung-Lauf.
    """
    rec = {"ticker": "T", "market": "US", "first_seen_date": "2026-08-07",
           "created_utc": _utc("US", "2026-08-07 09:45:00"), "entry_close": 100.0}
    historie = [
        {"ts": _utc("US", "2026-08-07 10:00:00"), "sha": "aaa",           # in Sitzung
         "markets": {"US": {"last_bar_date": "2026-08-07",
                            "bar_date_source": "diag", "closes": {"T": 111.0}}}},
        {"ts": _utc("US", "2026-08-07 16:30:00"), "sha": "bbb",           # nach Schluss
         "markets": {"US": {"last_bar_date": "2026-08-07",
                            "bar_date_source": "diag", "closes": {"T": 105.0}}}},
        {"ts": _utc("US", "2026-08-07 17:00:00"), "sha": "ccc",           # in Sitzung? nein
         "markets": {"US": {"last_bar_date": "2026-08-07",
                            "bar_date_source": "diag", "closes": {}}}},    # ohne Ticker
    ]
    gefunden, offen = ev.belege([rec], historie)
    assert offen == []
    assert len(gefunden) == 1
    e = gefunden[0]
    assert e["source_commit"] == "bbb", "der In-Sitzung-Lauf darf nicht gewinnen"
    assert e["close_after_session"] == 105.0
    assert e["deviation_pct"] == round((100.0 - 105.0) / 105.0 * 100.0, 4)


def test_belege_nimmt_den_SPAETESTEN_gueltigen_vergleichslauf():
    """GUARDIAN-NIT: die Mutation „erster statt letzter Match gewinnt" überlebte
    meine Reihe, weil im echten Bestand nie zwei gültige Vergleichsläufe für
    dieselbe Bar konkurrieren. Hier konkurrieren sie.

    Warum der späteste: er liegt am weitesten hinter dem Sitzungsschluss, ist
    also der abgeklärteste Stand derselben Bar.
    """
    rec = {"ticker": "T", "market": "US", "first_seen_date": "2026-08-07",
           "created_utc": _utc("US", "2026-08-07 09:45:00"), "entry_close": 100.0}
    def lauf(lokal, sha, close):
        return {"ts": _utc("US", lokal), "sha": sha,
                "markets": {"US": {"last_bar_date": "2026-08-07",
                                   "bar_date_source": "diag",
                                   "closes": {"T": close}}}}
    historie = [lauf("2026-08-07 16:05:00", "frueh", 104.0),
                lauf("2026-08-07 18:00:00", "spaet", 106.0)]
    gefunden, offen = ev.belege([rec], historie)
    assert offen == [] and len(gefunden) == 1
    assert gefunden[0]["source_commit"] == "spaet"
    assert gefunden[0]["close_after_session"] == 106.0


def test_belege_verwirft_einen_vergleichslauf_dessen_lage_UNKLAR_ist():
    """GUARDIAN-NIT: die Mutation `is not False` → `is True` überlebte — sie
    ließe einen Vergleichslauf durch, dessen In-Session-Lage gar nicht
    berechenbar ist (`None`), statt ihn zu verwerfen.

    `None` heißt „wir wissen nicht, ob das ein Zwischenstand war" — und ein
    Beweisstück, das auf einem Vielleicht steht, ist keines. Hier: ein Lauf mit
    unlesbarem Zeitstempel. Er ist der EINZIGE Kandidat; wird er zu Recht
    verworfen, bleibt der Record offen.
    """
    rec = {"ticker": "T", "market": "US", "first_seen_date": "2026-08-07",
           "created_utc": _utc("US", "2026-08-07 09:45:00"), "entry_close": 100.0}
    kaputt = {"ts": "2026-08-07T99:99:99Z", "sha": "unlesbar",
              "markets": {"US": {"last_bar_date": "2026-08-07",
                                 "bar_date_source": "diag",
                                 "closes": {"T": 104.0}}}}
    assert ins.ist_in_session_anlage("US", kaputt["ts"], "2026-08-07") is None
    gefunden, offen = ev.belege([rec], [kaputt])
    assert gefunden == [], "ein Lauf unklarer Lage darf kein Beleg sein"
    assert len(offen) == 1


def test_belege_meldet_offen_wenn_es_nur_in_session_vergleiche_gibt():
    rec = {"ticker": "T", "market": "US", "first_seen_date": "2026-08-07",
           "created_utc": _utc("US", "2026-08-07 09:45:00"), "entry_close": 100.0}
    historie = [{"ts": _utc("US", "2026-08-07 10:00:00"), "sha": "aaa",
                 "markets": {"US": {"last_bar_date": "2026-08-07",
                                    "bar_date_source": "diag",
                                    "closes": {"T": 111.0}}}}]
    gefunden, offen = ev.belege([rec], historie)
    assert gefunden == [] and len(offen) == 1


def test_evidence_ist_append_only():
    alt = {"created_utc": "2026-01-01T00:00:00Z",
           "records": [{"ticker": "ALT", "created_utc": "X", "deviation_pct": 1.0}]}
    neu = [{"ticker": "ALT", "created_utc": "X", "deviation_pct": 99.0},
           {"ticker": "NEU", "created_utc": "Y", "deviation_pct": 2.0}]
    datei, dazu = ev.zusammenfuehren(alt, neu, "2026-08-07T00:00:00Z")
    assert dazu == 1
    treffer = [e for e in datei["records"] if e["ticker"] == "ALT"]
    assert treffer[0]["deviation_pct"] == 1.0, "bestehender Eintrag überschrieben"
    assert datei["created_utc"] == "2026-01-01T00:00:00Z", "Erstdatum überschrieben"


def test_evidence_geht_in_keine_berechnung_ein():
    """Weder Auswertung noch Pipeline noch Frontend lesen die Datei."""
    for rel in ("scripts/evaluate.py", "scripts/elliott_pipeline.py",
                "scripts/forward_collection.py", "scripts/health_check.py",
                "scripts/notify.py", "docs/index.html"):
        assert "in_session_evidence" not in (ROOT / rel).read_text(encoding="utf-8")


# ===========================================================================
# 8 · GRENZEN — der Marker fasst nichts an, was zählt
# ===========================================================================
def test_marker_steht_nicht_in_frozen_fields():
    import evaluate

    assert ins.MARKER not in evaluate.FROZEN_FIELDS
    assert ins.MARKER_UTC not in evaluate.FROZEN_FIELDS


def test_population_und_zaehlwerk_sind_unbeeindruckt():
    """Mit und ohne Marker dieselbe Population, dieselben Zähler."""
    import forward_collection as fc
    import evaluate

    coll_mit = _coll()
    coll_ohne = _coll()
    ins.entferne_marker(coll_ohne["records"])
    assert fc.eval_counts(coll_mit) == fc.eval_counts(coll_ohne)
    pop_mit, diag_mit = evaluate.build_population(coll_mit)
    pop_ohne, diag_ohne = evaluate.build_population(coll_ohne)
    assert len(pop_mit) == len(pop_ohne)
    assert diag_mit == diag_ohne
    assert [r.get("is_excluded") for r in coll_mit["records"]] == \
           [r.get("is_excluded") for r in coll_ohne["records"]]


def test_bestehende_marker_sind_unberuehrt():
    """`episode_split_suspect` und `stale_market_suspect` unverändert — die
    bekannten Zahlen (10 Splits, 4 Stale) stehen weiter."""
    recs = _coll()["records"]
    assert sum(1 for r in recs if r.get("episode_split_suspect")) == 10
    assert sum(1 for r in recs if r.get("stale_market_suspect")) == 4


def test_konsumenten_vertragen_das_neue_feld():
    """Jeder Leser der Sammlung arbeitet feldweise, nicht über eine
    Feld-Allowlist — ein additives Feld kann keinen von ihnen stören."""
    import forward_collection as fc
    import health_check as hc

    coll = _coll()
    assert hc.check_finite(coll, "collection") == []
    sig = hc.collection_signature(coll)
    coll_ohne = _coll()
    ins.entferne_marker(coll_ohne["records"])
    assert sig == hc.collection_signature(coll_ohne)
    assert fc.stale_markets({"markets": {}}) == {}
