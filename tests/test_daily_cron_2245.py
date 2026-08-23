"""Cron-Verschiebung daily.yml: 21:45 -> 22:45 UTC (22.08.2026).

ANLASS (bereits belegt in #97, hier nur Referenz): die source_timing_probe-
Rohdaten (data/source_timing_probe.jsonl, 100 Zeilen) zeigen einen DE-Rückzug
(``last_bar_date`` fällt bei einem späteren Lauf desselben Tages auf ein
früheres Datum zurück) an 5 von 10 Tagen, jeweils zwischen dem 4. und 5.
Tageslauf — gedeckt durch den Live-Vorfall vom 21./22.08.2026
(health_check-Warnung „DE: Kurse 1 Handelstag zurück — erwartet 2026-08-20,
tatsächlich 2026-08-19"). US zeigt den Rückzug an KEINEM der 100 Datenpunkte.
Erster vollständiger Tagesbar-Datenpunkt (10/10 Ticker) für BEIDE Märkte:
Min 19:36, Median 19:54, Max 20:04 UTC — eine Stunde später (22:45 UTC) liegt
selbst mit dem größten gemessenen Startverzug (~54 Min., Woche 1) sicher
danach.

REINE ZEITVERSCHIEBUNG — keine Retry-/Wartelogik, keine Änderung an
health_check-Schwellenwerten/Marker-Definitionen, keine Änderung an der
wöchentlichen Wartungs-Cron (Mo 06:30 UTC) oder am Staleness-Cron (täglich
06:00 UTC) selbst.

ZWEI NETZE (Muster aus test_waehrungssymbole.py/test_beobachtungszone_
umbenennung.py):
  (a) Von-Hand-dekodierter Cron-Soll-Wert (nicht nur „Datei geändert").
  (b) Konsumenten-Anker — alle Stellen, die von der 21:45-UTC-Annahme
      abhingen, zeigen jetzt konsistent 22:45; die GRENZEN-Ausnahme
      validation_registry.md bleibt bewusst unangetastet — mit Gegenprobe,
      damit ein stiller Umbau dort auffiele.

NACHTRAG (23.08.2026, separater Löschauftrag): die ZWEITE GRENZEN-Ausnahme
dieser Datei — `source_timing_probe.py`/dessen Workflow-Datei/die
`.jsonl`-Rohdaten — war zum Zeitpunkt DIESES PRs (#98/#99) bewusst
unangetastet, WEIL die Sonde damals noch lief bzw. gerade erst abgeschaltet
hatte. Der geplante Löschweg (im Workflow-Kopf und in
`docs/validation_registry.md` selbst als „separater, noch offener Schritt"
angekündigt) ist inzwischen in einem eigenen, späteren PR gegangen worden —
die Datei existiert nicht mehr. Die zugehörige Gegenprobe unten
(`test_source_timing_probe_workflow_bewusst_unangetastet`) prüfte GENAU
DIESE Nicht-Existenz-Grenze; sie ist durch die tatsächliche Löschung erfüllt
und wurde durch eine Bestätigung ihrer Abwesenheit ersetzt (siehe dort).
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DAILY = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
MAINTENANCE = (ROOT / ".github/workflows/maintenance.yml").read_text(encoding="utf-8")
STALENESS = (ROOT / ".github/workflows/staleness_check.yml").read_text(encoding="utf-8")
HTML = (ROOT / "docs/index.html").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
CALENDAR_SRC = (ROOT / "scripts/market_calendar.py").read_text(encoding="utf-8")
REGISTRY = (ROOT / "docs/validation_registry.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (a) Von-Hand-dekodierter Cron-Soll-Wert
# ---------------------------------------------------------------------------
def test_cron_wert_von_hand_dekodiert():
    zeile = next(z for z in DAILY.splitlines() if "cron:" in z and "45" in z)
    roh = zeile.split('cron:', 1)[1].strip().strip('"')
    minute, stunde, tag, monat, wochentag = roh.split()
    assert minute == "45", "Minute muss unverändert 45 bleiben (nur Stunde verschiebt sich)"
    assert stunde == "22", "Stunde muss auf 22 UTC verschoben sein (vorher 21)"
    assert (tag, monat, wochentag) == ("*", "*", "1-5"), \
        "nur Werktage Mo-Fr, Tag/Monat unverändert '*'"


def test_cron_string_exakt():
    assert 'cron: "45 22 * * 1-5"' in DAILY
    assert 'cron: "45 21 * * 1-5"' not in DAILY
    assert DAILY.count("- cron:") == 1, "genau ein Cron-Eintrag, kein zweiter dazugekommen"


# ---------------------------------------------------------------------------
# (b) Konsumenten — müssen konsistent mitgezogen sein
# ---------------------------------------------------------------------------
def test_market_calendar_run_hour_verschoben():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import market_calendar as cal  # noqa: E402

    assert cal.RUN_HOUR == 22, "RUN_HOUR muss die neue Cron-Stunde spiegeln"
    assert cal.RUN_MIN == 45, "RUN_MIN bleibt unverändert (nur die Stunde verschiebt sich)"
    # GRACE_HOURS/TOLERANCE_HOURS bewusst NICHT angefasst (GRENZEN: reine
    # Zeitverschiebung, keine neue Warte-/Retry-Logik).
    assert cal.GRACE_HOURS == 6
    assert cal.TOLERANCE_HOURS == 6


def test_market_calendar_kommentar_nennt_die_neue_cron_zeit():
    assert '"45 22 * * 1-5"' in CALENDAR_SRC
    assert '"45 21 * * 1-5"' not in CALENDAR_SRC


def test_frontend_spiegel_zeigt_dieselbe_uhrzeit():
    """docs/index.html:_lastExpectedRun ist laut eigenem Kommentar ein
    ``Spiegel von scripts/market_calendar.py`` (Zeile ~1297) — beide Stellen
    MÜSSEN bei einer Cron-Änderung zusammen gepflegt werden."""
    start = HTML.index("function _lastExpectedRun(")
    ende = HTML.index("\n    }", start)
    koerper = HTML[start:ende]
    assert "now.getUTCDate(), 22, 45, 0));" in koerper
    assert "21, 45, 0" not in koerper


def test_readme_nennt_die_neue_cron_zeit():
    assert "Cron 22:45 UTC" in README
    assert "läuft täglich **22:45 UTC**" in README
    assert "21:45" not in README, "README darf die alte Uhrzeit nirgends mehr nennen"


def test_maintenance_und_staleness_kommentare_konsistent():
    """Reine Kommentar-Konsistenz — die tatsächlichen Cron-Werte dieser beiden
    Workflows (Mo 06:30 UTC bzw. täglich 06:00 UTC) sind laut GRENZEN NICHT
    Teil dieses Auftrags und bleiben unverändert; nur die Referenz auf die
    daily.yml-Zeit in ihren Kommentaren wird nachgezogen."""
    assert "vom Tageslauf (22:45, seit 22.08.2026)" in MAINTENANCE
    assert 'cron: "30 6 * * 1"' in MAINTENANCE, "Wartungs-Cron selbst bleibt GRENZEN-konform unangetastet"

    assert "22:45 UTC, seit 22.08.2026) ist dann ~7 h alt" in STALENESS
    assert "-> ~31 h -> Push" in STALENESS
    assert 'cron: "0 6 * * *"' in STALENESS, "Staleness-Cron selbst bleibt GRENZEN-konform unangetastet"


# ---------------------------------------------------------------------------
# Gegenprobe: die verbleibende bewusste GRENZEN-Ausnahme bleibt unangetastet
# ---------------------------------------------------------------------------
def test_source_timing_probe_workflow_ist_jetzt_geloescht():
    """Ersetzt `test_source_timing_probe_workflow_bewusst_unangetastet`
    (Stand PR #98/#99: die Sonden-Workflow-Datei sollte NICHT angefasst
    werden, solange sie noch existierte). Seit dem separaten Löschauftrag
    vom 23.08.2026 existiert die Datei gar nicht mehr — die alte
    Gegenprobe (Inhalt zeigt weiterhin '21:45 UTC') ist damit gegenstandslos.
    Neue Gegenprobe: die Datei ist wirklich weg, kein stiller Teil-Rückbau."""
    assert not (ROOT / ".github/workflows/source_timing_probe.yml").exists()


def test_validation_registry_bewusst_unangetastet():
    """GRENZEN dieses Auftrags: 'validation_registry.md-Regeln: nicht
    anfassen'. Die Datei enthält mehrere Stellen, die von der 21:45-UTC-
    Annahme abhängen (u. a. eine ET/MEZ-Umrechnung) — bewusst NICHT
    nachgezogen, im PR-Text als Widerspruch gemeldet (SESSION_HANDOVER.md
    hatte notiert, die Entscheidung gehöre in die Registry; die explizite
    GRENZEN-Vorgabe dieses Auftrags hat Vorrang)."""
    assert "45 21 * * 1-5" in REGISTRY, \
        "die Registry muss den ALTEN Cron-Wortlaut unverändert behalten (GRENZEN)"
    # HINWEIS: „22:45" kommt an EINER Stelle bereits vor (Zeile ~1060,
    # „21:45 UTC = 16:45 ET / 22:45 MEZ" — die Zeitzonen-Umrechnung DER ALTEN
    # Zeit, zufällig derselbe Zahlenwert). Das ist KEIN Hinweis auf eine
    # bereits nachgezogene Änderung, deshalb hier bewusst nicht geprüft.
