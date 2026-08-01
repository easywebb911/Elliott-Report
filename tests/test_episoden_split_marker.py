"""Marker für zerschnittene Alt-Episoden — markieren, NIEMALS heilen.

Die Anschluss-Reparatur vom 01.08.2026 wirkt nur vorwärts. Die bereits
zerschnittenen Records bleiben, wie sie sind (MET/D/PRU-Prinzip); sie bekommen
additiv ``episode_split_suspect``. Diese Datei beweist:

  * der Replay findet GENAU die Fälle, die die Soll-Regel verlängert hätte,
  * über die echte Historie sind das exakt zehn, alle an Mehrfach-Lauf-Tagen,
  * an EIN-Lauf-Tagen sind alte und neue Regel identisch (Äquivalenz),
  * das Markieren ändert NUR das Marker-Feld,
  * der Rückweg stellt Byte-Identität her,
  * ``evaluate.py`` bleibt byte-identisch und unbeeindruckt.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import forward_collection as fc  # noqa: E402
import mark_episode_splits as mes  # noqa: E402

SAMMLUNG = ROOT / "data/forward_collection.json"
SPIEGEL = ROOT / "docs/data/forward_collection.json"

# Von Hand aus dem Replay abgelesen und gegen data/forward_collection.json
# (Stand 15aec42, 31.07.2026) geprüft. Reihenfolge = Lauf-Reihenfolge.
ERWARTETE_FAELLE = [
    ("HAG.DE", "2026-07-24", "HAG.DE@2026-07-24", "HAG.DE@2026-07-23"),
    ("ADS.DE", "2026-07-25", "ADS.DE@2026-07-24", "ADS.DE@2026-07-24"),
    ("MTX.DE", "2026-07-28", "MTX.DE@2026-07-28", "MTX.DE@2026-07-27"),
    ("ANET", "2026-07-28", "ANET@2026-07-28", "ANET@2026-07-23"),
    ("ADS.DE", "2026-07-29", "ADS.DE@2026-07-29", "ADS.DE@2026-07-24"),
    ("EVK.DE", "2026-07-29", "EVK.DE@2026-07-28", "EVK.DE@2026-07-28"),
    ("ADS.DE", "2026-07-30", "ADS.DE@2026-07-29", "ADS.DE@2026-07-29"),
    ("KKR", "2026-07-31", "KKR@2026-07-31", "KKR@2026-07-29"),
    ("MTX.DE", "2026-07-31", "MTX.DE@2026-07-30", "MTX.DE@2026-07-28"),
    ("G1A.DE", "2026-07-31", "G1A.DE@2026-07-30", "G1A.DE@2026-07-23"),
]


def _historie_ist_flach() -> bool:
    """Flacher Klon = die Historie fehlt, der Replay kann nichts finden.

    ``actions/checkout`` klont per Default mit ``fetch-depth: 1``. Genau daran
    sind diese Tests am 01.08.2026 in der CI gescheitert, während sie lokal
    grün waren: `git log` fand EINEN Stand, `finde_splits` lieferte [], und die
    Beweise wären stumm leer gewesen. `ci.yml` holt jetzt die volle Historie;
    dieser Wächter sorgt dafür, dass ein Rückfall als **Skip mit Grund**
    sichtbar wird und nicht als grüner Haken über nichts.
    """
    out = subprocess.run(["git", "rev-parse", "--is-shallow-repository"],
                         cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() == "true"


braucht_historie = pytest.mark.skipif(
    _historie_ist_flach(),
    reason="flacher Klon — der Replay über die committeten Stände braucht die "
           "volle Historie (ci.yml: fetch-depth: 0)")


# ---------------------------------------------------------------------------
# 1) finde_splits als reine Funktion — Soll von Hand
# ---------------------------------------------------------------------------
def _rec(ticker, created, last_seen, matured=False, first_seen="2026-07-01"):
    return {"ticker": ticker, "created_utc": created,
            "last_seen_top5_date": last_seen, "matured": matured,
            "episode_id": f"{ticker}@{first_seen}"}


def _stand(run_date, updated, *recs):
    return {"last_run_date": run_date, "updated_utc": updated,
            "records": list(recs)}


def test_finde_splits_erkennt_den_mehrfach_lauf_schnitt():
    """Drei Stände: 30.07. (X dabei), 31.07. Lauf 1 (X fehlt), 31.07. Lauf 2
    (X zurück, neuer Record). Soll: GENAU dieser eine Record ist ein Split."""
    a = _rec("X", "2026-07-30T22:45:00Z", "2026-07-30", first_seen="2026-07-30")
    b = _rec("X", "2026-07-31T22:40:00Z", "2026-07-31", first_seen="2026-07-31")
    staende = [
        _stand("2026-07-30", "2026-07-30T22:45:00Z", a),
        _stand("2026-07-31", "2026-07-31T11:16:00Z", a),
        _stand("2026-07-31", "2026-07-31T22:40:00Z", a, b),
    ]
    treffer = mes.finde_splits(staende)
    assert len(treffer) == 1
    assert treffer[0]["key"] == ("X", "2026-07-31T22:40:00Z")
    assert treffer[0]["run_date"] == "2026-07-31"
    assert treffer[0]["would_have_extended"] == "X@2026-07-30"


def test_finde_splits_meldet_eine_ECHTE_luecke_nicht():
    """X fehlt einen ganzen Kalendertag -> neue Episode ist korrekt, kein
    Split. Genau die Grenze, an der markiert werden dürfte, aber nicht darf."""
    a = _rec("X", "2026-07-29T22:40:00Z", "2026-07-29", first_seen="2026-07-29")
    b = _rec("X", "2026-07-31T22:40:00Z", "2026-07-31", first_seen="2026-07-31")
    staende = [
        _stand("2026-07-29", "2026-07-29T22:40:00Z", a),
        _stand("2026-07-30", "2026-07-30T22:45:00Z", a),      # X nicht Top-5
        _stand("2026-07-31", "2026-07-31T22:40:00Z", a, b),
    ]
    assert mes.finde_splits(staende) == []


def test_finde_splits_meldet_nicht_was_die_ALTE_regel_schon_traf():
    """Ein-Lauf-Tag: die alte Regel hätte verlängert. Dass hier trotzdem ein
    neuer Record steht, wäre eine ANDERE Ursache — nicht dieser Defekt."""
    a = _rec("X", "2026-07-30T22:45:00Z", "2026-07-30", first_seen="2026-07-30")
    b = _rec("X", "2026-07-31T22:40:00Z", "2026-07-31", first_seen="2026-07-31")
    staende = [
        _stand("2026-07-30", "2026-07-30T22:45:00Z", a),
        _stand("2026-07-31", "2026-07-31T22:40:00Z", a, b),
    ]
    assert mes.finde_splits(staende) == []


def test_finde_splits_ueberspringt_gereifte_vorgaenger():
    a = _rec("X", "2026-07-30T22:45:00Z", "2026-07-30", matured=True,
             first_seen="2026-07-30")
    b = _rec("X", "2026-07-31T22:40:00Z", "2026-07-31", first_seen="2026-07-31")
    staende = [
        _stand("2026-07-30", "2026-07-30T22:45:00Z", a),
        _stand("2026-07-31", "2026-07-31T11:16:00Z", a),
        _stand("2026-07-31", "2026-07-31T22:40:00Z", a, b),
    ]
    assert mes.finde_splits(staende) == []


def test_die_vorgaenger_wahl_ist_NIE_mehrdeutig():
    """Guardian-Fund 01.08.2026: `max(...)` zu `min(...)` in ``finde_splits``
    blieb grün. Nachgerechnet ist das ein ÄQUIVALENTER Mutant, keine Lücke —
    und genau das wird hier bewiesen statt behauptet.

    Warum: markiert wird nur ``nach_soll and not nach_alt``. Die alten Anker
    sind ``{prev_run}``, die Soll-Anker ``{run_date, prev_distinct}`` (gleicher
    Kalendertag) bzw. ``{run_date, prev_run}`` (Tageswechsel). Ein Kandidat,
    der unter die Soll-Anker fällt, aber nicht unter ``{prev_run}``, kann
    deshalb nur EIN Datum tragen:
      * gleicher Tag: ``prev_run == run_date`` -> übrig bleibt nur
        ``prev_distinct``;
      * Tageswechsel: übrig bleibt nur ``run_date`` — und vor dem ersten Lauf
        eines Tages trägt kein Record dieses Datum, die Menge ist leer.
    Also ist ``kandidaten_last_seen`` immer einelementig, und die Auswahl
    zwischen max und min existiert gar nicht.

    Der Nachbau, mit dem ich zuerst eine echte Mehrdeutigkeit erzeugen wollte,
    ergab folgerichtig KEINEN Split: der jüngere Kandidat lag unter den alten
    Ankern, die alte Regel hätte also verlängert. Er steht als Gegenprobe hier.
    """
    frueh = _rec("X", "2026-07-30T22:45:00Z", "2026-07-30", first_seen="2026-07-30")
    spaet = _rec("X", "2026-07-31T04:00:00Z", "2026-07-31", first_seen="2026-07-31")
    neu = _rec("X", "2026-07-31T22:40:00Z", "2026-07-31", first_seen="2026-07-31b")
    staende = [
        _stand("2026-07-30", "2026-07-30T22:45:00Z", frueh),
        _stand("2026-07-31", "2026-07-31T04:00:00Z", frueh, spaet),
        _stand("2026-07-31", "2026-07-31T22:40:00Z", frueh, spaet, neu),
    ]
    # Gegenprobe: kein Split, weil `spaet` schon unter die ALTEN Anker fiel.
    assert [t for t in mes.finde_splits(staende)
            if t["key"] == ("X", "2026-07-31T22:40:00Z")] == []


@braucht_historie
def test_die_vorgaenger_wahl_ist_auch_REAL_nie_mehrdeutig(echte_staende):
    """Dieselbe Eigenschaft über die 44 committeten Stände: jeder der zehn
    Treffer hat GENAU EIN Kandidaten-Datum."""
    treffer = mes.finde_splits(echte_staende)
    assert treffer, "Testvoraussetzung: es gibt Treffer"
    for t in treffer:
        assert len(t["kandidaten_last_seen"]) == 1, (
            f"{t['ticker']} am {t['run_date']}: mehrdeutige Vorgänger-Wahl "
            f"{t['kandidaten_last_seen']} — max/min wäre plötzlich eine echte "
            f"Entscheidung, dann braucht sie einen Wert-Test")


def test_der_marker_traegt_die_diagnose_NICHT():
    """`kandidaten_last_seen` ist Diagnose, kein Marker-Inhalt — sonst stünde
    ein Implementierungsdetail dauerhaft in der Sammlung."""
    coll = _unmarkierter_bestand()
    mes.setze_marker(coll, treffer_aus_erwartung(), "2026-08-01")
    for r in coll["records"]:
        if mes.MARKER in r:
            assert set(r[mes.MARKER]) == {
                "marked_date", "reason", "run_date", "would_have_extended"}


def test_record_key_haelt_kollidierende_episode_ids_auseinander():
    """ADS.DE@2026-07-24 gibt es real ZWEIMAL — episode_id taugt nicht als
    Identität, created_utc schon."""
    a = _rec("ADS.DE", "2026-07-24T14:36:19Z", "2026-07-24", first_seen="2026-07-24")
    b = _rec("ADS.DE", "2026-07-25T13:35:26Z", "2026-07-25", first_seen="2026-07-24")
    assert a["episode_id"] == b["episode_id"]
    assert mes.record_key(a) != mes.record_key(b)


# ---------------------------------------------------------------------------
# 2) Die echte Historie
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def echte_staende():
    staende = mes.committete_staende(ROOT)
    assert len(staende) >= 44, (
        f"nur {len(staende)} committete Stände gefunden — die Historie ist "
        f"unvollständig, der Replay wäre stumm")
    return staende


def treffer_aus_erwartung() -> list:
    """Die zehn Fälle OHNE Git — aus ``ERWARTETE_FAELLE`` und den Record-Keys
    des ausgelieferten Bestands.

    Damit hängen die Marker-MECHANIK-Tests (ändert nur das Marker-Feld,
    idempotent, Rückweg byte-identisch) nicht an der Git-Historie: sie prüfen
    Eigenschaften des Setzens, nicht die Herkunft der Liste. Dass die Liste
    stimmt, prüfen die Replay-Tests weiter oben — die brauchen die Historie.
    """
    coll = json.loads(SAMMLUNG.read_text(encoding="utf-8"))
    nach_ticker_lauf = {}
    for r in coll["records"]:
        m = r.get(mes.MARKER)
        if m:
            nach_ticker_lauf[(r["ticker"], m["run_date"])] = mes.record_key(r)
    treffer = []
    for ticker, run_date, neue_episode, vorgaenger in ERWARTETE_FAELLE:
        key = nach_ticker_lauf.get((ticker, run_date))
        assert key is not None, f"{ticker}/{run_date} fehlt im Bestand"
        treffer.append({"key": key, "ticker": ticker, "run_date": run_date,
                        "neue_episode": neue_episode,
                        "would_have_extended": vorgaenger,
                        "kandidaten_last_seen": ["(aus der Erwartung)"]})
    return treffer


@braucht_historie
def test_der_replay_findet_die_zehn_echten_faelle(echte_staende):
    treffer = mes.finde_splits(echte_staende)
    gefunden = [(t["ticker"], t["run_date"], t["neue_episode"],
                 t["would_have_extended"]) for t in treffer]
    assert gefunden == ERWARTETE_FAELLE


@braucht_historie
def test_jeder_gefundene_fall_liegt_wirklich_in_der_sammlung(echte_staende):
    coll = json.loads(SAMMLUNG.read_text(encoding="utf-8"))
    vorhanden = {mes.record_key(r) for r in coll["records"]}
    for t in mes.finde_splits(echte_staende):
        assert t["key"] in vorhanden, f"{t['ticker']} nicht im aktuellen Stand"


@braucht_historie
def test_die_reale_historie_hat_KEINEN_ein_lauf_tag(echte_staende):
    """Ehrlich festgehalten (01.08.2026): der Äquivalenz-Beweis „über die
    Ein-Lauf-Tage der realen Historie" wäre LEER — jeder der neun Kalendertage
    seit dem 23.07. trägt zwischen zwei und sieben Lauf-Stände.

    Den Beweis führt deshalb ``test_AEQUIVALENZ_beim_ersten_lauf_eines_tages``:
    der ERSTE Lauf eines Kalendertags IST die Ein-Lauf-Lage — dort ist
    ``prev_run_date`` das vorige Kalenderdatum, und genau dort muss alte und
    neue Regel dasselbe entscheiden. Sollte die Historie je einen echten
    Ein-Lauf-Tag bekommen, wird dieser Test rot und der Hinweis ist fällig.
    """
    lauf_daten = [s["last_run_date"] for s in echte_staende
                  if s.get("last_run_date")]
    einzeln = sorted({d for d in lauf_daten if lauf_daten.count(d) == 1})
    assert einzeln == [], (
        f"Es gibt jetzt Ein-Lauf-Tage ({einzeln}) — den Kommentar hier und in "
        f"docs/validation_registry.md nachziehen, der Beweis wird nicht-leer")


@braucht_historie
def test_AEQUIVALENZ_beim_ersten_lauf_eines_tages(echte_staende):
    """Der Fix darf normale Tage NICHT verändern — über die echte Historie.

    Für JEDEN Übergang, der der erste Lauf seines Kalendertags ist, werden
    beide Regeln über den echten Vorzustand gefahren und Ticker für Ticker
    verglichen: welcher Record würde verlängert? Alte und Soll-Anker müssen
    denselben Record liefern (oder beide keinen).

    Der strukturelle Grund: vor dem ersten Lauf eines Tages kann kein Record
    ``last_seen == run_date`` tragen — nur ein Lauf DIESES Datums setzt das.
    Der zusätzliche Anker ist damit wirkungslos. Der Test misst das, statt es
    zu behaupten.
    """
    geprueft = 0
    uebergaenge = 0
    prev = None
    prev_run = None
    for cur in echte_staende:
        run_date = cur.get("last_run_date")
        if prev is not None and run_date and prev_run and prev_run != run_date:
            uebergaenge += 1
            alt_anker = {prev_run}
            soll_anker = {run_date, prev_run}
            for ticker in {r.get("ticker") for r in prev.get("records", [])}:
                a = fc._open_episode(prev["records"], ticker, alt_anker)
                b = fc._open_episode(prev["records"], ticker, soll_anker)
                assert a is b, (
                    f"{ticker} beim ersten Lauf am {run_date}: alte Regel "
                    f"waehlt {a and a.get('episode_id')}, neue "
                    f"{b and b.get('episode_id')}")
                geprueft += 1
        if run_date:
            prev_run = run_date
        prev = cur
    # Umfang festgenagelt, damit der Beweis nicht still leerläuft (Stand
    # 01.08.2026: neun Kalendertage -> acht Erst-Lauf-Übergänge, 197 Ticker-
    # Vergleiche). Wächst mit der Historie, schrumpft nie.
    assert uebergaenge >= 8, f"nur {uebergaenge} Erst-Lauf-Übergänge"
    assert geprueft >= 197, f"nur {geprueft} Ticker-Vergleiche — Beweis zu dünn"


@braucht_historie
def test_die_vorbedingung_des_aequivalenz_beweises_gilt_real(echte_staende):
    """Kein committeter Stand trägt ein ``last_seen_top5_date`` NACH seinem
    eigenen ``last_run_date`` — sonst wäre der zusätzliche Anker nicht inert."""
    for st in echte_staende:
        run_date = st.get("last_run_date")
        if not run_date:
            continue
        for r in st.get("records", []):
            assert str(r.get("last_seen_top5_date")) <= run_date, (
                f"{r.get('ticker')}: last_seen {r.get('last_seen_top5_date')} "
                f"> last_run_date {run_date}")


# ---------------------------------------------------------------------------
# 3) Markieren ändert NUR das Marker-Feld
# ---------------------------------------------------------------------------
def _unmarkierter_bestand() -> dict:
    """Der echte Sammlungs-Stand OHNE Marker — der Ausgangspunkt jeder Probe.

    Wichtig (Guardian-Fund 01.08.2026): die ausgelieferte Datei trägt die
    Marker bereits, und der Tageslauf schreibt sie in jedem Lauf mit fort.
    Tests, die einen unmarkierten Ist-Zustand VORAUSSETZEN, sind darum
    strukturell falsch — sie waren am 01.08. rot, sobald der Marker-Lauf
    einmal gefahren war. Der Bestand wird hier deshalb aktiv normalisiert,
    nicht angenommen.
    """
    coll = json.loads(SAMMLUNG.read_text(encoding="utf-8"))
    mes.entferne_marker(coll)
    return coll


def test_marker_aendert_ausschliesslich_das_marker_feld():
    coll = _unmarkierter_bestand()
    vorher = copy.deepcopy(coll)
    treffer = treffer_aus_erwartung()
    n = mes.setze_marker(coll, treffer, "2026-08-01")
    assert n == len(ERWARTETE_FAELLE) == 10

    assert set(coll) == set(vorher), "Top-Level-Schlüssel verändert"
    assert len(coll["records"]) == len(vorher["records"])
    markiert = []
    for neu, alt in zip(coll["records"], vorher["records"]):
        diff = {k for k in set(neu) | set(alt) if neu.get(k) != alt.get(k)}
        assert diff <= {mes.MARKER}, f"{neu['ticker']}: {diff}"
        if diff:
            markiert.append((neu["ticker"], neu[mes.MARKER]["run_date"]))
    assert sorted(markiert) == sorted(
        (t, d) for t, d, _, _ in ERWARTETE_FAELLE)


def test_marker_inhalt_ist_von_hand_nachgerechnet():
    coll = _unmarkierter_bestand()
    mes.setze_marker(coll, treffer_aus_erwartung(), "2026-08-01")
    g1a = [r for r in coll["records"]
           if r["ticker"] == "G1A.DE" and mes.MARKER in r]
    assert len(g1a) == 1
    assert g1a[0][mes.MARKER] == {
        "marked_date": "2026-08-01",
        "reason": "mehrfach_lauf_tag",
        "run_date": "2026-07-31",
        "would_have_extended": "G1A.DE@2026-07-23",
    }


def test_markieren_ist_idempotent():
    coll = _unmarkierter_bestand()
    treffer = treffer_aus_erwartung()
    assert mes.setze_marker(coll, treffer, "2026-08-01") == 10
    zwischenstand = copy.deepcopy(coll)
    assert mes.setze_marker(coll, treffer, "2026-08-01") == 0
    assert coll == zwischenstand


# ---------------------------------------------------------------------------
# 4) Rückweg: Byte-Identität
# ---------------------------------------------------------------------------
def _kopiere_bestand(tmp_path: Path) -> Path:
    for rel in mes.REL_PATHS:
        ziel = tmp_path / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes((ROOT / rel).read_bytes())
    return tmp_path


def _basis_ohne_marker(tmp_path: Path) -> dict:
    """Kopiert den echten Bestand nach ``tmp_path`` und PURGT ihn einmal.

    Damit ist der Ausgangspunkt unabhängig davon, ob die ausgelieferte Datei
    die Marker schon trägt (sie tut es) — der Rückweg-Beweis darf nicht davon
    abhängen, wann er gefahren wird.
    """
    _kopiere_bestand(tmp_path)
    assert mes.main(["--path", str(tmp_path), "--purge", "--live"]) == 0
    basis = {rel: (tmp_path / rel).read_bytes() for rel in mes.REL_PATHS}
    for rel, roh in basis.items():
        assert b"episode_split_suspect" not in roh, f"{rel}: Purge unvollständig"
    return basis


def test_purge_stellt_byte_identitaet_her(tmp_path):
    """Marker setzen, dann entfernen -> BYTE-identisch zur Basis.

    Die Schreibform ist dieselbe wie in ``write_collection`` (indent=2,
    sort_keys, ensure_ascii=False, Schluss-Newline); mit sort_keys ist ein
    zusätzliches Feld eine reine Einfügung, ihr Entfernen also exakt umkehrbar.
    """
    basis = _basis_ohne_marker(tmp_path)

    assert mes.main(["--path", str(tmp_path), "--git-root", str(ROOT),
                     "--date", "2026-08-01", "--live"]) == 0
    for rel in mes.REL_PATHS:
        jetzt = (tmp_path / rel).read_bytes()
        assert jetzt != basis[rel], f"{rel}: Marker nicht geschrieben"
        assert b"episode_split_suspect" in jetzt

    assert mes.main(["--path", str(tmp_path), "--purge", "--live"]) == 0
    for rel in mes.REL_PATHS:
        assert (tmp_path / rel).read_bytes() == basis[rel], \
            f"{rel}: Rückweg nicht byte-identisch"


def test_der_ausgelieferte_bestand_traegt_die_zehn_marker():
    """Gegenstück zur Normalisierung: die eingecheckte Datei IST markiert.

    Sonst wäre der Rückweg-Test grün, ohne dass je ein Marker im Repo stünde.
    """
    coll = json.loads(SAMMLUNG.read_text(encoding="utf-8"))
    markiert = [r for r in coll["records"] if mes.MARKER in r]
    assert len(markiert) == len(ERWARTETE_FAELLE) == 10
    assert sorted((r["ticker"], r[mes.MARKER]["run_date"]) for r in markiert) \
        == sorted((t, d) for t, d, _, _ in ERWARTETE_FAELLE)
    assert SPIEGEL.read_bytes() == SAMMLUNG.read_bytes(), \
        "Spiegel und kanonische Datei laufen auseinander"


def test_dry_run_schreibt_nichts(tmp_path):
    _kopiere_bestand(tmp_path)
    original = {rel: (tmp_path / rel).read_bytes() for rel in mes.REL_PATHS}
    assert mes.main(["--path", str(tmp_path), "--git-root", str(ROOT),
                     "--date", "2026-08-01"]) == 0
    for rel in mes.REL_PATHS:
        assert (tmp_path / rel).read_bytes() == original[rel]


def test_ohne_datum_verweigert_das_programm(tmp_path):
    _kopiere_bestand(tmp_path)
    assert mes.main(["--path", str(tmp_path), "--live"]) == 2


def test_zweiter_purge_ist_ein_no_op(tmp_path):
    """Auf einem bereits gepurgten Bestand schreibt der Rückweg nichts mehr."""
    basis = _basis_ohne_marker(tmp_path)
    assert mes.main(["--path", str(tmp_path), "--purge", "--live"]) == 0
    for rel in mes.REL_PATHS:
        assert (tmp_path / rel).read_bytes() == basis[rel]


def test_entferne_marker_laesst_andere_felder_stehen():
    coll = {"records": [{"ticker": "X", "score_heuristic": 1.0,
                         mes.MARKER: {"reason": "mehrfach_lauf_tag"}},
                        {"ticker": "Y", "score_heuristic": 2.0}]}
    assert mes.entferne_marker(coll) == 1
    assert coll == {"records": [{"ticker": "X", "score_heuristic": 1.0},
                                {"ticker": "Y", "score_heuristic": 2.0}]}


# ---------------------------------------------------------------------------
# 5) Auswertung v1 bleibt eingefroren
# ---------------------------------------------------------------------------
def test_evaluate_v1_ist_byte_identisch():
    """Der Marker hat JETZT keine Zählwirkung — evaluate.py wird nicht
    angefasst. Ob/wie markierte Records später behandelt werden, ist eine
    eigene, datierte Entscheidung VOR der ersten echten Auswertung.

    Sollwert erhoben am 01.08.2026 auf `main` (15aec42), VOR diesem Zweig.
    """
    ist = hashlib.sha256((ROOT / "scripts/evaluate.py").read_bytes()).hexdigest()
    assert ist == ("bc697df91235732c6c386abe38c79a98248488b9f30a239d9c26c3cbb"
                   "3b513fc"), "evaluate.py wurde verändert — Auswertung v1 ist eingefroren"


def test_die_auswertung_v1_sieht_den_marker_NICHT():
    """Gegenprobe zur Hash-Pinnung, an der ECHTEN Population.

    ``build_population`` ist der Eingang der Auswertung. Mit und ohne Marker
    müssen Population, Ausschluss-Gründe und die Fall-Liste identisch sein —
    der Marker hat JETZT keine Zählwirkung. Ob markierte Records später
    ausgeschlossen werden, ist eine eigene datierte Entscheidung.
    """
    ev = pytest.importorskip("evaluate")
    coll = json.loads(SAMMLUNG.read_text(encoding="utf-8"))
    faelle_ohne, diag_ohne = ev.build_population(coll)

    mes.setze_marker(coll, treffer_aus_erwartung(), "2026-08-01")
    faelle_mit, diag_mit = ev.build_population(coll)

    assert diag_ohne == diag_mit
    assert len(faelle_ohne) == len(faelle_mit)
    assert [tuple(f) for f in faelle_ohne] == [tuple(f) for f in faelle_mit]


def test_evaluate_py_wird_von_diesem_zweig_nicht_angefasst():
    """Zweite, unabhängige Sicherung: git sagt, die Datei ist unverändert."""
    geaendert = subprocess.run(
        ["git", "diff", "--name-only", "origin/main", "--", "scripts/evaluate.py"],
        cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert geaendert == "", f"evaluate.py steht im Diff: {geaendert!r}"
