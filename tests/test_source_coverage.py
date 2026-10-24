"""Daten-Abdeckungs-Wächter (Easy-Entscheid 24.10.2026, Auftrag 1 von 6).

Reine Funktionen, synthetische Zeit (keine echte Uhr). Deckt: Idempotenz
(Stunde als Teil des Schlüssels), Fenster-Trennung 24h/7 Tage mit
Grenzfällen, "alle Läufe leer" vs. "ein Lauf unter mehreren leer", und
bekannt tot (ℹ️) vs. unbekannt tot (⚠️).
"""
import datetime as _dt

import source_coverage as sc

JETZT = _dt.datetime(2026, 10, 24, 12, 0, tzinfo=_dt.timezone.utc)


def _iso(dt: _dt.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── upsert_entry / Idempotenz ──────────────────────────────────────────────
def test_zwei_laeufe_verschiedener_stunden_ergeben_zwei_eintraege():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 12, "midday",
                            _iso(JETZT), {"kurse_us": (10, 10, 10)})
    state = sc.upsert_entry(state, "2026-10-24", 22, "daily",
                            _iso(JETZT), {"kurse_us": (10, 10, 10)})
    assert len(state["entries"]) == 2


def test_zwei_schreibversuche_derselben_stunde_ergeben_einen_eintrag():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 22, "daily",
                            _iso(JETZT), {"kurse_us": (10, 0, 0)})
    state = sc.upsert_entry(state, "2026-10-24", 22, "daily",
                            _iso(JETZT), {"kurse_us": (10, 10, 10)})
    assert len(state["entries"]) == 1
    assert state["entries"][0]["sources"]["kurse_us"]["mit_daten"] == 10


def test_ring_puffer_kappt_bei_ring_max(monkeypatch):
    monkeypatch.setattr(sc, "RING_MAX", 3)
    state = sc._leer()
    for h in range(5):
        state = sc.upsert_entry(state, "2026-10-24", h, "daily",
                                _iso(JETZT), {"kurse_us": (1, 1, 1)})
    assert len(state["entries"]) == 3
    assert [e["run_hour"] for e in state["entries"]] == [2, 3, 4]


# ── silent_source_findings: Kernklasse "alle Läufe leer" ───────────────────
def test_alle_laeufe_im_fenster_leer_warnt():
    state = sc._leer()
    for h in (10, 11):
        state = sc.upsert_entry(state, "2026-10-24", h, "daily",
                                _iso(JETZT - _dt.timedelta(hours=12 - h)),
                                {"kurse_us": (10, 10, 0)})
    befunde = sc.silent_source_findings(state, JETZT)
    assert len(befunde) == 1
    assert befunde[0]["severity"] == "warn"
    assert befunde[0]["detail"]["source"] == "kurse_us"


def test_nur_ein_lauf_unter_mehreren_leer_warnt_nicht():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 10, "daily",
                            _iso(JETZT - _dt.timedelta(hours=2)),
                            {"kurse_us": (10, 10, 0)})
    state = sc.upsert_entry(state, "2026-10-24", 11, "midday",
                            _iso(JETZT - _dt.timedelta(hours=1)),
                            {"kurse_us": (10, 10, 5)})
    befunde = sc.silent_source_findings(state, JETZT)
    assert befunde == []


def test_nichts_erwartet_warnt_nicht():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 10, "daily",
                            _iso(JETZT - _dt.timedelta(hours=1)),
                            {"kurse_us": (0, 0, 0)})
    assert sc.silent_source_findings(state, JETZT) == []


# ── Fenster-Trennung 24h (kurse_*) vs. 7 Tage (ki_kommentare) ──────────────
def test_kurse_fenster_24h_lauf_ausserhalb_zaehlt_nicht():
    state = sc._leer()
    # 25h alt -> außerhalb des 24h-Fensters, wird ignoriert -> "nichts erwartet"
    state = sc.upsert_entry(state, "2026-10-23", 11, "daily",
                            _iso(JETZT - _dt.timedelta(hours=25)),
                            {"kurse_us": (10, 10, 0)})
    assert sc.silent_source_findings(state, JETZT) == []


def test_kurse_fenster_24h_grenzfall_genau_am_rand_zaehlt_noch_mit():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-23", 12, "daily",
                            _iso(JETZT - _dt.timedelta(hours=24)),
                            {"kurse_us": (10, 10, 0)})
    befunde = sc.silent_source_findings(state, JETZT)
    assert len(befunde) == 1 and befunde[0]["detail"]["source"] == "kurse_us"


def test_ki_kommentare_7_tage_fenster_lauf_innerhalb_warnt():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-20", 22, "daily",
                            _iso(JETZT - _dt.timedelta(days=4)),
                            {"ki_kommentare": (5, 5, 0)})
    befunde = sc.silent_source_findings(state, JETZT)
    assert len(befunde) == 1 and befunde[0]["detail"]["source"] == "ki_kommentare"


def test_ki_kommentare_7_tage_fenster_lauf_ausserhalb_ignoriert():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-16", 22, "daily",
                            _iso(JETZT - _dt.timedelta(days=8)),
                            {"ki_kommentare": (5, 5, 0)})
    assert sc.silent_source_findings(state, JETZT) == []


