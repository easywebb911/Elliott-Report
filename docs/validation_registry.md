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

> **Entry-Regel (Prinzip, festgeschrieben 23.07.2026 — PRU-Befund).** Ein Kandidat
> ist nur **auswertbar**, wenn bei Record-Anlage der Schlusskurs **UNTER
> `target_zone.low`** liegt — das Ziel darf erst **nach** der Anlage erreicht
> werden, sonst ist der „Treffer" ein Look-ahead-Artefakt und keine Vorhersage.
> Analog für `ext_hit` mit `extension.low`. **Hintergrund:** die stillschweigenden
> Annahmen der Backtest-Literatur (ein Signal wird zum Signalzeitpunkt eröffnet,
> das Ziel liegt noch voraus) müssen hier als **explizite Regeln** stehen — der
> PRU-Befund vom 23.07. zeigte, dass sie sonst still verletzt werden. Umsetzung:
> Guard in `mature_record` ab 23.07. (s. u. „Änderungs-Log").
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

- Auswertung **erst ab n ≥ 100 AUSWERTBAREN Setups** (gereift **und nicht**
  vom PRU-Guard ausgeschlossen — siehe nächster Punkt). „Gereift" allein reicht
  nicht; die n-Schwelle zählt `eval_counts(...)[2]` (auswertbar).
- **PRU-Guard / „Kurs schon bei Anlage über der Zone" (ab 23.07.2026, s. u.):**
  War der Schlusskurs am Anlage-Tag bereits **≥ Zonen-Unterkante**, ist ein
  späterer „Treffer" ein **Look-ahead-Artefakt** (das Ziel war zum Anlage-
  Zeitpunkt schon erreicht, keine Vorhersage). Solche Records reifen **normal**
  aus (Invalidierung, `max_gain/drawdown/r_multiple` voll gültig), aber
  `target_hit`/`ext_hit` sind **gesperrt** (auf 0, nie 1) und `pre_reached_target`
  / `pre_reached_ext` markieren sie. Records mit `pre_reached_*` **oder**
  `pre_guard_contaminated` sind aus **Trefferquote UND AUC** ausgeschlossen —
  sie zählen NICHT zur n ≥ 100-Population. Die Invalidierungs-Statistik bleibt
  von ihnen unberührt gültig.
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
- **`confluence`** (ab 23.07.2026 gesammelt) — **reines Mess-Feld**: welche breit
  beachteten Crowd-Marken (52-Wochen-Hoch, 200-Tage-Linie, nächste runde Zahl)
  innerhalb ±1 % mit Zielzone bzw. Invalidierung zusammenfallen (`{target, invalidation}`).
  **Point-in-time zum Anlage-Zeitpunkt eingefroren** (nie nachträglich geändert).
  **KEINE Score-/Ranking-Wirkung** (Registry-Vorbehalt). Zweck: die spätere
  n ≥ 100-Auswertung kann als **eigene Dimension** testen, ob Konfluenz-Zonen öfter
  treffen — eine etwaige Score-Wirkung käme **erst nach** einem Validierungsbefund.
