# SESSION_HANDOVER — Elliott-Report

**Kanonische, allein tragfähige Projekt-Quelle.** Eine frische Code-Session soll
allein mit diesem Dokument (plus Repo) weiterarbeiten können. Stand: **23.07.2026**,
nach PR #28 (dieser PR: **Filter `target_exceeded`**, offen). Alle Zahlen/
Hashes sind gegen `git log` und den Code geprüft, nicht aus dem Gedächtnis.

> **BRANCH-BASIS:** frisch von `main` (HEAD = #28-Merge `b1a20bd`) abgezweigt.
> Die stehenden Regeln „Rebase vor Ready-for-Review" **und** „Realdaten-Review nach
> Strukturänderung" (Abschnitt 8) vor dem Ready-Setzen prüfen.

> **PFLEGE-REGEL (nicht verhandelbar):** Dieses Dokument wird bei **JEDEM Merge im
> selben PR** aktualisiert — mindestens Abschnitte **2 (PR-Historie)**, **3
> (Offene Verifikationen)** und **4 (Roadmap)**. Ein PR ohne Handover-Update ist
> **unvollständig**; der Guardian prüft das mit.

---

## 1. PROJEKT-KERN

**Was:** Tägliches **Top-5-Elliott-Wellen-Screening je Markt** (🇺🇸 USA + 🇩🇪
Deutschland) als dunkle GitHub-Pages-**PWA**. Rein regelbasierte Wellen-
Auszählung aus Kursdaten → je Markt die 5 höchstbewerteten **Long**-Setups als
Karten, plus persönliche Watchlist.

**Nordstern:** ein **selbstüberwachendes System** — es sammelt seine eigenen
Vorhersagen forward-only ein, misst sich an einer vorab festgeschriebenen
Erfolgs-Definition und legt seinen Status transparent offen (Methodik /
Validierung / Lauf-Status im Menü).

**Auffanglinie (die rote Linie):** Der Score ist **`heuristisch · unvalidiert`**
bis ein Registry-Beweis vorliegt (Abschnitt 6). Das Tool ist ein
**Attention-Router** (wohin lohnt der Blick), **kein Alpha-Generator**. **Keine
Wahrscheinlichkeits-/Erfolgs-Sprache** irgendwo — nicht im JSON, nicht im UI.

---

## 2. PR-HISTORIE #1–#28

Format: `#N` · Feature-Commit-Hash (auf `main`) · Kern · Merge-Klasse.
Merge-Klassen: **manual** = Easy merged; **+G** = Guardian-Zweitblick vorab;
**+Bild** = Screenshot-Freigabe durch Easy. Guardian-Subagent eingeführt in #6,
durchgängig ab #13.

| PR | Hash | Kern | Merge |
|----|------|------|-------|
| #1 | `f4a8bc6` | Grundgerüst: Pipeline (ZigZag→Regeln→Score→JSON), PWA, `daily.yml`, Tests | manual |
| #2 | `6be7e9f` | Diag: Skip-Gründe instrumentieren (reines Logging) | manual |
| #3 | `fecb148` | **fix:** yfinance-MultiIndex-Spalten normalisieren (99/99-Skip-Bug) | manual |
| #4 | `202c30e` | Long-only: Short-Setups VOR dem Ranking filtern (`short_setup_excluded`) | manual |
| #5 | `906770e` | CI (`ci.yml`, pytest je PR) + Reload-Button | manual |
| #6 | `c4ee0d6` | Guardian-Zweitblick-Subagent (`.claude/agents/guardian.md`) + CI/Guardian-Doku | manual |
| #7 | `2272d0c` | Karten-Redesign im Squeeze-Stil + dunkelgrüne Sparkline | manual +Bild |
| #8 | `670ddc1` | additive Extension-Zielzone `target_zone_extended` (score-neutral) | manual |
| #9 | `c5ba450` | Karten-Header Squeeze (Rang, Name, Sektor, Chart-Link, Kurs+Δ) | manual +Bild |
| #10 | `bd33edf` | Live-Quote-Polling im Karten-Header (Cloudflare-Worker, 15 s) | manual +Bild |
| #11 | `c3eeeba` | Score als Donut in der Kartenmitte + Sparkline mit Pivot-Punkten | manual +Bild |
| #12 | `1c0d555` | großer Wellengrad (Wochen-Count `higher_degree`) + Wellen-Ziffern + Flaggen-Header | manual |
| #13 | `bec83fa` | **Forward-Sammlung** (präregistriert, separat, fail-soft) + `validation_registry.md` | +G manual |
| #14 | `7f67a6f` | Backtesting-Ansicht hinterm Hamburger (Episoden reviewen, eingefrorene Pivots + `price_path`) | +G manual +Bild |
| #15 | `69abd91` | Recalculate-Button (`workflow_dispatch`, Master-PW-AES-GCM-Token) | +G manual +Bild |
| #16 | `f029f73` | Menü-Ausbau: Methodik · Validierung · Lauf-Status (lesend) | +G manual +Bild |
| #17 | `f65f2f8` | persönliche Watchlist (Contents-API-Sync, `report["watchlist"]`) | +G manual +Bild |
| #18 | `f89e4c7` | N×-Zähler (`appearance_count`, Episoden nicht Tage) | +G manual +Bild |
| #19 | `f5e3dac` | Universum 99→361 (statisch) + Listen-Hygiene-Diag (`dead_tickers`) | +G manual |
| #20 | `d40a1d6` | **docs:** `SESSION_HANDOVER.md` (diese Datei) + Pflege-Regel | self (CI grün) |
| #21 | `cf2bd9f` | **fix:** `daily.yml` persistiert `forward_collection.json` (Sammlung akkumuliert, Push race-gehärtet) — **live bestätigt** (10 Records auf main) | manual |
| #22 | `efb57a1` | **Push-Paket Stufe 1** (ntfy, fast stumm): Lauf-Fehlschlag · Staleness-Cron · Meilenstein n≥100 · Review-Wecker | +G manual |
| #23 | `664952f` | **Mini-Sammler:** Disclaimer-Banner (einklappbar) · Wochenend-/Feiertags-Gate · kalenderbewusste Staleness (`market_calendar.py`) | +G manual +Bild |
| #24 | `d217d61` | **Score-Alert >90** (Flanke, nicht Zustand): EINMALIGER Push je Episode beim Neu-Überschreiten, gebündelt (1 Push/Lauf), an die vorhandene Episoden-Logik gekoppelt · `SCORE_ALERT_THRESHOLD=90` · Watchlist ausgenommen · fail-soft | +G manual |
| #25 | `408abe4` | **Watchlist-Sofortkarte** (Frontend): neu hinzugefügter Ticker zeigt sofort Live-Kurs-Karte statt leer/nur Chip; volle Elliott-Analyse weiter aus dem Lauf | manual |
| #26 | `5fb1188` | **Multi-Timeframe-Analyse Watchlist** (PR B): je Watchlist-Titel drei Zählungen `timeframes`{day,week,month}; Monatsgrad (`1mo`, `MIN_BARS_MONTHLY=60`) additiv; Analyse-Panel + Watchlist nach oben; Markt-Top-5 unberührt | +G manual +Bild |
| #27 | `a2d23bb` | **Token-Session-Remember** (Frontend): einmal Master-PW → 28 Tage still (`TOKEN_SESSION_DAYS=28`); IndexedDB-Wrap mit **non-extractable** Session-Key; „Sperren" im ☰; kein Klartext-Token persistiert | +G manual +Bild |
| #28 | `2bed684` | **Validierungs-Integrität (PRU-Guard)**: `mature_record`-Guard sperrt `target_hit`/`ext_hit`, wenn Kurs schon bei Anlage ≥ Zone (`pre_reached_*`); 3 Alt-Records `pre_guard_contaminated` ausgewiesen; Registry-Ausschluss datiert; Badge „Zielzone erreicht/überschritten". Kein Filter/Score-Eingriff, Ranking byte-identisch | +G manual +Bild |
| #(dieser) | `(offen)` | **Filter `target_exceeded`** (Produkt): Setups mit `close ≥ target_zone.low` fliegen VOR dem Ranking aus den Markt-Top-5 (Skip-Grund + Diag-Zähler, Rang 6+ rückt nach); Watchlist zeigt weiter alles (Badge). Populations-Änderung datiert; #28-Guard bleibt als zweites Netz | +G manual +Bild |

(Merge-Commits/tägliche `chore(data)`-Commits ausgelassen. Der tägliche
`report.json`-Commit trägt `[skip ci]`.)

---

## 3. OFFENE VERIFIKATIONEN (nicht schönreden — bleiben OFFEN bis belegt)

Aus der Sandbox **nicht** verifizierbar (kein Yahoo/EDGAR/externer Host, CORS):

- **✅ ERLEDIGT (#21, live bestätigt) — Forward-Sammlung wird persistiert:**
  `daily.yml` committet ab #21 auch `data/forward_collection.json` (+ Spiegel);
  der erste Lauf danach committete **10 Records** auf main (`c972403`). Die
  Sammlung akkumuliert über die Läufe; n wächst, `appearance_count`/N×-Badge und
  Reifung greifen. Push race-gehärtet (`git pull --rebase` + 3× Retry).
- **OFFEN — `.DE`-Chart-Link:** `stockanalysis.com/quote/etr/{SYMBOL ohne .DE}/`
  ist **Best-Guess** (`docs/index.html` `chartUrl`), nie live geöffnet. US-Muster
  `/stocks/{lower}/`.
- **OFFEN — `.DE`-Live-Quote:** der Worker `quote-proxy.easywebb.workers.dev`
  erlaubt nur Origin `easywebb911.github.io`; ein echter `SAP.DE`-Quote-Check steht
  aus (localhost trifft nur den Fail-soft-Pfad = grauer Punkt).
- **OFFEN — Recalculate-Live-Test:** Token hinterlegen (Fine-grained, **Actions:
  write**) → Recalculate → in *Actions* muss ein Lauf erscheinen. Real-POST in der
  Sandbox CORS-geblockt.
- **OFFEN — Token-Session am echten iPhone (#26/dieser PR):** einmal Master-PW →
  danach Recalculate/Watchlist-Speichern **ohne** erneutes PW (28 Tage) → „Sperren"
  fragt sofort wieder. Offline vollständig durchgespielt (Playwright 14/15, secure
  context http://localhost); die **iOS-ITP-Realität** (räumt Safari nach ~7 Tagen
  Inaktivität die Website-Daten, ist die Session früher weg → PW-Dialog) ist nur
  am echten Gerät beobachtbar.
- **OFFEN — Watchlist-Live-Test:** Ticker → „Für die Pipeline speichern" (Token
  zusätzlich **Contents: write**) → PUT auf `watchlist_personal.json` → nach Lauf
  erscheint die **volle** (analysierte) Karte. **Teil-Entschärft (dieser PR,
  „Sofort-Karte"):** ein neu hinzugefügter Ticker zeigt ab sofort eine Karte mit
  **Live-Kurs** (client-seitig, Quote-Worker) statt leer/nur Chip — die
  Elliott-Analyse (Setup/Score/Wellen) folgt weiterhin erst aus dem Lauf. Die
  Server-Runde (Token + Lauf) bleibt unverändert live zu prüfen.
- **OFFEN — Multi-Timeframe-Panel live (#PR-B):** greift erst mit echten
  Watchlist-Tickern (`watchlist_personal.json` aktuell `[]`) nach einem Lauf mit
  echten Monatsdaten. Offline/synthetisch belegt (Node-Harness + pytest): Panel
  rendert drei Zeilen Tag/Woche/Monat, null → „kein valider Long-Count". **Live zu
  prüfen:** echte yfinance-`1mo`-Daten je `.DE`/US-Titel (Datenlage ≥ 60 Monate),
  Panel-Optik am realen Ticker, `.DE`-Monatshistorie-Verfügbarkeit.
- **OFFEN — Push-Paket Stufe 1 scharfschalten (#22):** Easy muss das Repo-Secret
  **`NTFY_TOPIC`** (z. B. `easy-elliott-report`) setzen — bis dahin ist alles
  **still** (no-op). Danach live prüfen: Lauf-Fehlschlag-Push, Staleness-Push
  (report künstlich altern lassen / Cron dispatchen), ntfy-App auf das Topic
  abonnieren. Zustellung aus der Sandbox nicht testbar (Netz).
- **OFFEN — Score-Alert >90 live beobachten (dieser PR):** greift erst, wenn ein
  Kandidat real **>90** erreicht. **Frequenz-Messung über die GESAMTE committete
  Report-Historie (Universum 361): 0 Kandidaten je >90**, Höchststand **89,84**
  (PANW, aktueller Lauf) — also **de facto stumm** (aligned mit „bewusst fast
  stumm", KEIN Mini-Stopp nötig). Scharfschalten = dasselbe Secret **`NTFY_TOPIC`**
  wie #22. Zustellung aus der Sandbox nicht testbar (Netz).
- **TEILWEISE — Lauf-Status-Ansicht:** der #19-Dispatch-Lauf (`8a7d390`) hat
  `report.json` **mit** `diag` committet → die Ansicht sollte jetzt echte Zahlen
  zeigen (im UI noch gegenzuprüfen).
- **✅ ERLEDIGT — `dead_tickers`-Hygiene nach #19-Lauf** (Run 30002584301,
  Pipeline 85 s / Job ~1,7 min): `fetch_error=0` beide Märkte. `empty_data`
  namentlich — US: `MMC`, `FI`, `HES`; DE: `1COV.DE`, `CTS.DE`, `UN01.DE`,
  `SHA.DE`, `COP.DE`. **Achtung:** Mix aus echten Delistings (`HES`→Chevron,
  `1COV.DE`→ADNOC) und **transienter Yahoo-Drosselung** bei gültigen Größen
  (`MMC`,`FI`,`CTS.DE`,`SHA.DE`). **Nicht nach einem Lauf löschen** — über 2–3
  Läufe beobachten, nur konsistent Leere entfernen.

---

## 4. WARTESCHLANGE / ROADMAP (Stand 23.07.2026)

**✅ Push-Paket Stufe 1 — erledigt (#22, `scripts/notify.py`):** ntfy, bewusst
fast stumm. Anlässe: **Lauf-Fehlschlag** (`if: failure()` in daily.yml),
**Staleness** (separater Cron `staleness_check.yml`, erkennt den ausgefallenen
Lauf), **Meilenstein n ≥ 100** (einmalig, Marker-Datei), **`review_by`-Wecker**
(~1×/Woche). **Bewusst NICHT gebaut:** Invalidierungs-Riss-/Kandidaten-/Tages-
Pushes (Risse bleiben lautloser ✗-Status im Backtesting). Scharfschalten:
Secret `NTFY_TOPIC` setzen (Abschnitt 3).

**✅ Mini-Sammler — erledigt (#23):** Disclaimer-Banner (dezent, einklappbar,
localStorage `elliott_disc_collapsed`) · Wochenend-Gate (Cron `45 21 * * 1-5`) ·
Feiertags-Gate (gemeinsame NYSE∩Xetra-Voll-Schließtage in
`scripts/market_calendar.py`, mit Ablauf-Warnung ab 01.12.2027) ·
**kalenderbewusste Staleness** (Wächter rechnet gegen den letzten *erwarteten*
Lauf → kein Wochenend-/Feiertags-Fehlalarm).

**✅ Score-Alert >90 — erledigt (dieser PR, `forward_collection.score_alert_edges`
+ `notify.send_score_alert`):** EINMALIGER Push, wenn ein Kandidat in SEINER
Episode **neu** über `SCORE_ALERT_THRESHOLD` (=90) steigt (**Flanke, nicht
Zustand**). An DIESELBE Episoden-Erkennung wie der N×-Zähler gekoppelt (kein
Parallel-State): der Record der heutigen Erscheinung trägt `last_seen == run_date`,
das Flag `score_alert_fired` wird je Episode **einmalig** gesetzt und in der
Sammlung persistiert. Gebündelt (**1 Push/Lauf**), Markt im Text, trägt
„heuristisch · unvalidiert". Watchlist ausgenommen, fail-soft. **Lektion aus dem
Schwester-Repo (dortiger PR #471, 23.07.): Cooldowns ohne Flanken-Logik
re-alarmieren bei anhaltendem Zustand → Push-Flut.** Deshalb hier von Tag 1:
Flanke. Revert = Konstante entfernen / `edges`-Aufruf in `main` streichen (rein
additiv, Feld verschwindet beim nächsten Purge-Lauf).

**✅ Watchlist-Sofortkarte — erledigt (#25, Frontend):** lokal hinzugefügter Ticker
zeigt sofort eine Live-Kurs-Karte (`_wlInstantCard`) statt leer/nur Chip; volle
Elliott-Analyse weiter aus dem Lauf.

**✅ Multi-Timeframe-Analyse Watchlist — erledigt (dieser PR = „PR B", Herkunft:
Code-Vorschlag aus der #25-Session, von Easy freigegeben 23.07.):** je Watchlist-
Titel DREI Zählungen — Tag (bestehende Swing-Logik), Woche (bestehender Wochengrad),
NEU **Monat** (`interval=1mo`, `period=max`; Mindest-Datenlage
`config.MIN_BARS_MONTHLY=60` Monatskerzen = 5 Jahre → sonst fail-soft null).
Additives Feld `timeframes`{day,week,month} je Eintrag (jeweils {count_label,
invalidation_price, target_zone, target_zone_extended} oder null); Analyse-Panel
(`tfPanel`) auf der Karte mit drei Zeilen, null → dezent „kein valider Long-Count".
Reuse der ZigZag-/Regel-/Zielzonen-Mechanik über die geteilten Helfer
`_count_from_series`/`_count_from_fetch`. **Markt-Top-5, Score, Ranking,
forward_collection, Score-Alarm beweisbar unberührt** (Monatsgrad NUR Watchlist,
Watchlist bleibt außerhalb der Validierungs-Population). Laufzeit: bis zu **+2
Fetches je Watchlist-Titel** (Woche+Monat; Tag reust die geladene Tagesreihe) —
bei aktueller Liste (`watchlist_personal.json` = `[]`, 0 Titel) heute +0; Cap
`WATCHLIST_MAX=30` → höchstens +60. Revert = reiner Diff-Revert (Feld additiv).

**✅ Token-Session-Remember — erledigt (dieser PR, `docs/index.html`):** einmal
Master-PW entsperren → **28 Tage** (`TOKEN_SESSION_DAYS`) still, danach schlicht
wieder der PW-Dialog. IndexedDB-Session-Wrap nach Squeeze-Vorbild
(easywebb911/Aktien-Update), aber mit **non-extractable** Session-Key (sicherer
als Squeeze's rohe Key-Bytes) und **fester Frist** statt Rolling. Greift für
Recalculate UND Watchlist-Speichern (kein Doppel-Dialog); „Sperren"-Menüpunkt
beendet sofort. Klartext-Token nie persistiert. **Herkunft: Option 1 (Session-
Entsperrung) nach Risiko-Abwägung, Easy 23.07.** — bei PR #15 bewusst weggelassen,
jetzt portiert. Verifiziert: 14/15-Playwright-Zyklus (der eine „Fail" = externe
Quote-Worker-Netzfehler, nicht der Code). Revert = reiner Frontend-Diff-Revert.

**✅ Validierungs-Integrität / PRU-Guard — erledigt (dieser PR):** Grundlage =
Read-only-Diagnose 23.07. (PRU stand mit Kurs 117,4 **über** Zielzone 112,4–116,2,
rankte auf Platz 3, Score 84; die Reifung zählte solche Fälle als `target_hit` an
**Tag 1** — Treffer-Aufblähung der Validierung; 3 Records MET/D/PRU real betroffen).
Easy 23.07.: **Stufe 1 = Guard + Ausweisung + Badge** (Filter separat/später,
Score-Malus verworfen). Gebaut: (1) **Guard** in `mature_record` — `target_hit`/
`ext_hit` nur wenn `entry_close < Zonen-Low`, sonst gesperrt (0) + `pre_reached_*`;
Invalidierung/Kennzahlen bleiben voll gültig. (2) **Pre-guard-Ausweisung**
(forward-only, nichts gelöscht): MET/D/PRU mit `pre_guard_contaminated: true` im
Datenbestand markiert; `is_excluded`/`eval_counts` (auswertbar = gereift ohne
Ausschluss); Registry datiert (23.07.). (3) **Badge** „Zielzone erreicht"
(≥ low) / „überschritten" (≥ high), dezent, kein Alarm-Rot, Live-Quote aktualisiert
(`_setZoneBadge` in `quotePatch`); Panel zeigt „…· N auswertbar" + Tooltip.
**Grenzen:** kein Filter, kein Score-/Ranking-Eingriff (report.json byte-identisch,
belegt), SCHEMA_VERSION bleibt 1. Revert = Guard-Zeilen/Feld/Badge entfernen; die
`pre_guard_contaminated`-Marker sind rein additiv.

**✅ ENTSCHIEDEN & gebaut (dieser PR) — Filter `target_exceeded`:** Easys Produkt-
entscheidung (23.07., PRU-Diagnose). Setup mit Lauf-Schlusskurs **`≥ target_zone.low`**
(„Zielzone erreicht" = nicht mehr handelbar) wird in `build_candidate` VOR dem
Ranking verworfen (Skip-Grund `target_exceeded`, eigener Diag-Zähler, Lauf-Status-
Chip); Rang 6+ rückt nach. **NUR Markt-Top-5** — die Watchlist ruft
`build_candidate(..., exclude_target_reached=False)` und zeigt weiter alles (#28-
Badge markiert den Zustand). Schwelle **identisch** zur #28-Guard-/Entry-Regel.
**Verteidigung in der Tiefe:** Filter verhindert Neuanlagen über Zone, der
#28-Guard bleibt als zweites Netz (schützt die Messung, falls doch je einer
durchkommt). Registry: Populations-Änderung **datiert** (23.07.). Score/Ranking-
Formel unverändert; nur die Grundgesamtheit verengt sich auf handelbare Setups.
Revert = `exclude_target_reached`-Zweig + Konstante `TARGET_EXCEEDED` entfernen
(rein subtraktiver Filter, keine Datenreste). Nach Merge: `daily.yml` dispatchen,
`target_exceeded`-Zähler + neue Top-5-Besetzung + Nachrücker-Scores nachtragen.

**→ WARTESCHLANGE LEER.** Alle Bau-Punkte durch. Nächste Schritte brauchen einen
ausdrücklichen Startschuss von Easy (siehe GEPARKT). Naheliegend: Live-Verifikationen
aus Abschnitt 3 abarbeiten (NTFY_TOPIC scharfschalten, .DE-Chart/Quote, Recalculate/
Watchlist), dann irgendwann die KI-Entscheidung.

**Push-Paket spätere Stufen (geparkt):** die **Invalidierungs-Riss-Pushes** bleiben
bewusst **weg** (Rauschen); erst wieder aufgreifen, wenn Easy es ausdrücklich will.

**GEPARKT (mit Datum):**
- **KI-Agent** — Easy 23.07.: **weglassen**. Zuschnitts-Optionen für später
  notieren: (a) reiner Kommentator je Karte, (b) Research-Digest-Lauf, (c)
  Chat-Q&A über den Report. Keine Score-Beeinflussung.
- **Konfluenz-Marker** — Easy 23.07. (Lit-Check): Anzeige, wenn eine Zielzone
  oder die Invalidierung mit einer **Crowd-Marke** zusammenfällt (Vorjahreshoch/
  -tief, runde Zahl, 200-Tage-Linie). **Erst reine Anzeige/Messung** (additives
  Anzeige-Feld, wie `higher_degree`/`timeframes`) — **Score-Wirkung ausschließlich
  nach Validierungsbefund**. Kein Populations-/Ranking-Eingriff vor Beleg.
- **W5→A-Nachprüfung** — Easy 23.07. (Lit-Check): spätere **Anreicherung der
  Forward-Sammlung** — nachhalten, ob nach einem erwarteten W5 eine A-Korrektur
  folgt (Struktur-Nachprüfung des Counts). **Erst Messung/Erfassung** in den
  Episoden-Records (additiv, forward-only, Population unberührt) — **Score-/
  Erfolgs-Wirkung erst nach Validierungsbefund**. Kein Rückwirken auf `target_hit`
  o. Ä. vor Beleg.
- **Universum-Option B (Screener)** — nur mit **`source`-Markierung** UND
  **Populations-Ausschluss** (wie Watchlist: Screener-Ticker dürfen nie in die
  n ≥ 100-Population).
- **Score v1** — echte Kalibrierung, **erst nach** Validierungsbefund.
- **Robustere W5-Ext-Formel** — 2 bekannte Degenerierer (kurze Netto-Strecke
  P0→P3 drückt die Ext unter die Basis; Frontend blendet sie dann ehrlich aus,
  siehe `test_schema` W4-Kommentar).
- **Score-Smoothing** — erst nach Validierungsbefund.

---

## 5. ARCHITEKTUR-ANKER

### Pipeline (`scripts/elliott_pipeline.py`, `scripts/zigzag.py`, `scripts/rules.py`, `config.py`)
- **ZigZag:** `ZIGZAG_WINDOW = 5` (symmetrisches Fenster, alternierende Pivots).
  Wochen-Grad separat: `DATA_PERIOD_WEEKLY = "10y"`, `DATA_INTERVAL_WEEKLY = "1wk"`.
  Tagesdaten `DATA_PERIOD = "2y"` / `"1d"`, `MIN_BARS = 60`. **Monatsgrad (NUR
  Watchlist, #PR-B):** `DATA_PERIOD_MONTHLY = "max"`, `DATA_INTERVAL_MONTHLY = "1mo"`,
  `MIN_BARS_MONTHLY = 60` (5 Jahre — darunter kein Monats-Count, fail-soft null).
  `parse_download_df(df, min_bars=None)` teilt die Schwelle (Default = `MIN_BARS`).
- **3 harte Regeln (K.o., `rules.py`):** W2-Retracement ≤ 100 % · W3 nie die
  kürzeste von 1/3/5 · W4 überlappt W1 nicht.
- **Setups:** `end_of_w2` (letzte 3 Pivots P0–P2) und `end_of_w4` (letzte 5 Pivots
  P0–P4). Priorität W4 > W2. `end_of_c` existiert in config, wird aber nicht
  erzeugt.
- **Score** (`score_setup`, Gewichte `SCORE_WEIGHTS` je **1,0**, Summe):
  Basispunkte (`SETUP_BASE_POINTS`: **w2=45, w4=55**) + Fibonacci-Nähe (max
  **20**, Toleranz **±0,15**; Ziele w2 0,5/0,618 · w4 0,382/0,5) + Invalidierungs-
  Abstand (max **15**, linear bis Cap **10 %**). Max ≈ **90**. **Keine**
  Wahrscheinlichkeit.
- **Zielzonen (`TARGET_EXTENSIONS`, `_target_zone`):** W3 = P2 + [1,0–1,618]×W1 ·
  W5 = P4 + [0,618–1,0]×W1. **Extension (Variante b, additiv, nur Anzeige):**
  W3-Ext = P2 + [1,618–2,618]×W1 · W5-Ext = P4 + [0,382–0,618]×|P3−P0|.
- **Invalidierung:** W2-Setup → P0; W4-Setup → P1.
- **Long-only:** Short-Setups (direction < 0) VOR dem Ranking verworfen.
- **`target_exceeded`-Filter (#28-Folge, dieser PR):** in `build_candidate`
  (Param `exclude_target_reached`, Default True für Markt-Top-5, False für
  Watchlist) verwirft Setups mit `close ≥ target_zone.low` VOR dem Ranking —
  Skip-Grund `target_exceeded` (in `SKIP_REASONS`, Diag-Zähler + Lauf-Status-Chip
  „Zielzone erreicht"). Rang 6+ rückt nach. Schwelle = Guard-/Entry-Regel-Schwelle.
- **Universum (`config.py`, statisch):** **US 239** (S&P-Breite) · **DE 122**
  (DAX/MDAX/SDAX, `.DE`) = **361**. Dual-Class nur einmal (GOOGL/FOXA/NWSA,
  BRK-B). Ticker-Meta `data/ticker_meta.json` (Name+Sektor, 361/361 = 100 %,
  fail-soft).
- **Ranking:** `sort key = (-score_heuristic, ticker)`, dann `[:TOP_N]` (`TOP_N=5`).
- **Report-Felder:** `schema_version` (**=1**, additiv), `run_timestamp_utc`,
  `generated_in_seconds` (nur `main`), `markets[US|DE]` (`candidates` + `diag`
  {reason_counts, higher_degree_count, top_count, **dead_tickers**}),
  **`watchlist`** {entries, diag}. Kandidat trägt u. a. `count_label`,
  `invalidation_price`, `target_zone(_extended)`, `score_heuristic`,
  `chart_points`, `count_wave_labels`, `higher_degree`, `appearance_count`
  (in `main` gesetzt), `status="heuristisch · unvalidiert"`.
- **Multi-Timeframe (NUR Watchlist-Einträge, #PR-B):** additives Feld
  `timeframes`{`day`,`week`,`month`}, jede Ebene `null` **oder** {`count_label`,
  `invalidation_price`, `target_zone`, `target_zone_extended`}. Aufbau in
  `build_watchlist_entry` über die geteilten Helfer `_count_from_series` (Tag,
  reust die geladene Tagesreihe — kein Extra-Fetch) / `_count_from_fetch` (Woche
  via `get_weekly_fetcher`, Monat via `get_monthly_fetcher` — je +1 Fetch).
  `higher_degree` == `timeframes.week` (Wochen-Count EINMAL geholt, kein Doppel-
  Fetch). `build_report(..., monthly_fetcher=None, price_sink=None)` reicht den
  Monats-Fetcher **nur** an `build_watchlist` weiter — `build_market` bekommt ihn
  NICHT (Top-5 bleiben Tag+Woche, `timeframes` fehlt dort bewusst). Frontend
  `tfPanel()` rendert das Panel NUR bei vorhandenem `c.timeframes` (Markt-Karten
  behalten den reinen Wochen-`hd-block`).
- **Workflow:** `.github/workflows/daily.yml` — Cron **`45 21 * * 1-5`** (Werktage,
  #23) + `workflow_dispatch: {}`, `timeout-minutes: 30`, `concurrency:
  daily-elliott`, committet **report + collection** (#21) sowie den einmaligen
  `data/validation_milestone_fired.flag`.
- **Handelskalender (#23, `scripts/market_calendar.py`):** EINE Quelle für Gate +
  Staleness. `FULL_CLOSURE` = gemeinsame NYSE∩Xetra-Voll-Schließtage (Neujahr,
  Karfreitag, 1. Weihnachtstag) 2026–2027; `HOLIDAY_LIST_EXPIRES = 2027-12-01`
  (Ablauf-Warnung). Feiertags-Gate sitzt in `elliott_pipeline.main()` (nur echter
  Modus): an Voll-Schließtagen → log + `return 0`, nichts geschrieben.
  `last_expected_run(now)`/`is_stale(...)` überspringen Wochenende + Voll-
  Schließtage → **kein Staleness-Fehlalarm**. Einzelmarkt-Feiertage laufen normal.
- **CI:** `.github/workflows/ci.yml`, Check **`test`**, Offline-`pytest` je PR.
- **Push / Selbstüberwachung (#22, `scripts/notify.py`):** ntfy, `POST
  https://ntfy.sh/{NTFY_TOPIC}` + Title/Priority/Tags, fail-soft (`main()` immer
  exit 0). Topic aus **Secret `NTFY_TOPIC`** (leer → still). Modi: `--mode daily`
  (Meilenstein + Review-Wecker, in daily.yml VOR dem Commit) und `--mode staleness`
  (`.github/workflows/staleness_check.yml`, Cron **06:00 UTC**). Lauf-Fehlschlag =
  inline `if: failure()`-`curl`-Step in daily.yml. Config: `SCORE_REVIEW_BY`
  (menschlich), `STATUS_REVIEW_WEEKDAY=0`, `EVAL_MIN_N=100`, `STALENESS_HOURS=30`.
- **Score-Alert >90 (dieser PR):** IM Daily-Lauf, in `elliott_pipeline.main()`
  **nach** `update_forward_collection` (Episoden existieren) und **vor**
  `write_collection` (Flag persistiert). `fc.score_alert_edges(coll, report,
  config.SCORE_ALERT_THRESHOLD, run_date)` findet Kandidaten, die in ihrer Episode
  **neu** >Schwelle sind (Record mit `last_seen == run_date`, Flag
  `score_alert_fired` noch None → feuern + Flag setzen), gebündelt →
  `notify.send_score_alert(NTFY_TOPIC, edges, threshold)` = **1 Push/Lauf**. Flanke,
  nicht Zustand (Bleiben/Dip-Recross derselben Episode = stumm; neue Episode feuert
  erneut). Watchlist ausgenommen (nur `markets[].candidates`). Push **nach** dem
  Persistieren → Einmaligkeit vor Zustellgarantie (wie Meilenstein-Marker).

### Frontend (`docs/index.html`, Vanilla-JS, kein Framework, **kein** Service Worker)
- **Daten:** liest `data/report.json` (Fallback `../data/report.json`);
  `forward_collection.json` analog. Pages aus `/docs` → Report wird nach
  `docs/data/` gespiegelt.
- **Live-Quote-Anker:** `data-quote="price|dot|time"` (NICHT über CSS-Klassen
  ankern — Squeeze-Lesson). Worker **`https://quote-proxy.easywebb.workers.dev`**,
  Poll **15 s** (`QUOTE_POLL_MS`), `visibilitychange` pausiert.
- **Token-Krypto (aus Aktien-Update portiert):** PBKDF2-SHA256 **600000** Iter →
  **AES-GCM-256**, Salt **16 B**, IV **12 B**. `localStorage['elliott_gh_token_enc']`
  = nur verschlüsselter Blob `{v,salt,iv,ct}`; Master-PW nie persistiert.
  `GH_OWNER/REPO='easywebb911'/'Elliott-Report'`, `GH_WORKFLOW='daily.yml'`.
- **Token-Session-Remember (#26/dieser PR, `_ensureToken`-Layer):** nach EINEM
  Master-PW-Unlock bleibt die Token-Nutzung `TOKEN_SESSION_DAYS = 28` Tage still.
  Der Klartext-Token wird mit einem frisch generierten **non-extractable**
  AES-GCM-Key verschlüsselt und `{v, key(CryptoKey), iv, ct, expires_at_ms}` in
  **IndexedDB** (`elliott_session`/`session_wrap`/`tok`) via structured-clone
  abgelegt (`_persistSession`). `_ensureToken` probiert erst `_trySessionUnlock`
  (kein PW) — greift für **Recalculate UND Watchlist-Speichern** (kein Doppel-
  Dialog); Ablauf/Fehler → still Passwort-Dialog (fail-soft). **Feste Frist ab
  Unlock** (kein Rolling; Nutzung schreibt frischen Wrap mit SELBER Frist → nur
  ITP-Timer-Reset). „Sperren" (`mi-lock`) löscht den Record sofort. `_clearToken`
  löscht ihn mit (kein Geist-Session). **Klartext-Token NIE persistiert** —
  localStorage nur PW-Blob, IndexedDB nur ct + non-extractable Key. **Abweichung
  vom Squeeze-Vorbild** (dort rohe Key-Bytes b64 + 7-Tage-Rolling): non-extractable
  Key (sicherer) + feste 28-Tage-Frist (Easy-Vorgabe). iOS: Safari-Data-Clear →
  Session weg → normaler PW-Dialog.
- **Watchlist:** `localStorage['elliott_watchlist']`; Repo-Datei
  `watchlist_personal.json` via Contents-API (GET sha → PUT base64+sha, 409-Retry);
  Token zusätzlich **Contents: write**.
- **Menü (☰, 6 Punkte):** `mi-backtesting`, `mi-methodik`, `mi-validierung`,
  `mi-laufstatus`, `mi-recalc`, `mi-lock` („Sperren" — Session sofort beenden,
  #26/dieser PR). Escape-Priorität: Token-Modal > Menü > Info-Overlay > Backtesting.
- **Konstanten:** `EVAL_MIN_N = 100`, `COLLECTION_START = '22.07.2026'` (N×-Tooltip,
  an die Präregistrierung gebunden), `STALENESS_HOURS`-Banner bei > 30 h.
- **Disclaimer (#23):** dezenter, einklappbarer Banner oben; Merker
  `localStorage['elliott_disc_collapsed']` ('1' = eingeklappt).
- **Chart-Link:** `chartUrl` — US `/stocks/{lower}/`, DE `/quote/etr/{ohne .DE}/`
  (Best-Guess, unverifiziert).

### Merge-Policy & QS-Kette
- **Draft-PR → Guardian-Zweitblick (bei Workflow/Schema/Score/Filter/Pipeline) →
  Screenshots bei Optik → Easys Bild-Freigabe → Manual-Merge durch Easy.** Reine
  Doku-/Daten-PRs: kein Guardian; Doku-only darf bei grünem CI self-merge.
- Guardian = **Zweitblick, kein Gatekeeper** (Urteil OK / Nits / Blocker).
- **QS-Kette:** CI (`test`, required empfohlen) + Guardian + Easy.
- Modell-ID `claude-opus-4-8` **nie** in Commits/PRs/Artefakten.

---

## 6. VALIDIERUNG (`docs/validation_registry.md`)

**Präregistriert 22.07.2026 — VOR der ersten Zahl.** Erfolgs-Definition **wörtlich**:
Erfolg gilt **NUR** als belegt, wenn **BEIDES** zutrifft — (1) die **Trefferquote**
schlägt einen **Zufalls-Benchmark** (gleiche Aktien, zufällige Einstiegstage,
gleiche relative Ziel-/Stop-Distanzen) **Holm-korrigiert signifikant**, UND (2) die
**Bootstrap-CI-Untergrenze der AUC** (Score vs. `target_hit`) liegt **> 0,5**.

**Regeln (nicht verhandelbar):**
- Auswertung **erst ab n ≥ 100 AUSWERTBAREN** Setups (`EVAL_MIN_N`, `eval_counts`):
  gereift **und nicht** vom PRU-Guard ausgeschlossen.
- **Entry-Regel (PRU-Guard, 23.07.):** ein Record zählt in Trefferquote/AUC nur,
  wenn `entry_close < target_zone.low` (Ziel erst NACH Anlage); analog `ext_hit`
  mit `extension.low`. `pre_reached_*` / `pre_guard_contaminated` → ausgeschlossen
  (nie gelöscht). Invalidierung/Kennzahlen bleiben gültig.
- Marktregime je Record (SPY/DAX über/unter 200-Tage-Linie).
- Forward-Daten **nie** mit Backfill gepoolt.
- **Populations-Schutz (baulich):** **Watchlist**-, per-`appearance_count`-,
  **Score-Alert**- UND **Multi-Timeframe**-Logik berühren die Population nicht;
  alle lesen/schreiben **nur** außerhalb von `markets[].candidates` bzw. rein
  additiv. Watchlist (inkl. `timeframes`/Monatsgrad) lebt in `report["watchlist"]`
  und wird nie gesammelt/alarmiert; der Monats-Fetcher erreicht `build_market`
  nicht. Der Score-Alert setzt nur ein additives, anzeige-/push-neutrales Flag
  (`score_alert_fired`) — Score/Ranking/Reifung unberührt. Ein Punktschätzer
  allein ist nie Bestätigung.
- **Daten je forward-Kandidat (10 Handelstage):** `target_hit`, `ext_hit`,
  `invalidated` (binär), `max_gain_10d`, `max_drawdown_10d`, `r_multiple`.

**Datumsanker:** Sammlungs-Beginn/`COLLECTION_START` **22.07.2026**; **Universums-
Wechsel 23.07.2026** (99→361, Zählweise unverändert, im Register geloggt).

**Aktueller Zählerstand:** committete `forward_collection.json` = **0 Records** bis
zum ersten Lauf nach dem Persistenz-Fix (#21). Ab #21 akkumuliert die Sammlung —
der erste echte Lauf schreibt ~10 Records, danach wächst n Lauf für Lauf. (Live-
Beleg = Abschnitt 3.)

---

## 7. LESSONS (teuer gelernt)

- **Look-ahead in der Reifung (PRU, 23.07., → PR-Guard):** ein Setup, dessen Kurs
  schon BEI ANLAGE über der Zielzone stand, zählte als `target_hit` an Tag 1 — ein
  Look-ahead-Artefakt, das die Validierungs-Trefferquote aufbläht. Regel: Hits nur
  zählen, wenn das Ziel NACH der Anlage erreicht wird (`entry_close < Zonen-Low`),
  und schon-erreichte Fälle aus der Population ausschließen (nie löschen —
  ausweisen). Der Score „belohnt" das Davonlaufen zusätzlich (inval_bonus wächst
  mit dem Abstand zum K.o. bis zum Cap) — dort wurde bewusst NICHT eingegriffen.
- **yfinance-MultiIndex:** `download` liefert MultiIndex-Spalten; Test-Mocks
  müssen diese Form spiegeln (`get_level_values(0)`), sonst grüne Tests + 99/99-Skip
  live (PR #3). Guardian prüft: „Spiegeln die Mocks die echte Form?"
- **Sandbox-Stale-Base:** die Sandbox startet auf altem Stand → **immer zuerst
  `origin/main` fetchen und davon branchen** (steht in jedem Aufgaben-Prompt).
- **Proxy-Rechte:** `workflow_dispatch` geht; Branch-Delete / Branch-Protection-
  Änderungen → **403**. Nicht dagegen anrennen.
- **Sandbox erreicht kein Yahoo/EDGAR/externe Hosts** → alles Externe bleibt
  **Live-Verify durch Easy** (Abschnitt 3); Playwright-Tests mocken die GitHub-API.
- **iOS-Cache:** Design-Änderungen greifen sofort, **Daten** hängen im Safari-Cache
  → `cache:'no-store'` + Cache-Buster; **kein Service Worker**. `localStorage`
  räumt iOS-WebKit nach **~7 Tagen** Inaktivität (Token/Watchlist ggf. neu setzen).
- **Sequenz-Regel:** pro Runde **ein** Anzeige-/Optik-PR (Review-Last klein halten).
- **Draft-Bild-Freigabe:** Optik-PRs als Draft + Screenshots (~390 px) in den Chat
  → Easys Freigabe → dann ready/merge.
- **Alert-Flanke statt Zustand (Schwester-Repo PR #471, 23.07.):** Cooldowns/
  Schwellen ohne **Flanken-Logik** re-alarmieren, solange der Zustand anhält →
  Push-Flut. Regel: edge-triggered (einmal je Episode, Flag), NICHT
  level-triggered. Beim Score-Alert an die vorhandene Episoden-Erkennung koppeln,
  **kein** zweites State-System.
- **Determinismus:** `report.json` byte-identisch belassen (Realdaten macht nur CI);
  nicht-deterministische Felder (`generated_in_seconds`, `appearance_count`) nur in
  `main` setzen, nicht in `build_report` (Tests bleiben deterministisch).

---

## 8. ARBEITSWEISE

- **Drei-Rollen-Disziplin:** **Claude** (in Easys Slack/Chat) formuliert Prompts &
  berät; **die Code-Session** (dieses Repo) baut; **Easy** entscheidet & merged.
  Kein Selbst-Merge außer reiner Doku bei grünem CI.
- **Exzellenz-Selbstprüfung** je Aufgabe: Ziel-Mechanik statt „nichts kaputt";
  Fakten/Hashes belegen statt behaupten; Unverifiziertes bleibt **OFFEN** markiert.
- **Rate-Limit:** **kein Retry-Sturm** — bei Limit/Fehler **melden**, nicht blind
  wiederholen. Netz-Push mit Backoff (2/4/8/16 s), max 4 Versuche.
- **Mini-Stopp** bei fragilen Annahmen (z. B. Laufzeit-Hochrechnung > 25 min,
  nicht identifizierbarer toter Ticker, mehrdeutiger Review-Kommentar): kurz
  innehalten + Rückfrage statt bauen.
- **Guardian vor Manual-Merge** laufen lassen (Diff-Review), Urteil in den PR-Text.
- **Rebase vor Ready-for-Review (stehende Regel):** Vor jedem Ready-for-Review
  `origin/main` fetchen und **rebasen, wenn `main` sich seit Branch-Erstellung
  bewegt hat** — Handover-Konflikte **proaktiv auflösen** statt sie im PR-UI
  auflaufen zu lassen. Der Guardian prüft das künftig mit.
- **Realdaten-Review nach Strukturänderung (stehende Regel):** Nach jedem Eingriff,
  der **Population oder Datenlage** ändert (Universum, neue Wellengrade, neue
  Sammel-/Anzeige-Felder), folgt **binnen eines Laufs** ein bewusster Diagnose-Blick
  auf **ECHTE** Ergebnisse mit der Leitfrage **„Was ist hier absurd?"** —
  konstruierte Testfälle genügen NICHT. **Lesson:** der PRU-/`target_exceeded`-Fall
  blieb in allen Mocks unsichtbar, weil niemand den Fall konstruiert hatte; erst
  der Blick auf den echten Lauf (Kurs über Zielzone) deckte ihn auf.
- **Absolute Vorsicht, kein Risiko:** additiv, fail-soft, `report.json`/Score/
  Ranking/Population unberührt, Revert-Weg im PR-Text.

---

*Pflege: bei jedem Merge Abschnitte 2–4 (mind.) aktualisieren. Siehe README.*
