# Validierungs-Register — Score-Validierung (Forward-Sammlung)

**Registriert am 22.07.2026 — VOR der ersten gesammelten Zahl.**
Diese Erfolgs-Definition ist vorab festgeschrieben (Präregistrierung). Sie darf
nicht nachträglich zugunsten eines gewünschten Ergebnisses geändert werden.

> **Der Score ist bis auf Weiteres `heuristisch · unvalidiert`.** Dieses Register
> legt fest, was „validiert" überhaupt bedeuten würde — und dass ein
> Punktschätzer allein das nie belegt.

## Was gesammelt wird (forward-only, je Kandidat ab Karten-Erscheinen)

Ab dem Tag, an dem ein Kandidat auf einer Karte erscheint, werden über einen
Horizont von **10 Handelstagen** ausschließlich vorwärts (forward-only)
gesammelt:

- **`target_hit`** — Basis-Zielzone erreicht **VOR** der Invalidierung (binär).
- **`ext_hit`** — Extension-Zone erreicht **VOR** der Invalidierung (binär).
- **`invalidated`** — Invalidierung zuerst gerissen (binär).
- **`max_gain_10d`** — maximaler Gewinn im Horizont (relativ zum Einstiegskurs).
- **`max_drawdown_10d`** — maximaler Rückgang im Horizont (relativ).
- **`r_multiple`** — max. Gewinn ÷ Abstand Kurs→Invalidierung (Reward in R).

## Wann Erfolg als BELEGT gilt

Erfolg gilt **NUR** als belegt, wenn **BEIDES** zutrifft:

1. Die **Trefferquote** schlägt einen **Zufalls-Benchmark** (gleiche Aktien,
   zufällige Einstiegstage, gleiche relative Ziel-/Stop-Distanzen)
   **Holm-korrigiert signifikant**, UND
2. die **Bootstrap-CI-Untergrenze der AUC** (Score vs. `target_hit`) liegt
   **> 0,5**.

## Regeln (nicht verhandelbar)

- Auswertung **erst ab n ≥ 100 gereiften Setups**.
- Das **Marktregime** wird je Record mitprotokolliert (z. B. SPY/DAX über/unter
  der 200-Tage-Linie).
- Forward-Daten werden **NIE mit Backfill gepoolt**.
- **Persönliche Watchlist-Ticker gehören NICHT zur Population.** Sie sind eine
  eigene Selektion, keine Tool-Auswahl; sie einzumischen würde die Auswahl-
  Verzerrung messen statt den Score. Der Schutz ist **baulich**: die Sammlung
  liest ausschließlich die Markt-Top-5 (`markets[].candidates`); die Watchlist
  lebt im separaten Feld `watchlist` und wird nie gesammelt. Ein Watchlist-Ticker
  zählt nur, wenn er **unabhängig** einen Top-5-Platz verdient.
- Ein **Punktschätzer allein ist nie Bestätigung**.

## Score-Status & Review-Wecker (`review_by`)

**Status:** `heuristisch · unvalidiert` — bleibt so, **bis** die obige
Erfolgs-Definition BELEGT ist. Der Status-Wechsel ist **rein menschlich**; nichts
automatisiert ihn.

**`review_by` (menschliche Kopie):** aktuell **2026-12-07** (grob projiziert, wann
n ≥ 100 gereift erreicht sein könnte). Die maschinenlesbare Quelle liegt in
`config.SCORE_REVIEW_BY`; **beide bei einer Änderung zusammen pflegen.** Ein
schlanker Wecker (`scripts/notify.py`) erinnert ~1×/Woche per ntfy, wenn das Datum
überschritten ist — er **ändert nichts**, weckt nur. Nach einer Auswertung wird
`review_by` **menschlich** neu gesetzt (Datum in die Zukunft) oder auf `None`
(abgeschaltet). Der Meilenstein-Push (n ≥ 100 tatsächlich gereift) feuert
zusätzlich datengetrieben genau einmal.

## Sammel-Mechanik (Kurzfassung)

- Ein Record **pro Ticker-Episode**. Kein Doppel-Record, wenn derselbe Ticker am
  Folgetag wieder in den Top-5 ist. **Wiederauftauchen nach Verschwinden = neue
  Episode.**
- Ein aus den Top-5 gefallener Ticker ändert **nichts** an offenen Records — die
  Episode reift trotzdem aus (kein Survivorship-Bias).
- Gesammelt wird in `data/forward_collection.json` (separat von
  `report.json`, additiv, revertierbar via `scripts/purge_forward_collection.py`).
- Fail-soft: ein Sammel-Fehler darf den Report nie brechen.

## Zusätzlich mitprotokollierte Felder (nur Anzeige/Backtesting)

Rein für die Review-Ansicht (Hamburger-Menü → „Validierung / Backtesting"),
**ohne** Einfluss auf die obige Erfolgs-Definition oder auf Score/Ranking:

- **`count_label`, `chart_points`, `count_wave_labels`** — die Auszählung zum
  **Anlage-Zeitpunkt** (Pivots Datum/Kurs/Art + Wellen-Ziffern). **Point-in-time
  eingefroren:** werden bei späteren Läufen nie geändert, damit die damalige
  Zählung exakt verortbar bleibt.
- **`price_path`** — die Folgetags-Schlusskurse (max. `HORIZON_DAYS`), je Lauf
  deterministisch aus der vollen Historie neu aufgebaut.

Diese Felder sind reine Anzeige-Daten; die Auswertungs-Sperre (kein Aggregat vor
n ≥ 100) gilt unverändert.

## Änderungs-Log der Population

- **23.07.2026 — Universum erweitert von 99 auf 361 Ticker** (US ~50 → 239
  S&P-500-Titel; DE ~49 → 122 DAX/MDAX/SDAX). Statische Listen, kein Screener.
  **Wirkung auf die Validierung:** die Population (Kandidaten-Grundgesamtheit)
  wächst — die **Zählweise** ändert sich NICHT. Episoden-Definition,
  `appearance_count` (Episoden, nicht Tage) und die n ≥ 100-Sperre bleiben
  unverändert. Ab jetzt gesammelte Episoden entstammen dem größeren Universum;
  das ist transparent zu halten, wenn später ausgewertet wird (der Score-Test
  misst weiterhin den Score, nicht die Universums-Auswahl).