- **`a_correction_observed`, `a_retrace_pct`, `a_observe_until`** (W5→A-Nachprüfung,
  **ab 24.07.2026 gemessen**) — **reines Mess-Feld**: folgt nach einem erfüllten
  **Ende-W4-Treffer** (`target_hit`, gereift, **nicht** PRU-ausgeschlossen) die
  theorie-gemäße Korrektur A? Nach dem Episoden-Hoch werden **`A_OBSERVE_DAYS = 10`**
  weitere Handelstage beobachtet; `a_correction_observed = true`, sobald der Kurs
  **≥ `A_RETRACE_MIN = 38,2 %`** (Fibonacci-Minimum) der W5-Strecke (P4→Hoch)
  zurückläuft, `false` bei vollem Fenster ohne Rücklauf, `null` solange das Fenster
  offen ist bzw. keine Messung greift. **Angehängtes Beobachtungsfenster** — es
  **verlängert oder ändert die bestehende Reifung nicht** (separater Durchgang,
  Reifungs-Zahlen byte-identisch). **Guard-Konsistenz:** `pre_reached`/`pre_guard`-
  Records bekommen **keine** Messung (ihr „Hoch" ist nicht interpretierbar → `null`).
  **KEINE Score-/Ranking-/Filter-Wirkung** (Registry-Vorbehalt); **Auswertung
  gemeinsam mit der n ≥ 100-Population**, dann als eigene Dimension „stimmt auch das
  Nachspiel?".

Diese Felder sind reine Anzeige-/Mess-Daten; die Auswertungs-Sperre (kein Aggregat
vor n ≥ 100) gilt unverändert.

## Änderungs-Log der Population

- **23.07.2026 — Universum erweitert von 99 auf 361 Ticker** (US ~50 → 239
  S&P-500-Titel; DE ~49 → 122 DAX/MDAX/SDAX). Statische Listen, kein Screener.
  **Wirkung auf die Validierung:** die Population (Kandidaten-Grundgesamtheit)
  wächst — die **Zählweise** ändert sich NICHT. Episoden-Definition,
  `appearance_count` (Episoden, nicht Tage) und die n ≥ 100-Sperre bleiben
  unverändert. Ab jetzt gesammelte Episoden entstammen dem größeren Universum;
  das ist transparent zu halten, wenn später ausgewertet wird (der Score-Test
  misst weiterhin den Score, nicht die Universums-Auswahl).
- **23.07.2026 — PRU-Guard: „Kurs schon bei Anlage über der Zone" von der
  Trefferquote ausgeschlossen.** Befund (Read-only-Diagnose 23.07.): PRU (Lauf
  2026-07-23) stand mit Kurs 117,4 **über** Zielzone 112,4–116,2 (Ende-W4), rankte
  aber mit Score 84 auf Platz 3 — und die Reifung zählte solche Fälle als
  `target_hit` **an Tag 1** (das Ziel war bei Anlage schon erreicht). Empirisch
  betroffen im Bestand: **MET, D, PRU** (`entry_close ≥ Zonen-Low`, `target_hit=1`
  nach 1 Bar). **Maßnahme (forward-only, nichts gelöscht):** (1) Guard in
  `mature_record` — `target_hit`/`ext_hit` nur, wenn `entry_close < Zonen-Low`
  (sonst gesperrt + `pre_reached_*`); (2) die 3 Alt-Records mit
  `pre_guard_contaminated: true` **ausgewiesen** (bleiben im Datenbestand,
  reifen weiter, zählen aber nicht in Trefferquote/AUC); (3) n ≥ 100 zählt ab
  jetzt **auswertbare** Records (`eval_counts`). **Bewusst NICHT geändert:** Score,
  Ranking, Filterung der Kandidaten. Ein **Filter** (verbrauchte Setups gar nicht
  erst ranken, Skip-Grund `target_exceeded`) ist eine **separate, spätere Produkt-
  Entscheidung** (offen), kein Teil dieses Registry-Eintrags. Score-Malus verworfen.
- **23.07.2026 — Filter `target_exceeded` aktiv (Populations-Änderung).** Easys
  Produktentscheidung auf Basis der PRU-Diagnose: ein Setup, dessen Lauf-
  Schlusskurs die Zielzone bereits erreicht hat (**`close ≥ target_zone.low`** =
  „Zielzone erreicht" = nicht mehr handelbar), wird **VOR dem Ranking** aus den
  **Markt-Top-5** verworfen (Skip-Grund `target_exceeded`, eigener Diag-Zähler);
  Rang 6+ rückt nach. **Wirkung auf die Population:** ab jetzt entstehen forward-
  Episoden **nur noch für handelbare** (nicht-verbrauchte) Top-5 — die Grundgesamt-
  heit verengt sich bewusst auf einsteigbare Setups. Die **Watchlist** ist
  ausgenommen (zeigt alles, Badge markiert den Zustand) und war ohnehin nie Teil
  der Population. **Verteidigung in der Tiefe:** der Filter verhindert die Neuanlage
  über Zone, der **#28-Guard bleibt** als zweites Netz (schützt die Messung, falls
  doch je eine Episode über Zone durchkommt — `pre_reached_*`/Ausschluss).
  Schwelle **identisch** zur Guard-/Entry-Regel (`target_zone.low`). Score/Ranking-
  Formel **unverändert**; nur die Kandidaten-Grundgesamtheit ändert sich (transparent
  zu halten, wenn ausgewertet wird — der Score-Test misst weiter den Score).
- **24.07.2026 — W5→A-Nachprüfung (Lit-Check b) als Mess-Feld ergänzt.** Für gereifte
  **Ende-W4-Treffer** wird ab jetzt mitprotokolliert, ob nach dem Episoden-Hoch die
  theorie-gemäße Korrektur A einsetzt (`a_correction_observed`/`a_retrace_pct`/
  `a_observe_until`, s. Feld-Beschreibung oben; benannte Konstanten
  `A_OBSERVE_DAYS = 10`, `A_RETRACE_MIN = 0.382` in `scripts/forward_collection.py`).
  **Reines Mess-Feld, angehängtes Beobachtungsfenster** — die bestehende Reifung
  bleibt **byte-identisch** (separater Durchgang), `pre_reached`/`pre_guard`-Records
  werden **nicht** gemessen. **Bewusst NICHT geändert:** Score, Ranking, Filterung,
  `report.json`-Markt-Payload, Erfolgs-Definition. **Auswertung erst gemeinsam mit
  der n ≥ 100-Population** (dann als eigene Dimension). Revertierbar (additive Felder).
- **25.07.2026 — Universum-Hygiene: 8 Symbole entfernt** (US 239 → 236, DE 122 → 117;
  Gesamt 361 → 353). Grundlage: `market.diag.dead_tickers` aus dem committeten
  `report.json` (Lauf 2026-07-25T13:35Z), alle Grund `empty_data` (yfinance liefert
  keine Kursreihe). Entfernt aus `config.py`-Listen **und** `data/ticker_meta.json`:
  **US (3):** `MMC`, `FI`, `HES`; **DE (5):** `1COV.DE`, `CTS.DE`, `UN01.DE`,
  `SHA.DE`, `COP.DE`. **Keine Ersatz-Ticker erfunden** — das Universum schrumpft
  minimal (ehrlicher als geratene Ersetzungen). Deckt sich exakt mit den
  `empty_data`-Zählern (DE 5 / US 3); gesunde Namensvettern **erhalten** (`COP`≠`COP.DE`,
  `FI`≠`FIS`, `NEM`/`NEM.DE`). **Wirkung auf die Validierung:** die Population
  schrumpft um tote Symbole, die ohnehin nie Kandidaten wurden — **Zählweise, Score,
  Ranking, Filter unverändert**. Erwartung Folge-Lauf: `empty_data → 0` je Markt.
  Revert = die 8 Symbole in `config.py` + `ticker_meta.json` wieder eintragen.
- **25.07.2026 — Messfelder v1 (Lit-Check P2): drei literaturgestützte MESS-Felder
  point-in-time eingefroren.** REINE MESSUNG — **Score, Ranking, Filter, Population
  und die bestehende Reifung bleiben byte-identisch** (belegt: Report-Diff nur
  additive `vol_*`-Keys, gleiche Kandidaten/Reihenfolge/Scores; Reifungs-Test grün).
  Volumen steckt im **selben** yfinance-Download (kein Extra-Call), additiv aus
  `parse_download_df` als `FetchOutcome.volumes`. **STEHENDE REGEL (nicht
  verhandelbar):** eine Definition wird **nie umdefiniert** — eine Änderung erzeugt
  neue, datierte Felder (`…_v2`), damit die n≥100-Auswertung stabile Zeitreihen hat.
  Definitionen v1 (Konstanten in `scripts/forward_collection.py`):
  - **(A) Volumen-Profil** (bei Anlage, `build_candidate`): `vol_profile` = Ø-Tages­
    volumen je Welle über das Pivot-Segment **inklusive** beider Pivot-Bars
    (`end_of_w2`: W1,W2 · `end_of_w4`: W1–W4). Abgeleitet: `vol_ratio_w3_w1`,
    `vol_ratio_w4_w3` (end_of_w4) bzw. `vol_ratio_w2_w1` (end_of_w2). Division-
    Guards: fehlendes/0-Volumen → betroffenes Feld `null`. **Guideline:** Volumen
    trägt in W1/3/5, **W3 am höchsten** — `vol_ratio_w3_w1 < 1` ist der
    Zählfehler-Verdacht (einziges sichtbares Element: dezenter Chip „W3-Volumen
    schwach", kein Score-Einfluss).
  - **(B) Alternation** (bei Anlage, **nur `end_of_w4`**; `end_of_w2` → alle `null`):
    Rohwerte `w2_retrace_pct` (von W1), `w4_retrace_pct` (von W3), `w2_bars`,
    `w4_bars` aus den eingefrorenen Pivots. Flag `alternation_observed` =
    `|w2_retrace − w4_retrace| ≥ ALTERNATION_MIN_DIFF_PP (20 pp)` **ODER**
    Dauer-Verhältnis `max/min ≥ ALTERNATION_DURATION_RATIO (2×)`. Die **Rohwerte**
    machen die Auswertung definitions-unabhängig (das Flag ist nur eine mögliche
    Operationalisierung).
  - **(C) W5-Momentum-Divergenz** (bei **Reifung**, **nur `end_of_w4` + `target_hit`**,
    nicht ausgeschlossen): Momentum-Proxy = `MOMENTUM_ROC_BARS`-Tage-Rate-of-Change
    der Schlusskurse (reines Python, keine Dependency). `w5_momentum_divergence` =
    Episoden-Hoch **> W3-Hoch** **und** ROC am Episoden-Hoch **<** ROC am W3-Hoch
    (W3-Hoch per **Datum** aus den Pivots gesucht — 2-J-Fenster wandert). Roh-
    Momentum `w5_mom_w3`/`w5_mom_high` mit eingefroren. Nicht bestimmbar (zu wenig
    Bars / `pre_reached` / kein P3) → `null`. **Angehängter** Schritt wie die
    W5→A-Nachprüfung — die Reifung (Schritt 2) bleibt byte-identisch.
  Alt-Records unberührt (Felder fehlen = `null`, forward-only, **kein Backfill**).
  Revert = die additiven Felder + `volumes`-Pfad + der eine Frontend-Chip raus.
- **25.07.2026 — Ambiguität v1 (Lit-Check P3): Ambiguitäts-Ausweis.** Fach-Konsens
  ist Multi-Count (fast immer > eine valide Zählung); der Haupt-Kritikpunkt an
  Elliott ist Subjektivität — dieser Ausweis macht sie **sichtbar UND messbar**.
  **`ambiguity v1` misst Mehrdeutigkeit INNERHALB des heutigen Zähl-Vokabulars
  (2 Fenster: Ende-W4/Ende-W2), nicht den vollen Elliott-Interpretationsraum.
  Erweitert sich das Vokabular später (z. B. ABC-Erkennung aus P4), entsteht ein
  NEUES datiertes Feld (`ambiguity v2`) — v1 wird nie umdefiniert.** REINE ANZEIGE/
  MESSUNG: **Score, Ranking, Filter, `target_exceeded`, Reifung byte-identisch**
  (belegt: Report-Diff rekursiv nur additive `valid_count_total`/`alt_count`-Keys,
  gleiche Top-5/Scores/Reihenfolge; `SCHEMA_VERSION` = 1). **Befund/Zuschnitt:**
  `classify_setup` (`scripts/elliott_pipeline.py`) ist **first-fit** über genau diese
  zwei festen End-Fenster; der Ausweis **zählt beide** (statt nur den ersten) — kein
  neuer Suchraum, keine Enumeration über variable Fenster (die wäre mit den zwei
  fixen Validatoren nicht sauber abgrenzbar → bewusst NICHT gebaut). Definitionen v1:
  - **`valid_count_total`** (int, 1..2): Anzahl regelkonformer **LONG**-Counts unter
    {Ende-W4 auf den letzten 5 Pivots, Ende-W2 auf den letzten 3}. Short-Counts
    zählen **nicht** mit (Long-only, konsistent zum Board). Auf jeder erzeugten
    Zählung (Markt-Kandidat + Watchlist + alle Zeitebenen `timeframes`/`higher_degree`).
  - **`alt_count`** (nur wenn `total ≥ 2`, sonst `null`): kompakte **zweitbeste** —
    `{count_label, invalidation_price, target_zone, score_heuristic}`, geordnet nach
    **exakt derselben** `score_setup`-Formel (kein neues Ranking-Kriterium). Die
    Primär-Zählung (`counts[0]`) ist byte-identisch zu `classify_setup`.
  - **`ambiguity_n`** (Sammlung, bei **Anlage** eingefroren = `valid_count_total`):
    Auswertungs-Dimension für n≥100 — treffen **eindeutige** Zählungen (N=1) öfter
    als **mehrdeutige** (N=2)? Alt-Records `null`, forward-only, kein Backfill.
  **UI (dezent):** am Count-Label „Zählung 1 von N" **nur bei N ≥ 2** (Maximum
  **„1 von 2"**); darunter aufklappbar die Alternative (Label · Inval · Ziel · Score
  gedämpft). N = 1 zeigt nichts (Eindeutigkeit ist der Normal-Idealfall). Laufzeit-
  Impact vernachlässigbar (1 zusätzlicher fixer 5-/3-Punkt-Check je Zählung, O(1);
  synthetic-Vollreport 353 Ticker ≈ 64 ms). Revert = additive Felder + `_eval_*`/
  `enumerate_long_counts`/`ambiguity_fields` + Frontend-Block raus; `classify_setup`
  bleibt (die Helfer-Auslagerung ist verhaltensgleich).
- **25.07.2026 — Struktur-Vokabular v2 + ambiguity v2 (Lit-Check P4a): ABC-Korrektur-
  Erkennung.** Das Zähl-Vokabular wird um einfache **Zigzag-Korrekturen (A-B-C)**
  erweitert — AUSSCHLIESSLICH für (1) den Watchlist-Struktur-Befund, (2) `ambiguity
  v2` und (3) die W5→A-Strukturmessung. **HARTE SCOPE-GRENZE (Populations-Schutz):
  KEIN neuer Markt-Setup-Typ — Top-5, Score, Ranking, Filter, Episoden-Anlage
  byte-identisch** (belegt: rekursiver Report-Diff nur additive
  `valid_count_total_v2`/`alt_count_v2`-Keys; v1-Felder byte-identisch). Ein
  „Ende-ABC = Long-Einstieg" wäre eine SPÄTERE, datierte Produktentscheidung.
  Definitionen v2 (`_detect_correction`/`_corr_from` in `scripts/elliott_pipeline.py`,
  Konstanten `_ABC_IMPULSE_PIVOTS=6`, `_ABC_MAX_CORR_PIVOTS=3`):
  - **ABC-Erkennung** (nur auf BESTÄTIGTEN ZigZag-Pivots — die Pivot-Bestätigung IST
    der Signifikanzfilter, der Rest strikte Preis-Ungleichungen): nach einem per
    `validate_impulse` **validen 5er-Impuls** (6 Pivots) gilt, richtungs-normalisiert:
    **A** gegen die Impulsrichtung (`d·A < d·P5`), **B** retraced A ohne den
    Impuls-Endpunkt zu überschreiten (`d·A < d·B < d·P5`), **C** jenseits des A-Endes
    (`d·C < d·A`). **Longest-first** (A-B-C vor A-B vor A) → deterministisch.
  - **Neue `structure_state`-Kategorien** (Watchlist): `correction_running` (A oder
    A-B bestätigt; Marke = Invalidierung der Korrektur-Lesart: bei A das
    **W5-Extrem** — darüber ist die Korrektur-Lesart hinfällig —, bei A-B das
    **B-Hoch/B-Tief** — darüber/darunter wäre B kein Korrektur-Hoch mehr) und
    `correction_complete` (A-B-C komplett; Marke = **C-Tief/C-Hoch** — jenseits
    läuft die Korrektur weiter, „neuer Impuls möglich" ist Ehrlichkeits-Sprache,
    KEIN Setup-Versprechen). **Präzedenz:** eine bestätigte Korrektur-Lesart
    beschreibt die Lage vollständiger als das erneute Impuls-Lesen der letzten
    6/5/3 Pivots → sie **gewinnt** gegen die bestehenden 5 Kategorien; greift NUR
    bei ≥7 Pivots mit validem Impuls + erfüllten Ungleichungen, sonst unverändert.
  - **`valid_count_total_v2`/`alt_count_v2`** (Kandidat + alle Zeitebenen):
    Lesarten im erweiterten Vokabular = valide Impuls-Fenster (wie v1) **+ 1**,
    falls eine Korrektur-Lesart bestätigt ist. Primär bleibt die Impuls-Zählung;
    `alt_count_v2` bevorzugt die zweitbeste Impuls-Lesart (nach `score_setup`),
    sonst die Korrektur-Lesart (`kind`='correction', ohne Zielzone/Score). Die
    **Anzeige** („Zählung 1 von N") nutzt ab jetzt v2 (fail-soft-Fallback v1).
  - **`ambiguity_n_v2`** (Sammlung, bei Anlage): ZUSÄTZLICH eingefroren; **`ambiguity_n`
    (v1) wird UNVERÄNDERT weiter befüllt** (Vergleichbarkeit der Alt-Daten).
  - **W5→A strukturell** (`observe_w5_structure`, bei Reifung, nur end_of_w4 +
    target_hit): `a_structure_observed` = True, sobald nach dem Episoden-Hoch
    mindestens **ein bestätigter ZigZag-Gegen-Pivot** vorliegt (dieselbe Engine wie
    der Count); False erst nach voll beobachtetem `A_OBSERVE_DAYS`-Fenster ohne
    Gegen-Pivot; sonst null. `c_target_pct` = Tiefe des tiefsten bestätigten
    Korrektur-Pivots in % der W5-Strecke (P4→Hoch). **Angehängter Schritt** —
    Reifung + bestehende W5→A-Felder byte-identisch.
  Alt-Records: Felder fehlen = null, forward-only, kein Backfill. **v1-Felder werden
  nie umdefiniert.** Revert = `_detect_correction`/`_corr_from` + Präzedenz-Zweig +
  v2-Felder + `observe_w5_structure` + Frontend (2 CSS-States, v2-Badge-Switch,
  Methodik-Absatz) raus.
- **26.07.2026 — Agent-Kommentar v1 (KI-Entscheidung Easy): nächtlicher LLM-Kommentar
  je Markt-Top-5-Karte.** REINE KOMMENTAR-EBENE — **kein Score-/Ranking-/Filter-
  Effekt** (belegt: der Schritt läuft in `main()` NACH `build_report`, also nach
  Sortierung, Top-N-Schnitt und allen Filtern, und schreibt ausschließlich das
  additive Feld `agent_comment`; Test `test_ranking_and_scores_byte_identical`).
  Adaption der Squeeze-KI unter Elliott-Disziplin. **Bewusst NICHT übernommen:**
  Agent-Boost ins Ranking (Squeeze-Re-Test: kein Edge), KI-Score, Stunden-Ticks.
  **NEU gegenüber Squeeze:** das Urteil wird **messbar eingefroren**.
  - **Umfang:** nur die FINALEN Markt-Top-5 (~10 Aufrufe/Lauf), **Watchlist
    ausgenommen**. Ein Aufruf je Kandidat.
  - **Konstanten** (`scripts/agent_comment.py`): `AGENT_MODEL =
    "claude-haiku-4-5-20251001"`, `AGENT_TEMPERATURE = 0.0`, `AGENT_MAX_TOKENS = 500`,
    `AGENT_TIMEOUT_S = 30`, `AGENT_PARSE_RETRIES = 1`, `ANTHROPIC_VERSION = "2023-06-01"`.
  - **Input:** ausschließlich eigene Pipeline-Felder des Kandidaten (`count_label`,
    Zonen, Invalidierung, Score, `valid_count_total_v2` + Alternative, `vol_ratio_*`,
    Alternation-Rohwerte, `confluence`, `appearance_count`, `change_pct`) — **keine
    externen Fetches in v1**, keine Nachrichten/Fundamentaldaten.
  - **Output** (strukturiert erzwungen): `{lesart, gegenargument, concern_level}` mit
    `concern_level ∈ {none, low, high}`; Parse-Fehler → 1 Retry → sonst `null`.
  - **Inhalts-Netz (Guardian-Nit, 26.07.):** der Prompt verbietet Wahrscheinlichkeits-/
    Empfehlungs-Sprache, ein LLM ist aber nicht bindbar — deshalb prüft `_parse_reply`
    den Freitext zusätzlich gegen `BANNED_PHRASES` (`wahrscheinlich`, `probability`,
    `confidence`, `trefferquote`, `kaufempfehlung`, `verkaufsempfehlung`,
    `anlageberatung`; dieselben Wörter wie das Report-Sicherheitsnetz). Treffer wird
    wie ein Parse-Fehler behandelt (Retry → sonst `null`) — verbotene Sprache kann
    also **nie** in `report.json` oder die UI gelangen (Test auf Report-Ebene).
    Gespeichert als `agent_comment = {lesart, gegenargument, concern_level, model,
    generated_at}` oder `null`.
  - **Fail-soft total:** fehlendes `ANTHROPIC_API_KEY` → no-op (Feld gar nicht
    gesetzt) + Log-Zeile; jeder API-/Parse-Fehler → `null`, der Lauf läuft weiter.
    Der Key wird **nie** geloggt (Test `test_key_never_logged`). Kosten-Log je Lauf
    (Tokens in/out).
  - **Messung:** bei Episoden-ANLAGE werden `agent_concern_level` und `agent_model`
    **point-in-time eingefroren**. Begründung: **LLM-Output ist nicht
    deterministisch** — `temperature 0` mildert das, garantiert es nicht; deshalb
    muss der Wert ZUM ANLAGE-ZEITPUNKT verortbar bleiben. Alt-Records `null`,
    forward-only, kein Backfill. **Auswertungs-Frage (n≥100):** trifft
    `concern_level = "high"` seltener als `none`/`low`?
  - **Der Prompt ist Teil dieser datierten Definition** (Änderung ⇒ neue Version,
    v1 wird nie umdefiniert). System-Prompt wörtlich:

    > Du bist ein nüchterner Elliott-Wellen-Analyst und kommentierst eine bereits
    > fertig berechnete Zählung. Du bewertest NICHT neu und vergibst KEINE Punkte —
    > du erklärst und widersprichst. Sprich Klartext auf Deutsch, ohne Werbe- oder
    > Empfehlungssprache, ohne Wahrscheinlichkeits- oder Trefferquoten-Behauptungen,
    > ohne Kauf-/Verkaufsempfehlung. Nutze AUSSCHLIESSLICH die gelieferten Zahlen;
    > erfinde keine Kurse, Nachrichten oder Fundamentaldaten. Antworte NUR mit einem
    > JSON-Objekt, ohne Markdown-Codefence, mit exakt den Schlüsseln: lesart (2-3
    > Sätze: was diese Zählung im Klartext behauptet), gegenargument (1-2 Sätze: der
    > stärkste Einwand, der sich AUS DEN DATEN ergibt — z. B. Mehrdeutigkeit,
    > schwaches W3-Volumen, weite Invalidierung, fehlende Alternation),
    > concern_level (genau einer der Werte "none", "low", "high" — wie stark die
    > Daten der Zählung widersprechen).

    User-Nachricht: `Kommentiere diese Elliott-Zählung. Alle Angaben stammen aus
    unserer eigenen Pipeline (heuristisch, unvalidiert):\n\n{facts-als-JSON}`.
  - **Anzeige:** dezente Karten-Sektion „KI-Kommentar" (Lesart + Gegenargument,
    grauer „heuristisch"-Badge, Modellname klein). `concern_level` bewusst als
    **neutraler Text**, NICHT als Ampel-Farbe (das wäre Score-Optik). Fehlt das
    Feld → Sektion fehlt.
  Revert = `scripts/agent_comment.py` + der `try`-Block in `main()` + die 2
  Freeze-Felder in `_new_record` + `agentBlock`/CSS + das `env:`-Secret raus.

- **27.07.2026 — Health-Check Stufe 2 (Plausibilitäts-Regeln mit Push).**
  Keine Populations-, Score- oder Auswertungs-Änderung — dieser Eintrag steht
  hier ausschließlich der Nachvollziehbarkeit halber. Stufe 1 (`notify.py`)
  meldet **Absturz** und **Ausfall**; Stufe 2 (`scripts/health_check.py`)
  schließt die verbleibende Lücke: **ein Lauf kann technisch erfolgreich sein
  und trotzdem Unsinn liefern.**
  **Anlass:** Lehre aus dem Schwester-Repo (easywebb911/Aktien-Update, PR #485,
  27.07.) — dort erzeugte ein Fetch-Pfad **NaN statt None**; NaN passierte alle
  `is not None`-Guards und jeden Vergleich (`nan <= 0` ist False), der
  Provider-Check verbuchte „Erfolg", der Fehler lief zwei Tage still weiter und
  ließ am Ende einen Trigger falsch feuern. Elliott rechnet ebenfalls Ratios aus
  Kursreihen — dieselbe Klasse ist strukturell möglich, mit **anderem
  Schadensbild**: `json.dump` schreibt `float('nan')` als literales `NaN`, das
  ist **kein gültiges JSON**; Python liest es klaglos, `JSON.parse` im Browser
  **wirft** → die PWA lädt gar nicht mehr (empirisch geprüft, nicht angenommen).
  **Sechs Regeln** am Lauf-Ende: (1) **Nicht-finit** — rekursiv über den
  fertigen Report **und** die Sammlung, geprüft mit `math.isfinite` (nicht mit
  `is not None`) und **vor** beiden Serialisierungen → `crit`; (2)
  **Vollständigkeit** — 0 Top-Einträge in einem Markt `crit`, weniger als
  `HEALTH_MIN_CANDIDATES` `warn`; (3) **Fetch-Qualität** — Fehlanteil über
  `HEALTH_MAX_FETCH_ERROR_PCT`, tote Ticker um mehr als `HEALTH_MAX_DEAD_DELTA`
  gegenüber dem Vorlauf gestiegen → `warn`; (4) **Sammlung** — Top-5 vorhanden,
  aber die Forward-Sammlung weder gewachsen noch verlängert → `warn` (fängt
  Persistenz-Regressionen wie #21 wieder ein); (5) **Agent** — weniger als
  `HEALTH_AGENT_MIN_OK` von 10 Karten mit Kommentar trotz gesetztem Secret →
  `warn` (ohne Secret: kein Befund); (6) **Push-Disziplin** — alle Befunde
  gebündelt in **einen** ntfy-Push, nur auf der **Flanke** (neu oder
  verschlechtert), `warn` frühestens nach `HEALTH_WARN_REPEAT_RUNS` Läufen
  erneut, Marker in `data/health_state.json`, Wochenend-/Feiertags-Gate.
  **Transparenz:** additiver Block `report["health"]`, sichtbar in der
  Lauf-Status-Ansicht — der Zustand ist auch **ohne** gesetztes `NTFY_TOPIC`
  nachlesbar.
  **SCHWELLEN SIND BETRIEBS-PARAMETER, KEINE AUSWERTUNGS-DEFINITIONEN.** Sie
  steuern, wann sich die Selbstüberwachung **meldet** — sie definieren nichts,
  was gemessen oder ausgewertet wird (kein Score, kein Erfolgsmaß, keine
  Populations-Regel). Sie dürfen deshalb **ohne neue Registry-Version** justiert
  werden; hier stehen sie nur, damit der damalige Melde-Stand verortbar bleibt:
  `HEALTH_MIN_CANDIDATES = 3`, `HEALTH_MAX_FETCH_ERROR_PCT = 10.0`,
  `HEALTH_MAX_DEAD_DELTA = 3`, `HEALTH_AGENT_MIN_OK = 5`,
  `HEALTH_WARN_REPEAT_RUNS = 3` (alle in `config.py`).
  **Harte Grenzen:** der Health-Check **ändert nie Daten**, **bricht den Lauf
  nie ab** (der Report wird geschrieben, der Befund gemeldet) und berührt
  **Score/Ranking/Filter/Reifung nicht** (bewiesen: der Report ist mit und ohne
  Health-Check identisch bis auf den additiven `health`-Schlüssel).
  Revert = `scripts/health_check.py` + die drei `try`-Blöcke in `main()` + der
  `HEALTH_*`-Block in `config.py` + `.health-box`-CSS/Renderer + die zwei
  `daily.yml`-Zeilen raus.

- **27.07.2026 — Nicht-finit-Härtung: Bars mit nicht-finiten Werten werden VOR
  der Zählung verworfen.** Ursachen-Fix zum Health-Check (#51); dieser Eintrag
  ist datiert, weil er die **Zähl-Definition berührt** — v1-Felder werden
  dadurch **nicht umdefiniert**.
  **Regel ab heute:** Eine Kurszeile ohne endlichen Schlusskurs (`NaN`/`±Inf`)
  ist **kein Bar**. Sie wird direkt beim Parsen verworfen — **bevor** Pivots,
  Zählungen, Zielzonen, Score oder Ratios entstehen — und je Ticker gezählt
  (`market.diag.dropped_bars`, sichtbar im Lauf-Status). Eine Zeile mit
  gültigem Kurs, aber unbrauchbarem **Volumen**, bleibt erhalten; nur ihr
  Volumen wird `null` (`invalid_volume_bars`). Begründung: das Volumen ist ein
  rein additives Messfeld ohne Score-Wirkung — die Zählung darf nicht von der
  Volumen-Verfügbarkeit abhängen.
  **Was vorher galt (und was daran still falsch war):** `df["Close"].dropna()`
  entfernte NaN-Zeilen, aber die Datumsliste wurde nur **vorne** abgeschnitten.
  Saß die Lücke in der **Mitte**, bekam jeder Kurs danach das Datum seines
  Vorgängers — das verschob Pivot-Daten, `chart_points`, die Sparkline-Achsen
  und die **point-in-time eingefrorenen** Pivots in der Sammlung. Zusätzlich
  entfernte `dropna` **kein ±Inf**, und die Volumen stammten aus dem
  **ungefilterten** Frame (zweiter Versatz). Alles drei lief ohne Fehlermeldung.
  **Reifung (`mature_record`):** ein nicht endlicher Close ist ab jetzt ein
  **fehlender Bar**, kein „kein Treffer". Vorher verlor er jeden Vergleich
  (`nan <= inval` ist False) und zählte trotzdem als abgelaufener Handelstag —
  er konnte also eine **Invalidierung verschlucken** und die Reifung
  gleichzeitig vorantreiben. Jetzt: solche Bars werden übersprungen und in
  `skipped_bars` ausgewiesen; gereift wird über **10 gültige** Bars (der
  Fehlbar verzögert um einen Handelstag, er blockiert nicht — ein Record bleibt
  nie still ewig offen). Alt-Records mit nicht endlichem Anlage-Wert werden mit
  `unmeasurable: true` markiert statt weitergerechnet.
  **POPULATIONS-VERGLEICH (Pflicht, belegt):** die Reifung wurde mit ALTEM und
  NEUEM Code über **25 committete Sammlungs-Stände** (23.–27.07.) und
  **341 Reifungs-Läufe** gerechnet und Feld für Feld verglichen —
  `target_hit`, `invalidated`, `ext_hit`, `matured`, `bars_elapsed`,
  `max_gain_10d`, `max_drawdown_10d`, `r_multiple`, `pre_reached_*`:
  **0 Abweichungen.** Ebenso 0 Abweichungen bei Alternation (27 Records mit
  eingefrorenen Pivots) und beim Invalidierungs-Bonus (10 Kandidaten des
  aktuellen Laufs). **Die Population ändert sich durch diese Härtung nicht** —
  die committeten Stände enthalten keinen einzigen nicht-finiten Wert. Die
  Härtung wirkt also ausschließlich in die Zukunft, falls die Kursquelle je
  löchrig liefert.
  **Bewusst NICHT geändert:** Score-Formel, Gewichte, Ranking, Filter,
  Erfolgs-Definition, `SCHEMA_VERSION` (bleibt 1 — alle neuen Felder additiv).
  Revert = `scripts/numeric.py` + die `finite(...)`-Guards + `_extract_bars` +
  der `skipped_bars`/`unmeasurable`-Zweig + die Diag-Felder raus.

- **28.07.2026 — AUSWERTUNG v1: das Auswertungs-Programm (`scripts/evaluate.py`)
  als datierte Definition festgeschrieben.** **BLIND GEBAUT bei 0 gereiften
  Fällen** — genau das ist der Zweck: wer die Auswertung erst schreibt, wenn er
  die Ergebnisse kennt, biegt sie unbewusst zurecht. Das Programm **setzt dieses
  Register um und definiert nichts neu**; wo es etwas operationalisieren musste,
  steht das unten ausdrücklich.
  **Harte Grenzen:** läuft **nie** im Tageslauf (kein Aufruf in
  `.github/workflows/`, kein Import aus `elliott_pipeline`/`notify`/
  `health_check` — per Test abgesichert), sendet **keinen** Push, schreibt
  **nie** in `forward_collection.json` oder `report.json`. Reines Lesen + eine
  Ergebnis-Datei.
  - **Population:** gereift UND nicht per PRU-Guard ausgeschlossen. Das Prädikat
    ist `forward_collection.is_excluded`, die Grösse wird gegen
    `eval_counts(...)[2]` **geprüft** — Abweichung = Abbruch der Auswertung
    (keine still abweichende Grundgesamtheit). Ausgeschlossene werden nach
    Grund getrennt ausgewiesen, nie weggelassen.
  - **Nur eingefrorene Felder** (`FROZEN_FIELDS`): der Ausgang kommt aus dem bei
    der Reifung eingefrorenen `target_hit`, **nie** aus einer neuen Rechnung mit
    heutigen Kursen. Ein Test protokolliert jeden Feldzugriff und schlägt fehl,
    sobald ein Feld ausserhalb der Liste angefasst wird.
  - **Sperre:** unter `EVAL_MIN_N` **auswertbaren** Fällen verweigert das
    Programm das offizielle Ergebnis; es läuft dann nur mit `--vorschau`, und
    jede Ausgabe trägt „VORSCHAU — NICHT GÜLTIG".
  - **Primär-Familie** (vorregistriert, Reihenfolge fest):
    (a) **Trefferquote gegen Zufalls-Benchmark** — je echtem Fall wird im
    **selben Ticker** über den **selben Zeitraum** (frühestes bis spätestes
    `first_seen_date` der Population) ein zufälliger Einstiegstag gezogen und
    mit **denselben relativen** Abständen zu Zielzonen-Unterkante und
    Ungültigkeitsmarke, **demselben Horizont** (`HORIZON_DAYS`) und **derselben
    Treffer-Definition** gerechnet (Gleichstand am selben Tag = Ungültigkeit,
    nie Treffer). `BENCH_DRAWS` Ziehungen ergeben die Null-Verteilung;
    p = (1 + #{Ziehungen ≥ beobachtet}) / (Ziehungen + 1) — die Add-One-Form,
    damit nie p = 0 behauptet wird.
    (b) **Score-Trennschärfe** — AUC (Rang-Form, Gleichstände 0,5) mit
    Perzentil-Bootstrap-Intervall; Kriterium ist die **Untergrenze > 0,5**.
    Beide Tests werden **Holm-korrigiert** über die Familie.
  - **Konstanten (Teil dieser Version):** `EVAL_SEED = 20260728` (fest, im
    Ergebnis dokumentiert), `EVAL_ALPHA = 0.05`, `BENCH_DRAWS = 10000`,
    `BOOTSTRAP_DRAWS = 10000`, `PERM_DRAWS = 10000`, `SECONDARY_MIN_N = 30`.
    `HORIZON_DAYS`/`EVAL_MIN_N` werden aus `forward_collection` gelesen
    (Single Source, keine Kopie).
  - **Sekundär (explorativ, NICHT beweisend):** W2 gegen W4, Konfluenz ja/nein,
    Volumen-Verhältnisse, Alternation, Momentum-Divergenz, Ambiguität v1 und v2,
    Agent-Einwand. Je Gruppe wird die **Fallzahl** ausgewiesen; unter
    `SECONDARY_MIN_N` erscheint **„zu wenige Fälle"** statt einer Quote.
    Bewusst **ohne** p-Werte und Intervalle — diese Dimensionen sind nicht
    vorregistriert, und jede Zahl mit Signifikanz-Anstrich wäre eine Einladung
    zum nachträglichen Erzählen.
  - **Ausgabe zweiteilig:** ein Klartext-Fazit in einfacher Sprache (ein Nein
    steht dort so deutlich wie ein Ja: „Der Ansatz hat den Test nicht
    bestanden") und ein Zahlenanhang (Fallzahlen, Quoten, Intervalle, p-Werte,
    Seed, Datum, verwendete Definitionen).
  - **ZWEI OPERATIONALISIERUNGEN, die dieses Register offen liess** (hier
    festgeschrieben, damit sie nicht später still anders ausfallen):
    1. **Kursbasis des Benchmarks.** Das Register verlangt „gleiche Aktien,
       zufällige Einstiegstage", sagt aber nicht, woher deren Kurse kommen — in
       der eingefrorenen Sammlung stehen sie nicht (dort liegen nur die Bars
       NACH dem echten Einstieg). Umsetzung: eine **separate
       Momentaufnahme-Datei**, erzeugt mit `--kurse-holen` (eigener Modus). Die
       Auswertung selbst geht **nie** ins Netz; fehlt oder lückt die Datei, wird
       der Benchmark als „nicht durchführbar" gemeldet und das Ergebnis kann
       **nicht** „belegt" lauten. Die Prüfsumme der verwendeten Kursbasis steht
       im Ergebnis.
    2. **Holm auf ein Intervall-Kriterium.** Für die AUC nennt das Register
       kein p-Kriterium, sondern eine Intervall-Untergrenze. Umsetzung: für die
       AUC wird zusätzlich ein **Permutations-p-Wert** gebildet (Labels
       gemischt), Holm läuft über beide p-Werte, und das Bootstrap-Intervall
       wird auf **demselben Holm-Niveau** gebildet (bei zwei Tests: 97,5 %).
       „Belegt" verlangt **beides**: Holm-Signifikanz **und** Untergrenze > 0,5.
  - **Selbsttests mit bekannter Antwort** (der eigentliche Beleg, dass das
    Programm taugt): reines Rauschen → **kein** Signal; eingebauter starker
    Zusammenhang → Signal erkannt; Punktzahl ohne Trennschärfe → Untergrenze
    unter 0,5; Grenzfall 99/100 an der Sperre. Ein realer Fund dabei: eine
    selbstgeschriebene binäre Suche in der AUC war falsch herum und lieferte
    still **0,5** — der Selbsttest „starker Zusammenhang" fing es, seither
    `bisect` aus der Standardbibliothek.
  **Spätere Änderungen erzeugen eine NEUE datierte Version (`Auswertung v2`);
  v1 bleibt stehen** — dieselbe stehende Regel wie bei den Messfeldern.
  **Bewusst NICHT geändert:** Score, Ranking, Filter, Reifung, Sammlung,
  `report.json`, `SCHEMA_VERSION`. Revert = `scripts/evaluate.py` +
  `tests/test_evaluate.py` + dieser Eintrag raus.

- **29.07.2026 — KLARSTELLUNG (keine Definitionsänderung): „Auswertung v1"
  verwendet den Setup-Typ der Sammlung wieder, statt ihn nachzubauen.**
  `scripts/evaluate.py` trug eine wortgleiche eigene Fassung von
  `_is_end_of_w4` — ausgerechnet in dem Modul, dessen Kernaussage
  „wiederverwenden statt nachbauen" ist. Sie ist jetzt ein Import aus
  `forward_collection`. **Verhalten unverändert:**
  `tests/test_one_count_source.py` stellt die entfernte Fassung nach und prüft
  über alle Rand- und Normalfälle (Ende-W4, Ende-W2, leere/fehlende Label,
  `wave: None`, Mehrfach-Label), dass beide **dieselbe Gruppe** liefern.
  **„Auswertung v1" bleibt inhaltlich unangetastet** — Population,
  Primär-Familie, Konstanten, Seed und Sekundär-Dimensionen sind identisch;
  dieser Eintrag dokumentiert ausschließlich, dass eine Doppelung im Code
  aufgelöst wurde. Kein neuer Versionsstand, keine v2.
  Im selben Zug, ebenfalls ohne Auswertungs-Wirkung: die Aggregate
  (gesammelt/gereift/auswertbar) stehen ab jetzt als additiver Block
  `report["validation"]` im Report und werden **nicht mehr im Frontend
  nachgerechnet** — eine Quelle (`eval_counts`) statt zweier Sprachen. Der
  PRU-Guard `_recExcluded` bleibt im Frontend, weil er JE FALL gebraucht wird
  (Episoden-Status); ein Test hält seine Feldliste mit `is_excluded`
  deckungsgleich. Score, Ranking, Filter, Reifung, Sammlung und
  `SCHEMA_VERSION` unberührt (belegt: rekursiver Report-Diff ALT/NEU über
  einen vollständigen Lauf → **nur** der `validation`-Block kommt hinzu).
  Revert = `report["validation"]` + der Frontend-Zweig + der Import raus.

- **29.07.2026 — KLARSTELLUNG: Abruf-Robustheit und Ehrlichkeit der Ausgabe.
  KEINE Änderung an „Auswertung v1".** Anlass war ein Trockenlauf des
  Programms an der ECHTEN Sammlung (37 Records, 0 gereift) — read-only,
  bevor es etwas zu sehen gibt. Population, Primär-Familie, Treffer-Definition,
  Konstanten, Seed und die Sekundär-**Dimensionen** sind unverändert; belegt
  durch einen Ergebnis-Vergleich an vollständigen Kunstdaten: `primaer`,
  `holm`, `urteil`, `fazit_klartext`, `reproduzierbarkeit` und `definitionen`
  **identisch** vor und nach der Änderung.
  Drei Punkte, alle außerhalb der Auswertungs-Definition:
  1. **Kursbasis-Abruf (`--kurse-holen`) scheitert jetzt sichtbar.** yfinance
     meldet einen Fehlschlag **nicht** als Ausnahme, sondern als leeren
     DataFrame. Der landete als gültig aussehender Eintrag mit 0 Bars in der
     Datei, das Log meldete „Kursbasis geschrieben (4 Ticker)", der
     Rückgabewert war 0 — der Fehler wäre erst bei der Auswertung aufgefallen.
     Jetzt: leere oder in sich versetzte Antworten kommen **gar nicht erst** in
     die Datei, `ticker_ohne_kurse` benennt die Fehlenden, das Log fasst
     zusammen, und der Modus endet mit Rückgabewert **3**, sobald ein Ticker
     fehlt. Die Auswertung selbst war nie gefährdet (unvollständige Kursbasis
     ⇒ „nicht durchführbar" ⇒ nie „belegt") — sichtbar war der Fehler trotzdem
     nicht.
  2. **Jede beauftragte Sekundär-Dimension erscheint**, auch ohne einen
     einzigen Fall (`hinweis: "keine Fälle"`). Vorher fiel eine leere Dimension
     ersatzlos aus der Ausgabe: im Trockenlauf fehlte `momentum_divergenz`
     komplett, weil das Feld bei allen Records `null` war. Wer die Ausgabe las,
     sah nicht, dass die Dimension geprüft wurde. Die Dimensionsliste steht
     jetzt fest in `SECONDARY_DIMS` (10 Einträge). Die Form je Dimension ist
     dabei von „Gruppen-Dict" auf `{faelle_gesamt, gruppen, hinweis}`
     gewechselt — reine Ausgabe-Form des **explorativen** Anhangs, keine
     Messgröße.
  3. **`ausgeschlossen_gruende` sind NENNUNGEN, keine Fälle.** Ein Record kann
     mehrere Gründe tragen (`pre_reached_target` UND `pre_reached_ext`); im
     Trockenlauf standen 13 Nennungen für 5 Fälle. Der neue Schlüssel
     `ausgeschlossen_gruende_hinweis` sagt das ausdrücklich und nennt die Zahl
     der betroffenen Fälle.
  **BEKANNTE EIGENSCHAFT (offen, nicht geändert):** Die Zufallsziehungen des
  Benchmarks stammen aus **demselben Zeitfenster** wie die echten Fälle und
  **überlappen sich zeitlich** — sowohl untereinander als auch mit den echten
  10-Tage-Horizonten. Ob das den Test **strenger oder milder** macht, ist
  **offen**; es ist hier bewusst nicht geraten. Vor der ersten echten
  Auswertung wird das an **Kunstdaten** geprüft (Null-Verteilung mit und ohne
  Überlappung gegeneinander). Die Konstruktion selbst folgt der
  Registry-Vorgabe „gleiche Aktien, zufällige Einstiegstage, **derselbe
  Zeitraum**" und bleibt bis zu diesem Befund **unverändert** — eine etwaige
  Anpassung wäre eine neue datierte Version, nicht eine stille Korrektur an v1.
  Revert = die drei Punkte in `scripts/evaluate.py` zurücknehmen; kein
  Datenstand wird ungültig.

- **30.07.2026 — BEKANNTE EIGENSCHAFT: der letzte Handelstag kann zwischen den
  Märkten um einen Tag abweichen.** Keine Änderung an „Auswertung v1", keine
  Änderung an Population, Zählweise, Score, Ranking, Filter oder Reifung —
  dies ist eine **Notiz**, jetzt festgehalten und nicht erst zur Auswertung.
  - **Was ist der Fall.** Je Lauf hängt es vom **Abrufzeitpunkt** ab, welchen
    letzten Handelstag die Kursquelle je Markt schon geschlossen liefert. Am
    29.07.2026 endete die US-Reihe auf dem 29.07., die DE-Reihe auf dem
    28.07. — die deutsche Schlusszeile des laufenden Tages war zum
    Abrufzeitpunkt noch nicht endlich (`NaN`) und wurde von der Härtung
    verworfen. Es ist **kein fester Versatz**: ein späterer Lauf am selben Tag
    (18:14 UTC) legte `ADS.DE` mit `first_seen_date = 2026-07-29` an, während
    der Lauf um 03:55 UTC genau diese Zeile verworfen hatte.
  - **Warum es zählt.** Der letzte Schlusskurs (`closes[-1]`) geht ein in den
    **Score** (Bonus über die Distanz zur Invalidierung, bis +15), in den
    **`target_exceeded`-Filter**, in die **Anzeige** und in `entry_close` /
    `first_seen_date` neu angelegter Episoden. **Innerhalb** eines Marktes ist
    das konsistent (alle Ticker desselben Marktes werden am gleichen Stand
    gemessen), **zwischen** den Märkten nicht.
  - **Ursache read-only belegt.** Ein Bündel-Abruf ist **ausgeschlossen**:
    `elliott_pipeline.fetch_yfinance` und `evaluate.fetch_prices` holen beide
    **je Ticker**. Der Unterschied lag allein in der fehlenden
    Endlichkeitsprüfung im Kurs-Abruf der Auswertung — offline reproduziert:
    dieselbe Reihe, Pipeline verwirft eine Zeile und endet einen Tag früher,
    der Abruf behielt das `NaN` und schrieb es als literales `NaN` in die
    Datei (ungültiges JSON, das Python still zurücklas).
  - **Bewusst NICHT geändert:** der **Abrufzeitpunkt** und ein Abschneiden der
    **letzten Zeile**. Beides würde die Population verschieben (welche Ticker
    gefunden werden, welche Episoden entstehen) — genau das soll diese Notiz
    vermeiden. Geändert wurde nur: (a) der Kurs-Abruf der Auswertung verwirft
    nicht-endliche Schlusskurse **mit passendem Datum**, benennt die
    betroffenen Ticker in `ticker_mit_luecken` und endet rot (Rückgabewert 3) —
    Abruf-Robustheit, nicht Auswertungs-Definition; (b) `markets[].last_bar_date`
    steht **additiv** im Report und im Lauf-Status („Kurse vom"), damit der
    Stand ablesbar ist statt aus `price_path` rekonstruiert werden zu müssen.
    Belegt durch rekursiven Report-Diff ALT/NEU über einen vollständigen Lauf:
    **nur** `last_bar_date` kommt hinzu.
  - **Für die Auswertung heißt das:** Der Vergleich echter Fälle gegen den
    Benchmark läuft je Fall auf **derselben** Kursreihe wie die Erfassung; ein
    markt-übergreifender Vergleich einzelner Schlusskurse auf denselben
    Kalendertag ist damit **nicht** zulässig. Sollte sich zeigen, dass der
    Versatz die Messung berührt, ist das eine neue **datierte** Version — nicht
    eine stille Korrektur an v1.
  Revert = `last_bar_date` (Pipeline + Frontend) und die Endlichkeitsprüfung in
  `evaluate.fetch_prices` zurücknehmen; kein Datenstand wird ungültig, diese
  Notiz bleibt gültig.
