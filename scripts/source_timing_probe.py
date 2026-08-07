"""WEGWERF-MESSUNG: wann liefert die Quelle je Markt einen brauchbaren Tag?

ZWECK (06.08.2026, befristet bis PROBE_END_DATE): Zwei Fragen sind aus der
committeten Lauf-Historie **nicht** beantwortbar, weil dort schlicht keine Läufe
zu den entscheidenden Uhrzeiten liegen:

  1. **DE-Rückzugsgrenze.** Bei 21:29 UTC war DE sauber, bei 22:38 UTC waren
     116 von 117 Tickern um ihre letzte Zeile gebracht. Dazwischen gibt es
     keinen einzigen Lauf — die Grenze ist auf 69 Minuten unbestimmt.
  2. **US-Nachlauf nach Börsenschluss.** Ein *fertiger* US-Tag ist frühestens
     31 Minuten nach Schluss belegt (Lauf 20:31 bei Schluss 20:00). Ob die
     Quelle schon nach 10 Minuten so weit ist, weiß niemand.

Beides entscheidet, ob es eine Tageslauf-Zeit gibt, zu der **beide** Märkte
einen fertigen Handelstag tragen — im Sommer **und** im Winter, wo der
NYSE-Schluss in UTC eine Stunde später liegt.

DIESE DATEI MISST NUR. Sie rechnet nichts, sie veröffentlicht nichts, sie
schreibt ausschließlich nach ``PROBE_PATH``. Report, Sammlung, Health-Zustand
und ``docs/`` bleiben unberührt.

DIESELBE ABRUF-FUNKTION WIE DIE PIPELINE: ``elliott_pipeline.fetch_yfinance``
— inklusive ``auto_adjust`` und Finit-Prädikat. Eine zweite Fassung würde
etwas anderes messen als der Tageslauf sieht, und die Messung wäre wertlos.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import elliott_pipeline as pipe  # noqa: E402

PROBE_PATH = "data/source_timing_probe.jsonl"

# WEGWERF: danach ist die Messung ein no-op mit klarer Logzeile. Ohne Enddatum
# läuft so etwas jahrelang weiter und niemand weiß mehr, wofür.
PROBE_END_DATE = _dt.date(2026, 8, 21)

# Stichprobe statt Vollabruf: gemessen wird der ZEITPUNKT, zu dem die Quelle
# den Tag trägt — dafür genügen wenige Titel. 10 je Markt halten den Aufwand
# bei ~20 Abrufen je Lauf (der Tageslauf macht 353) und decken trotzdem breit
# ab: je Markt die größten, meistgehandelten Namen aus verschiedenen Branchen,
# damit ein einzelner hängender Titel das Bild nicht kippt. Alle stammen aus
# dem echten Universum (config.MARKETS) — ein Test hält das fest.
PROBE_TICKERS: Dict[str, List[str]] = {
    "US": ["AAPL", "MSFT", "NVDA", "JPM", "JNJ",
           "XOM", "PG", "HD", "CAT", "KO"],
    "DE": ["SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "BAS.DE",
           "BMW.DE", "BAYN.DE", "MUV2.DE", "RWE.DE", "ADS.DE"],
}


def _jetzt() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def probe_markt(markt: str, tickers: Sequence[str],
                fetcher: Callable[[str], "pipe.FetchOutcome"],
                jetzt: Optional[_dt.datetime] = None) -> Dict:
    """Eine Messzeile für EINEN Markt.

    ``jetzt`` ist der ECHTE Abrufzeitpunkt — nicht die Cron-Sollzeit. Genau
    darin liegt der Wert der Messung: GitHub verzögert geplante Läufe (bisher
    gemessen 52–60 min, einmal aber 3:19 h), und eine Zeile mit der Sollzeit
    wäre eine Zeile über
    einen Zeitpunkt, zu dem gar nichts abgerufen wurde.

    Neben ``fetched_utc`` steht ``finished_utc``: 10 Abrufe dauern, und die
    gesuchte DE-Grenze soll auf ~15 min genau werden. Liegen Beginn und Ende
    einer Zeile weit auseinander, ist die Zeile über einen ZEITRAUM, nicht über
    einen Zeitpunkt — das muss bei der Auswertung sichtbar sein, statt als
    stille Unschärfe im Ergebnis zu landen.
    """
    begonnen = jetzt or _jetzt()
    reihen: Dict[str, tuple] = {}
    dropped_last = 0
    fehler: List[str] = []
    for tk in tickers:
        outcome = fetcher(tk)
        dropped_last += getattr(outcome, "dropped_last_row", 0) or 0
        if outcome.data is None:
            fehler.append(f"{tk}:{outcome.reason}")
            continue
        dates, _closes = outcome.data
        if dates:
            reihen[tk] = (len(dates), dates[0], dates[-1])
    fertig = _jetzt() if jetzt is None else begonnen
    q = pipe.series_summary(reihen) or {}
    return {
        "fetched_utc": begonnen.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_utc": fertig.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market": markt,
        "tickers_probed": len(tickers),
        "tickers_with_series": q.get("tickers", 0),
        "last_bar_date": q.get("last_bar_max"),
        "last_bar_min": q.get("last_bar_min"),
        "tickers_at_last_bar": q.get("tickers_at_last_bar"),
        "dropped_last_row": dropped_last,
        "shape_digest": q.get("shape_digest"),
        "errors": fehler,
    }


def _anhaengen(zeilen: Sequence[Dict], pfad: Optional[Path] = None) -> Path:
    """Eine Zeile je Markt anhängen. NUR diese Datei wird angefasst."""
    ziel = pfad or (REPO_ROOT / PROBE_PATH)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with ziel.open("a", encoding="utf-8") as fh:
        for z in zeilen:
            fh.write(json.dumps(z, ensure_ascii=False, sort_keys=True) + "\n")
    return ziel


def abgelaufen(heute: Optional[_dt.date] = None) -> bool:
    return (heute or _dt.date.today()) > PROBE_END_DATE


def main() -> int:
    if abgelaufen():
        print(f"[probe] Messfenster beendet (bis {PROBE_END_DATE.isoformat()}) "
              f"— kein Abruf, nichts geschrieben. Workflow und "
              f"{PROBE_PATH} können gelöscht werden.")
        return 0
    if os.environ.get("ELLIOTT_OFFLINE") == "1":
        print("[probe] OFFLINE — die Messung braucht die ECHTE Quelle, no-op.")
        return 0

    zeilen = []
    for markt, tickers in sorted(PROBE_TICKERS.items()):
        try:
            zeile = probe_markt(markt, tickers, pipe.fetch_yfinance)
        except Exception as exc:  # noqa: BLE001 — messen darf nie eskalieren
            # Rate-Limit oder Netzfehler: SOFORT aufhören, kein zweiter Versuch.
            # Ein Messlauf, der sich in Wiederholungen verbeißt, wäre genau die
            # Last, die er untersuchen soll.
            print(f"[probe] {markt}: Abruf abgebrochen "
                  f"({type(exc).__name__}: {exc}) — kein Retry, keine Zeile.")
            break
        # KEINE Reihe = KEINE Messung (Guardian-Fund 06.08.2026). `fetch_yfinance`
        # fängt Fehler INTERN ab und liefert `FETCH_ERROR` statt zu werfen — der
        # realistische Rate-Limit-Fall landet also NICHT im `except` oben, sondern
        # ergäbe eine vollständig leere Zeile. Die sähe später aus wie „die Quelle
        # hatte um 22:15 keine Daten" und würde genau die Cron-Entscheidung
        # verfälschen, für die hier gemessen wird.
        if not zeile["tickers_with_series"]:
            print(f"[probe] {markt}: KEIN einziger Ticker lieferte eine Reihe "
                  f"({len(zeile['errors'])} Fehler, erster: "
                  f"{zeile['errors'][0] if zeile['errors'] else '?'}) — das ist "
                  f"keine Messung, sondern ein Abruf-Ausfall. Keine Zeile, kein "
                  f"Retry.")
            break
        zeilen.append(zeile)
        print(f"[probe] {markt}: {zeile['fetched_utc']} · "
              f"letzter Bar {zeile['last_bar_date']} · "
              f"{zeile['tickers_at_last_bar']}/{zeile['tickers_with_series']} "
              f"am jüngsten · {zeile['dropped_last_row']} letzte Zeilen verworfen "
              f"· Abdruck {zeile['shape_digest']}")
    if not zeilen:
        print("[probe] nichts gemessen — nichts geschrieben.")
        return 0
    # ABSICHT, nicht Versehen: gelingt der erste Markt und fällt der zweite aus,
    # bleibt die EINE gelungene Zeile stehen. Sie ist ein vollwertiger Datenpunkt
    # für ihren Markt — sie wegzuwerfen, weil ein anderer Markt streikte, würde
    # Messungen vernichten, die nichts miteinander zu tun haben.
    if len(zeilen) < len(PROBE_TICKERS):
        fehlend = sorted(set(PROBE_TICKERS) - {z["market"] for z in zeilen})
        print(f"[probe] Teil-Messung: {fehlend} fehlt/fehlen — die gelungenen "
              f"Zeilen werden trotzdem geschrieben (eigenständige Datenpunkte).")
    ziel = _anhaengen(zeilen)
    print(f"[probe] {len(zeilen)} Zeile(n) an {ziel.relative_to(REPO_ROOT)} angehängt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
