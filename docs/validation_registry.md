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
- Ein **Punktschätzer allein ist nie Bestätigung**.

## Sammel-Mechanik (Kurzfassung)

- Ein Record **pro Ticker-Episode**. Kein Doppel-Record, wenn derselbe Ticker am
  Folgetag wieder in den Top-5 ist. **Wiederauftauchen nach Verschwinden = neue
  Episode.**
- Ein aus den Top-5 gefallener Ticker ändert **nichts** an offenen Records — die
  Episode reift trotzdem aus (kein Survivorship-Bias).
- Gesammelt wird in `data/forward_collection.json` (separat von
  `report.json`, additiv, revertierbar via `scripts/purge_forward_collection.py`).
- Fail-soft: ein Sammel-Fehler darf den Report nie brechen.