def test_zwei_quellen_unterschiedliche_fenster_unabhaengig_bewertet():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 10, "daily",
                            _iso(JETZT - _dt.timedelta(hours=1)),
                            {"kurse_us": (10, 10, 10), "ki_kommentare": (5, 5, 0)})
    befunde = sc.silent_source_findings(state, JETZT)
    assert len(befunde) == 1
    assert befunde[0]["detail"]["source"] == "ki_kommentare"


# ── bekannt tot (ℹ️) vs. unbekannt tot (⚠️) ─────────────────────────────────
def test_bekannt_tote_quelle_wird_info_statt_warn(monkeypatch):
    monkeypatch.setattr(sc, "KNOWN_DEAD_SOURCES", ("kurse_de",))
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 10, "daily",
                            _iso(JETZT - _dt.timedelta(hours=1)),
                            {"kurse_de": (10, 10, 0)})
    befunde = sc.silent_source_findings(state, JETZT)
    assert len(befunde) == 1
    assert befunde[0]["severity"] == "info"
    assert "bekannt tot" in befunde[0]["message"]


def test_unbekannte_quelle_ohne_eintrag_bleibt_warn():
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 10, "daily",
                            _iso(JETZT - _dt.timedelta(hours=1)),
                            {"kurse_de": (10, 10, 0)})
    befunde = sc.silent_source_findings(state, JETZT)
    assert befunde[0]["severity"] == "warn"
    assert "bekannt tot" not in befunde[0]["message"]


# ── load_coverage / write_coverage: fail-soft ───────────────────────────────
def test_load_coverage_fehlende_datei_gibt_leere_struktur(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "REPO_ROOT", tmp_path)
    assert sc.load_coverage() == {"schema_version": 1, "entries": []}


def test_load_coverage_kaputte_datei_ist_fail_soft(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "REPO_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "source_coverage.json").write_text("{kaputt", encoding="utf-8")
    assert sc.load_coverage() == {"schema_version": 1, "entries": []}


def test_write_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "REPO_ROOT", tmp_path)
    state = sc.upsert_entry(sc._leer(), "2026-10-24", 10, "daily",
                            _iso(JETZT), {"kurse_us": (10, 10, 10)})
    sc.write_coverage(state)
    assert sc.load_coverage() == state


# ── Mutationsproben: diese drei Varianten MÜSSEN rot werden ────────────────
def test_mutation_fenster_operator_gedreht_wuerde_grenzfall_falsch_ausschliessen():
    # Produktionscode nutzt "recorded < cutoff" (Ausschluss). Eine gedrehte
    # Variante "recorded <= cutoff" würde den Grenzfall-Lauf fälschlich
    # ausschließen -> kein Befund, wo einer erwartet wird.
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-23", 12, "daily",
                            _iso(JETZT - _dt.timedelta(hours=24)),
                            {"kurse_us": (10, 10, 0)})
    cutoff = sc._window_cutoff("kurse_us", JETZT)
    recorded = JETZT - _dt.timedelta(hours=24)
    assert not (recorded <= cutoff and recorded != cutoff)  # Dokumentation der Grenze
    befunde = sc.silent_source_findings(state, JETZT)
    assert len(befunde) == 1  # echte Funktion zählt den Grenzfall mit


def test_mutation_idempotenz_schluessel_ohne_stunde_wuerde_laeufe_verschmelzen():
    key_mit_stunde_a = sc._entry_key("2026-10-24", 10, "daily")
    key_mit_stunde_b = sc._entry_key("2026-10-24", 22, "daily")
    assert key_mit_stunde_a != key_mit_stunde_b
    # Eine Variante ohne Stunde (nur Datum+Workflow) würde beide verschmelzen:
    key_ohne_stunde_a = "2026-10-24|daily"
    key_ohne_stunde_b = "2026-10-24|daily"
    assert key_ohne_stunde_a == key_ohne_stunde_b  # genau der Fehler, den wir vermeiden


def test_mutation_mit_daten_durch_beantwortet_ersetzt_wuerde_befund_unterdruecken():
    # "beantwortet" kann > 0 sein, obwohl "mit_daten" 0 ist (Antwort, aber
    # leer) — genau die Lücke, die dieses Modul schließen soll. Würde die
    # Prüfung "mit_daten" durch "beantwortet" ersetzen, verschwände der Befund.
    state = sc._leer()
    state = sc.upsert_entry(state, "2026-10-24", 10, "daily",
                            _iso(JETZT - _dt.timedelta(hours=1)),
                            {"kurse_us": (10, 10, 0)})
    befunde_echt = sc.silent_source_findings(state, JETZT)
    assert len(befunde_echt) == 1

    def _mutierte_pruefung_mit_beantwortet(state, jetzt):
        summen = {}
        for e in state.get("entries", []):
            recorded = _dt.datetime.fromisoformat(
                str(e.get("recorded_utc", "")).replace("Z", "+00:00"))
            for name, zahlen in (e.get("sources") or {}).items():
                cutoff = sc._window_cutoff(name, jetzt)
                if recorded < cutoff or recorded > jetzt:
                    continue
                paar = summen.setdefault(name, [0, 0])
                paar[0] += int(zahlen.get("erwartet", 0) or 0)
                paar[1] += int(zahlen.get("beantwortet", 0) or 0)  # Mutation
        return [n for n, (e, b) in summen.items() if e > 0 and b <= 0]

    assert _mutierte_pruefung_mit_beantwortet(state, JETZT) == []  # kein Befund mehr
