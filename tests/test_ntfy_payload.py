"""ntfy-Weiterleitung (Easy-Entscheid 30.10.2026, Auftrag 4 von 6) —
`scripts/ntfy_payload.py`: Umgebungsvariablen -> sicheres JSON-Payload
für ntfys JSON-Publish-API.

SICHERHEITSZIEL (wörtlich): kein Eingabetext kann Befehle ausführen oder
Header manipulieren, nichts Vertrauliches landet im Protokoll. Da das
Ergebnis IMMER über `json.dumps` entsteht (nie String-Konkatenation),
ist jeder Wert automatisch JSON-sicher escaped — die Tests hier prüfen
zusätzlich die EXPLIZIT geforderten Filter (Steuerzeichen, Länge,
Tag-Zeichensatz, Priorität, leere message) UND belegen per
Round-Trip (`json.dumps`/`json.loads`), dass harmlose Sonderzeichen
(Shell-Metazeichen, Anführungszeichen) unverändert als DATEN ankommen,
nicht als Code ausgeführt werden.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ntfy_payload as np  # noqa: E402


# ---------------------------------------------------------------------------
# title
# ---------------------------------------------------------------------------
def test_title_entfernt_cr_lf():
    assert np.sanitize_title("Zeile1\r\nZeile2") == "Zeile1Zeile2"


def test_title_entfernt_sonstige_steuerzeichen():
    assert np.sanitize_title("A\x00B\x07C\x1bD\x7fE") == "ABCDE"


def test_title_kuerzt_auf_100_zeichen():
    lang = "x" * 250
    ergebnis = np.sanitize_title(lang)
    assert len(ergebnis) == 100
    assert ergebnis == "x" * 100


def test_title_behaelt_emoji_und_umlaute():
    assert np.sanitize_title("Ünö äöü 😀 Meldung") == "Ünö äöü 😀 Meldung"


def test_title_behaelt_shell_metazeichen_als_reine_daten():
    """Anführungszeichen/Backticks/$(...) sind NICHT verboten — sie werden
    nie an eine Shell gereicht (nur ins JSON), bleiben also harmlos."""
    roh = '$(whoami) `id` "; rm -rf / #'
    assert np.sanitize_title(roh) == roh


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------
def test_tags_nur_erlaubte_zeichen():
    assert np.sanitize_tags("Alert!,foo_bar,a-b-c,x y z") == [
        "lert", "foo_bar", "a-b-c", "xyz"]


def test_tags_hoechstens_fuenf():
    roh = ",".join(f"t{i}" for i in range(10))
    assert np.sanitize_tags(roh) == ["t0", "t1", "t2", "t3", "t4"]


def test_tags_leere_eingabe_ergibt_leere_liste():
    assert np.sanitize_tags("") == []


def test_tags_entfernt_steuerzeichen_vor_dem_filtern():
    assert np.sanitize_tags("a\r\nb,c\x00d") == ["ab", "cd"]


def test_tags_injektionsversuch_wird_auf_erlaubte_zeichen_reduziert():
    """Grossbuchstaben sind NICHT im erlaubten Zeichensatz [a-z0-9_,-] und
    werden verworfen wie jedes andere unerlaubte Zeichen (keine
    Gross-/Kleinschreibungs-Normalisierung, strikt wie im Auftrag
    beschrieben) — ein rein grossgeschriebener Tag wird dadurch leer und
    damit ganz verworfen."""
    assert np.sanitize_tags('$(rm -rf /),`id`,"; DROP TABLE') == ["rm-rf", "id"]


def test_tags_leere_zwischentags_werden_uebersprungen():
    assert np.sanitize_tags("a,,,b") == ["a", "b"]


# ---------------------------------------------------------------------------
# priority
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("roh,erwartet", [
    ("1", 1), ("3", 3), ("5", 5),
    ("0", 3), ("6", 3), ("-1", 3), ("100", 3),
    ("", 3), ("abc", 3), ("3.0", 3), (" 4 ", 4), ("$(id)", 3),
])
def test_priority_nur_1_bis_5_sonst_3(roh, erwartet):
    assert np.sanitize_priority(roh) == erwartet


# ---------------------------------------------------------------------------
# message
# ---------------------------------------------------------------------------
def test_message_leer_wirft_fehler():
    with pytest.raises(np.NtfyPayloadFehler):
        np.sanitize_message("")


def test_message_nur_whitespace_wirft_fehler():
    with pytest.raises(np.NtfyPayloadFehler):
        np.sanitize_message("   \n\t  ")


def test_message_kurz_bleibt_unveraendert():
    assert np.sanitize_message("Alles gut.") == "Alles gut."


def test_message_behaelt_emoji_und_umlaute():
    text = "Lauf fertig ✅ — Ünö äöü 😀"
    assert np.sanitize_message(text) == text


def test_message_ueberlaenge_wird_gekuerzt_mit_hinweis():
    lang = "a" * 5000
    ergebnis = np.sanitize_message(lang)
    assert len(ergebnis.encode("utf-8")) <= np.MESSAGE_MAX_BYTES
    assert ergebnis.endswith("[gekürzt]")


def test_message_ueberlaenge_utf8_grenze_mitten_in_mehrbyte_zeichen():
    """Konstruiert eine Nachricht, deren naive Byte-Kürzung mitten in einem
    Mehrbyte-UTF-8-Zeichen landen würde (2-Byte-Zeichen 'π' am Ende einer
    ASCII-Strecke knapp vor der Grenze) — das Ergebnis MUSS trotzdem
    gültiges UTF-8 bleiben (kein UnicodeDecodeError, keine Ersatzzeichen)."""
    fuellung = "a" * (np.MESSAGE_MAX_BYTES - 5)
    lang = fuellung + ("π" * 20)  # 2-Byte-Zeichen, Grenze trifft garantiert eines mittig
    ergebnis = np.sanitize_message(lang)
    # Muss ohne Fehler decodierbar sein (sonst waere sanitize_message selbst
    # schon mit UnicodeDecodeError gescheitert) und innerhalb des Limits bleiben.
    assert len(ergebnis.encode("utf-8")) <= np.MESSAGE_MAX_BYTES
    assert ergebnis.endswith("[gekürzt]")
    # Kein kaputtes/halbes Zeichen vor dem Hinweis:
    vor_hinweis = ergebnis[: -len("[gekürzt]")]
    assert vor_hinweis.encode("utf-8").decode("utf-8") == vor_hinweis


def test_message_ueberlaenge_mit_vierbyte_emoji_an_der_grenze():
    fuellung = "b" * (np.MESSAGE_MAX_BYTES - 3)
    lang = fuellung + ("😀" * 10)  # 4-Byte-Zeichen
    ergebnis = np.sanitize_message(lang)
    assert len(ergebnis.encode("utf-8")) <= np.MESSAGE_MAX_BYTES
    ergebnis.encode("utf-8").decode("utf-8")  # wirft nicht


def test_message_injektionsversuch_bleibt_unveraendert_als_daten():
    roh = 'Lauf OK\nZeile2 $(whoami) `id` "; rm -rf /'
    assert np.sanitize_message(roh) == roh


# ---------------------------------------------------------------------------
# build_payload / JSON-Sicherheit (Round-Trip)
# ---------------------------------------------------------------------------
def test_build_payload_struktur():
    payload = np.build_payload("mein-topic", "Titel", "Nachricht", "a,b", "4")
    assert payload == {
        "topic": "mein-topic", "title": "Titel", "message": "Nachricht",
        "tags": ["a", "b"], "priority": 4,
    }


def test_build_payload_leere_message_wirft_fehler():
    with pytest.raises(np.NtfyPayloadFehler):
        np.build_payload("t", "Titel", "", "", "3")


def test_build_payload_json_roundtrip_erhaelt_injektionsversuche_als_daten():
    """`json.dumps` escaped automatisch — ein Angreifer kann damit weder das
    JSON-Dokument aufbrechen noch Code ausführen. Belegt per Round-Trip."""
    boese_titel = 'Titel" , "evil": "true'
    boese_message = 'Zeile1\nZeile2 $(id) `whoami` \\ "quote"'
    payload = np.build_payload("t", boese_titel, boese_message, "", "3")
    text = json.dumps(payload)
    zurueck = json.loads(text)
    assert zurueck["title"] == np.sanitize_title(boese_titel)
    assert zurueck["message"] == boese_message
    # Es gibt kein zusaetzliches "evil"-Feld - der Versuch, das JSON zu
    # erweitern, landete nur als Textinhalt des title-Feldes.
    assert set(zurueck.keys()) == {"topic", "title", "message", "tags", "priority"}


def test_build_payload_topic_wird_nie_durch_sanitizer_veraendert():
    """Topic kommt aus dem Secret, nicht aus Nutzereingaben — wird 1:1
    übernommen (kein Filtern eines Werts, den Easy selbst kontrolliert)."""
    payload = np.build_payload("  exotisch!Topic_123  ", "T", "M", "", "3")
    assert payload["topic"] == "  exotisch!Topic_123  "


# ---------------------------------------------------------------------------
# Datei-/CLI-Weg (ohne Netzzugriff)
# ---------------------------------------------------------------------------
def test_schreibe_payload_datei_schreibt_gueltiges_json(tmp_path):
    payload = np.build_payload("t", "Titel", "Nachricht", "a,b", "2")
    pfad = np.schreibe_payload_datei(payload)
    try:
        inhalt = json.loads(Path(pfad).read_text(encoding="utf-8"))
        assert inhalt == payload
    finally:
        Path(pfad).unlink(missing_ok=True)


def test_main_ohne_topic_bricht_ab_ohne_dateiausgabe(monkeypatch, capsys):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    monkeypatch.setenv("NTFY_IN_MESSAGE", "Testnachricht")
    code = np.main()
    out = capsys.readouterr()
    assert code == 1
    assert out.out == ""  # keine Datei-Pfad-Zeile -> kein Erfolg behauptet


def test_main_leere_message_bricht_ab_ohne_eingabe_im_fehlertext(monkeypatch, capsys):
    monkeypatch.setenv("NTFY_TOPIC", "mein-topic")
    monkeypatch.setenv("NTFY_IN_MESSAGE", "")
    code = np.main()
    out = capsys.readouterr()
    assert code == 1
    assert out.out == ""
    assert "mein-topic" not in out.err  # Secret-Wert nie im Fehlertext


def test_main_erfolg_schreibt_nur_den_dateipfad(monkeypatch, capsys):
    monkeypatch.setenv("NTFY_TOPIC", "mein-topic")
    monkeypatch.setenv("NTFY_IN_TITLE", "Titel")
    monkeypatch.setenv("NTFY_IN_MESSAGE", "Testnachricht")
    monkeypatch.setenv("NTFY_IN_TAGS", "info")
    monkeypatch.setenv("NTFY_IN_PRIORITY", "4")
    code = np.main()
    out = capsys.readouterr()
    assert code == 0
    pfad = out.out.strip()
    assert "mein-topic" not in out.out  # Topic nie ausgegeben
    try:
        inhalt = json.loads(Path(pfad).read_text(encoding="utf-8"))
        assert inhalt["topic"] == "mein-topic"
        assert inhalt["title"] == "Titel"
        assert inhalt["priority"] == 4
    finally:
        Path(pfad).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Mutationsproben (ohne Produktionscode zu verändern) — belegen, dass die
# jeweilige Prüfung oben NICHT vacuous ist: die "kaputte" Variante (ohne
# den Filter) würde eine andere, falsche Antwort liefern.
# ---------------------------------------------------------------------------
def test_mutationsprobe_steuerzeichen_filter_entfernt_waere_title_kaputt():
    roh = "Zeile1\r\nZeile2"
    ohne_filter = roh[:np.TITLE_MAX_ZEICHEN]  # Mutation: kein _ohne_steuerzeichen
    assert ohne_filter != np.sanitize_title(roh)
    assert "\r" in ohne_filter and "\n" in ohne_filter
    assert "\r" not in np.sanitize_title(roh) and "\n" not in np.sanitize_title(roh)


def test_mutationsprobe_laengenkuerzung_entfernt_waere_title_zu_lang():
    lang = "x" * 250
    ohne_kuerzung = lang  # Mutation: kein [:TITLE_MAX_ZEICHEN]
    assert len(ohne_kuerzung) != len(np.sanitize_title(lang))
    assert len(np.sanitize_title(lang)) == np.TITLE_MAX_ZEICHEN


def test_mutationsprobe_message_laengenkuerzung_entfernt_waere_zu_lang():
    lang = "a" * 5000
    ohne_kuerzung_bytes = len(lang.encode("utf-8"))  # Mutation: keine Kürzung
    assert ohne_kuerzung_bytes > np.MESSAGE_MAX_BYTES
    assert len(np.sanitize_message(lang).encode("utf-8")) <= np.MESSAGE_MAX_BYTES


def test_mutationsprobe_tag_zeichensatz_filter_entfernt_waere_injektion_durch():
    roh = "$(rm -rf /)"
    ohne_filter = [t.strip() for t in roh.split(",") if t.strip()]  # Mutation: kein Zeichensatz-Filter
    assert ohne_filter != np.sanitize_tags(roh)
    assert "$(rm -rf /)" in ohne_filter
    assert "$(rm -rf /)" not in np.sanitize_tags(roh)


def test_mutationsprobe_priority_bereichspruefung_entfernt_waere_ungueltig_durch():
    roh = "999"
    ohne_pruefung = int(roh)  # Mutation: kein 1..5-Bereichscheck
    assert ohne_pruefung != np.sanitize_priority(roh)
    assert np.sanitize_priority(roh) == 3
