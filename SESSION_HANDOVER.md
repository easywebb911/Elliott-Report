# SESSION_HANDOVER — Elliott-Report

**Kanonische Arbeits-Quelle. Für den Session-Start reicht DIESE Datei.**
Sie enthält, was gilt und was offen ist: geltende Regeln, aktueller Zustand,
offene Punkte mit Datum, Lessons als Merksätze. Erledigte Stränge stehen mit
ihren vollständigen Belegketten im Archiv.

> **`SESSION_ARCHIVE.md` beim Session-Start NICHT lesen** — nur bei
> Detailfragen zu einem **erledigten** Strang (Lauf-IDs, Commit-Hashes,
> Mutationsproben, alte Live-Verifikationen). Wer hier nichts findet, findet es
> dort; umgekehrt gilt: was dort steht, ist abgeschlossen.

**Stand: 08.08.2026**, nach PR **#89** (`timeout-minutes` für `eval_prices.yml`,
gemerged `3ea7424`, Merge-Commit `4109999`). Zahlen gegen `main`
geprüft, nicht aus dem
Gedächtnis: **1045 Tests** grün · Sammlung **70 Records** (20 gereift, **15
auswertbar** von 100) · Marker **44 von 70** tragen mindestens einen
(`in_session_creation` 34 · `episode_split_suspect` 10 · `stale_market_suspect`
4) · Beweis-Datei `data/in_session_evidence.json` **17 Einträge** · Universum
**353** Ticker.

> **BRANCH-BASIS:** `claude/elliott-report-handover-health-oksgld`, auf
> `origin/main` aufgesetzt. Nach jedem Merge neu von `origin/main` aufsetzen —
> **nie** auf gemergter Historie stapeln.


> **PFLEGE-REGEL (nicht verhandelbar):** Dieses Dokument wird bei **JEDEM Merge im
> selben PR** aktualisiert — mindestens Abschnitte **2 (PR-Index)**, **3 (Offene
> Punkte)** und **4 (Warteschlange/Roadmap)**. Ein PR ohne Handover-Update ist
> **unvollständig**; der Guardian prüft das mit.
>
> **ARCHIV-REGEL (seit 08.08.2026, damit dieses Dokument nicht wieder
> zuwächst):** Wird ein Strang **abgeschlossen**, wandert seine **Belegkette im
> SELBEN PR** nach `SESSION_ARCHIVE.md` — Lauf-IDs, Commit-Hashes,
> Mutationsproben, Live-Verifikationen, Guardian-Urteile, Revert-Wege. Im
> Handover bleibt **eine Zeile mit Datum und Verweis**.
> **Anlass:** vor der Teilung (#85) trug dieses Dokument 1808 Zeilen / 253 KB,
> davon allein 663 Zeilen erledigte Bau-Blöcke in der Roadmap — nichts davon war
> falsch, es blieb nur nie jemand fürs Umräumen zuständig. Genau deshalb konnte
> „Warteschlange leer" monatelang **über** einer aktiven Warteschlange stehen.
> Die Regel dreht die bestehende Mechanik nur um eine Richtung: Erledigtes
> **verlässt** das Handover zum selben Zeitpunkt, zu dem es erledigt wird.

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


---

## 2. PR-INDEX #1–#90

Nur Nummer, Feature-Hash auf `main` und Kern in einer Zeile. **Die vollen
Zeilen mit Belegketten, Mutationsproben, Guardian-Urteilen und Revert-Wegen
stehen im Archiv** (`SESSION_ARCHIVE.md`, Abschnitt „PR-Historie") — dort
nachschlagen, wenn ein einzelner PR im Detail interessiert.

Merge-Klassen, Guardian-Urteile und Screenshot-Freigaben: ebenfalls im Archiv.

| PR | Hash | Kern |
|----|------|------|
| #1 | `f4a8bc6` | Grundgerüst |
| #2 | `6be7e9f` | Diag |
| #3 | `fecb148` | fix |
| #4 | `202c30e` | Long-only |
| #5 | `906770e` | CI (ci.yml, pytest je PR) + Reload-Button |
| #6 | `c4ee0d6` | Guardian-Zweitblick-Subagent (.claude/agents/guardian.md) + CI/Guardian-Doku |
| #7 | `2272d0c` | Karten-Redesign im Squeeze-Stil + dunkelgrüne Sparkline |
| #8 | `670ddc1` | additive Extension-Zielzone target_zone_extended (score-neutral) |
| #9 | `c5ba450` | Karten-Header Squeeze (Rang, Name, Sektor, Chart-Link, Kurs+Δ) |
| #10 | `bd33edf` | Live-Quote-Polling im Karten-Header (Cloudflare-Worker, 15 s) |
| #11 | `c3eeeba` | Score als Donut in der Kartenmitte + Sparkline mit Pivot-Punkten |
| #12 | `1c0d555` | großer Wellengrad (Wochen-Count higher_degree) + Wellen-Ziffern + Flaggen-Head |
| #13 | `bec83fa` | Forward-Sammlung (präregistriert, separat, fail-soft) + validation_registry.md |
| #14 | `7f67a6f` | Backtesting-Ansicht hinterm Hamburger (Episoden reviewen, eingefrorene Pivots |
| #15 | `69abd91` | Recalculate-Button (workflow_dispatch, Master-PW-AES-GCM-Token) |
| #16 | `f029f73` | Menü-Ausbau |
| #17 | `f65f2f8` | persönliche Watchlist (Contents-API-Sync, report["watchlist"]) |
| #18 | `f89e4c7` | N×-Zähler (appearance_count, Episoden nicht Tage) |
| #19 | `f5e3dac` | Universum 99→361 (statisch) + Listen-Hygiene-Diag (dead_tickers) |
| #20 | `d40a1d6` | docs |
| #21 | `cf2bd9f` | fix |
| #22 | `efb57a1` | Push-Paket Stufe 1 (ntfy, fast stumm) |
| #23 | `664952f` | Mini-Sammler |
| #24 | `d217d61` | Score-Alert >90 (Flanke, nicht Zustand) |
| #25 | `408abe4` | Watchlist-Sofortkarte (Frontend) |
| #26 | `5fb1188` | Multi-Timeframe-Analyse Watchlist (PR B) |
| #27 | `a2d23bb` | Token-Session-Remember (Frontend) |
| #28 | `2bed684` | Validierungs-Integrität (PRU-Guard) |
| #29 | `3e59b4e` | Filter target_exceeded (Produkt) |
| #30 | `e9727d6` | Konfluenz-Marker (Lit-Check a) |
| #31 | `3ad9473` | W5→A-Nachprüfung (Lit-Check b) |
| #32 | `8d2ac29` | ☰-Menü an Squeeze angeglichen |
| #33 | `d6bfa1f` | Watchlist-Kompakt-Grid |
| #34 | `d543303` | Recalculate-Status mit Zeitzähler (Squeeze-Muster) |
| #35 | `ff411c7` | Watchlist-Mehrwert |
| #36 | `a06f200` | Struktur-Marke präzisiert + A-Orientierung (Read-only-Diagnose PANW) |
| #37 | `b891efa` | Watchlist-Auto-Sync |
| #38 | `e5b04c1` | 3D-Karten-Look + blaue Watchlist-Tönung (Squeeze „Variante 1B" portiert) |
| #39 | `7946dad` | Header-Layout |
| #40 | `c5b14ca` | „Ziel erreicht/überschritten" je Zeitebenen-Zeile |
| #41 | `2320157` | P1-Audit |
| #42 | `e9101d3` | P2-Audit |
| #43 | `c41658f` | P3-Audit |
| #44 | `efa3f87` | Textgrößen-Steuerung (Squeeze-Vorbild app.html:3511) |
| #45 | `6f6d98c` | P4a-Audit |
| #46 | `29d1e1e` | P4b-Audit |
| #47 | `0ac6d92` | P4c-Audit |
| #48 | `90577a7` | Elliott-Wellen-Banner + Chip-Zeile entfernt |
| #49 | `48665a4` | Agent-Kommentar v1 (KI-Entscheidung Easy 26.07.) |
| #50 | `4c7b7d4` | KI-Kommentar standardmäßig eingeklappt |
| #51 | `85589a5` | Health-Check Stufe 2 |
| #52 | `79375fb` | NTFY_TOPIC-Verdrahtung |
| #53 | `87ed590` | Nicht-finit-Härtung (Ursachen-Fix zu #51) |
| #54 | `7393971` | Heartbeat-Push |
| #55 | `ba457cd` | Validierungs-Seite in Klartext |
| #56 | `5cd59f7` | Methodik |
| #57 | `89c5602` | Zählweise vereinheitlicht + Klartext auf der Methodik-Seite |
| #58 | `89c5602` | Auswertungs-Programm v1 (scripts/evaluate.py) |
| #59 | `3112f42` | Code-Hygiene |
| #60 | `5c6feae` | Abruf-Robustheit + Ehrlichkeit der Ausgabe (Folge des Trockenlaufs an der echt |
| #61 | `16a4c90` | Trade-Journal |
| #62 | `24cd0f9` | Drei Kleinigkeiten |
| #63 | `8380f88` | Abruf-Endlichkeit + last_bar_date + Registry-Notiz zum Ein-Tag-Versatz (Folge |
| #64 | `e0feedd` | Kursspalten im Abruf absichern (der offene Nit aus #63, erledigt) |
| #65 | `1c9c3fe` | Trade-Journal mit Lebenszyklus |
| #66 | `8846717` | Score-Alarm typ-relativ |
| #67 | `7cb8c1b` | Dispatch-Kollision im Tageslauf (Vorfall 31.07., Lauf 30626433741) |
| #68 | `ff07e78` | Episoden-Anschluss zählt KALENDERTAGE statt Läufe (mein Befund (b) aus dem Che |
| #69 | `bbca810` | notify-Skriptstart + Score-Dezimale |
| #70 | `b127d22` | Zonen-Abstand in Prozent (Easy-Wunsch, reines Frontend) |
| #71 | `43d1afc` | Kurs-Stand-Wächter |
| #72 | `3a8ae52` | Sammlungs-Schutz bei veraltetem Kurs-Stand |
| #73 | `bedde10` | Watchlist-Sync repariert |
| #74 | `38aa0ca` | Reihen-Diagnose + Veraltungs-Hinweis auf der Karte (Punkte 1 und 2 aus dem TKA |
| #75 | `ba01875` | Sitzungs-Ende als Erwartungs-Anker |
| #77 | `df68c9d` | Wegwerf-Mess-Workflow |
| #(dieser, nach #77) | `(offen)` | Umgebungsleck im Test |
| #78 | `3da447e` | Umgebungsleck im Test — die CI auf `main` war dauerrot, und niemand sah es |
| #79 | `9a2206a` | Ready-Meldung braucht Lauf-ID, Head-SHA und Zweigkopf-Abgleich |
| #81 | `97060d8` | In-Session-Marker in_session_creation (Beschluss Easy 07.08., nach read-only-D |
| #82 | `f8fd324` | Beweissicherung nachgezogen + Live-Verifikation von #81 |
| #83 | `f8219b1` | Marker-Entscheidung aufgelöst |
| #84 | `53b46af` | Nachtrag zur Auswertungsregel |
| #85 | `71a6522` | Handover geteilt — Arbeits-Handover + Beweis-Archiv |
| #86 | `f6fcb79` | Archiv-Regel in die Pflege-Regel, README-Verweis korrigiert |
| #87 | `e18eb4a` | README-Regel-Kopie durch Verweis ersetzt — EIN Ort für die Regel |
| #88 | `0d080af` | EIN Pfad-Baustein (`scripts/repo_path.py`) + laute statt stille Rückfälle in `health_check`/`notify` |
| #89 | `3ea7424` | `timeout-minutes: 20` für `eval_prices.yml` — der letzte Workflow ohne Deckel |
| #90 | `(offen, dieser)` | `requests` deklariert — die Sendeschicht aller Pushes hing an einer fremden Abhängigkeit |

<sub>**#85–#87 sind hier nachgetragen** (08.08., in #88): die drei Doku-PRs
aktualisierten das Handover, trugen sich aber nicht selbst in diesen Index ein —
die Pflege-Regel verlangt beides. Volle Belegketten haben sie nicht im Archiv;
ihre Commit-Nachrichten sind die Quelle.</sub>

<sub>**#76** fehlt bewusst: geschlossen, **nicht gemergt** (Wiederhol-Abruf; im Archiv begründet, der Zweig `claude/wiederhol-abruf` liegt noch auf dem Remote). **#80** war ein reiner Daten-/Doku-PR ohne eigene Historien-Zeile. Bei **#79** und **#81** nennt die Archiv-Zeile noch `(offen, dieser)` — hier steht der erste Feature-Commit (`9a2206a` bzw. `97060d8`), gemergt als `1acfe96` bzw. `eb0cd43`.</sub>


---

## 3. OFFENE PUNKTE (nicht schönreden — bleiben OFFEN bis belegt)

Aus der Sandbox **nicht** verifizierbar (kein Yahoo/EDGAR/externer Host, CORS):
was hier steht, braucht einen echten Lauf oder Easys Gerät.

**Erledigte Verifikationen sind ins Archiv gewandert** — unter anderem
#21 (Sammlung persistiert), #66 (Score-Alarm feuert), #67 (Zweig-Checkout),
#68 (Episoden-Anschluss), #78 (CI auf `main`), #81 (In-Session-Marker live),
der Mitternachts-Lauf vom 07.08. 01:04 (beide Befunde am selben Tag von selbst
aufgelöst), das erstmalige Greifen des #72-Gates und `last_fresh_run_date` im
echten Lauf. Wer die Belegketten braucht: Archiv.

- **OFFEN (Beobachtung, 07.08. 22:16) — der DE-Abendrückzug ist wieder da, und
  das Gate hat gegriffen.** Der Abend-Cron meldet DE `last_bar_date 2026-08-06`
  bei erwartetem `2026-08-07`, `dropped_bars 116` von 117 Tickern — dieselbe
  Form wie am 03.08. Folge: `bar_freshness:DE` **warn** und
  `new_episodes_gated: True` für DE, während US frisch blieb und normal
  sammelte. **Wächter (#71/#75) und Sammlungs-Schutz (#72) haben genau so
  gearbeitet, wie sie gebaut sind** — der Befund ist die dokumentierte
  Quellen-Unruhe, kein neuer Defekt. **Nebenwirkung, die man kennen muss:** DE-
  Records eines Tages sind dadurch schwer belegbar, weil kein späterer Lauf
  desselben Tages eine DE-Bar dieses Datums zeigt (siehe DUE.DE/TKA.DE unten).

- **OFFEN, STRUKTURELL UNBEANTWORTBAR (ab #81) — kippt bei den In-Session-Records
  ein Treffer-Verdikt?** Von den 34 markierten Records sind **16 belegbar**
  (Median 0,36 %, Maximum 1,58 % Abweichung des eingefrorenen `entry_close` vom
  echten Schluss) — aber **alle 16 sind ungereift**, tragen also noch kein
  Verdikt. Umgekehrt sind **alle 9 gereiften** markierten Records **nicht
  belegbar**: `diag.last_bar_date` gibt es erst ab #63 (30.07.), und für die
  Bars vom 23./24.07. existiert kein späterer Lauf, der den Ticker noch in den
  Top-5 führt. Betroffen namentlich: **WAC.DE, TKA.DE, G1A.DE, HAG.DE, PBB.DE,
  RTX** (Bar 23.07.) sowie **XEL, NVDA, SPG** (Bar 24.07.) — darunter **zwei
  `target_hit=1`** (HAG.DE, SPG) und **ein `invalidated=1`** (NVDA). **Es gibt
  in dieser Datenlage keinen einzigen Record, an dem die Frage überhaupt
  gestellt werden kann.** Das ist eine Lücke, keine Entwarnung.
  **Der einzige Weg, sie zu schließen**, wäre ein späterer Abruf der amtlichen
  Tagesschlüsse jener Tage — ein festgestellter Tagesschluss ändert sich nicht
  rückwirkend, wäre also ein gültiger Referenzwert (nur für die *echte* Seite,
  nie für den eingefrorenen Zwischenstand). **Easys Entscheidung**, ausdrücklich
  offen gelassen; die Sandbox erreicht die Quelle ohnehin nicht.
- **OFFEN (laufend, ab #81) — das Beweisfenster schließt sich täglich.** Ein
  In-Session-Record ist nur belegbar, solange die committete Report-Historie
  einen späteren Lauf mit derselben Bar enthält, der den Ticker **noch in den
  Top-5 führt**. **Sechs** der 18 heutigen Lücken sind genau so entstanden. Die
  drei Records vom 07.08. 14:46 (DUE.DE, SYK, TKA.DE) sind heute noch nicht
  belegt, weil zum Bau-Zeitpunkt kein späterer Lauf mit Bar `2026-08-07`
  vorlag; `scripts/collect_in_session_evidence.py` ist **append-only** und holt
  sie beim nächsten Lauf nach, wenn sie dann noch in den Top-5 stehen.
  **Praktisch:** das Skript nach dem Abend-Cron noch einmal fahren.
  **NACHTRAG 07.08. 22:16 (erledigt, siehe #82):** genau das gemacht — **SYK ist
  jetzt belegt** (eingefroren 339,47 gegen echten Schluss 339,03, **+0,1298 %**,
  Quelle Lauf `2026-08-07T22:16:41Z`, Commit `bfdbfd1`). Damit **17 von 34**
  belegbar. **DUE.DE und TKA.DE bleiben offen** — und zwar aus einem
  strukturellen Grund, nicht aus Zufall: der Abend-Cron zeigt DE auf
  `last_bar_date 2026-08-06` (der dokumentierte DE-Abendrückzug, 116 von 117
  Tickern verlieren die Freitags-Zeile), es gibt also **keinen** späteren Lauf
  mit DE-Bar `2026-08-07`. Solange DE abends zurückfällt, sind DE-Records vom
  selben Tag grundsätzlich schwer belegbar — der Beweis hängt an einem Markt,
  der genau dann unzuverlässig liefert.
- **BETRIEBSREGEL ab 07.08.2026 (Easy) — keine Hand-Dispatches während der
  Sitzungen.** US 09:30–16:00 New York, DE 09:00–17:30 Berlin. **Alle 34**
  In-Session-Records stammen aus `workflow_dispatch`; der geplante Abend-Cron
  (`45 21 * * 1-5`) hat **nie** einen erzeugt. Damit ist das Problem für
  künftige Records ohne Code-Änderung, ohne Gate und ohne Populations-Beweis
  beseitigt. Der Marker läuft trotzdem weiter — als Nachweis, nicht als Ersatz
  für die Regel.

- **BEFUND 06./07.08. — der Verzögerungs-Ausreißer, der die Messung begrenzt:**
  GitHub startet den geplanten Tageslauf (Soll 21:45 UTC) sonst nach
  **51:48 · 52:51 · 55:18 · 55:40 · 55:53 · 56:59 · 59:37** — der Lauf vom
  06.08. startete aber erst um **01:04**, also **3 h 19 min** zu spät. Das
  Cron-Raster der Sonde bleibt bei 55 min, weil es den Normalfall trifft.
  **Gegen drei Stunden Verzug hilft kein Raster:** fünf um denselben Betrag
  verschobene Einträge landen geschlossen mitten in der Nacht. Ein solcher Tag
  liefert **keine falschen** Daten (protokolliert wird der ECHTE
  Abrufzeitpunkt), sondern **keinen Ertrag** — er wird verworfen, die Messung
  braucht einen Tag länger. Steht so auch im Kopf der Workflow-Datei.
- **OFFEN (Backlog, kein Auftrag) — Rückfallwerte in `notify.py` können still divergieren:** `REPORT_PATH`, `CARD_STATUS` und `EVAL_MIN_N` haben `getattr(config, …, <Literal>)`-Rückfälle, deren Literale **zufällig** mit den echten Werten übereinstimmen. Genau deshalb blieb der Import-Ausfall unsichtbar — nur die zwei Werte ohne passenden Rückfall fielen auf. Die Pfad-Hygiene aus der Inventur (ein gemeinsamer `sys.path`-Baustein statt drei Fassungen) bleibt vorgemerkt.
- **OFFEN — Kurs-Abruf mit Löchern (Rot-Fall):** zweimal dispatcht (29.07. `bd2f63a`, 30.07. `c37a5dc`), **beide Male 33/33 Ticker ohne Lücken** → zu Recht grün, Artefakt hochgeladen, „Arbeitsbaum sauber". Der ROT-Fall ist damit live **noch nicht gesehen**, nur offline nachgestellt; er bleibt offen, bis ein echter Abruf einen Ticker in `ticker_mit_luecken` schreibt.
- **BEFUND 30.07. (Registry-Notiz bestätigt, mit einer Präzisierung) — der Ein-Tag-Versatz hat ZWEI Wege:** der Dispatch um 07:04 UTC zeigte alle 17 US-Ticker auf `2026-07-29`, alle 16 `.DE`-Ticker auf `2026-07-28`. Dabei wurde **keine** Zeile verworfen — die 29.07.-Zeile für `.DE` war **gar nicht vorhanden**. Der Versatz entsteht also (a) über eine noch nicht endliche Tages-Zeile, die die Härtung verwirft (so am 29.07. um 03:55), **und** (b) über eine Zeile, die die Quelle für `.DE` später liefert. Die Registry-Notiz vom 30.07. beschreibt Wirkung und Folgen korrekt, ihr Ursachen-Satz nennt aber nur (a) — Ergänzung ist Easys Entscheidung, nicht still nachgetragen.
- **OFFEN (laufend) — `last_bar_date` je Markt:** Stand 31.07. (Lauf 22:40Z): **DE `2026-07-30`**, **US `2026-07-31`** — der Ein-Tag-Versatz ist wieder da, in der Form aus der Registry-Notiz vom 30.07.: die letzte Zeile war für **alle 116** DE-Ticker nicht-finit (`dropped_bars: 116`, `dropped_bar_dates: {'2026-07-31': 116}`, je Ticker `(-1/0)` = letzte Zeile verworfen, keine mitten in der Reihe). US `dropped_bars: 0`. Bleibt in Beobachtung.
- **OFFEN (Beobachtung) — beide Märkte hingen am 04.08. auf dem 31.07.:** der Lauf vom 04.08. (04:46 UTC) meldet `last_bar_date` **DE und US je `2026-07-31`**, bei `dropped_bars` **116 (DE)** und **236 (US)** — erstmals auch US vollständig. Der Handelstag Montag 03.08. fehlt damit in beiden Märkten. Ob das der bekannte Ein-Tag-Versatz in größerer Form ist oder etwas Neues, ist **weiterhin nicht geklärt** — Easys Entscheidung, ob das eine eigene Untersuchung wert ist. **Die URSACHE bleibt offen; nur die FOLGEN sind seither eingedämmt:** #71 macht den Zustand laut (Health-Regel + Hinweis im Lauf-Status), dieser PR hindert einen solchen Lauf daran, neue Episoden anzulegen. Ein Lauf auf veralteten Kursen ist damit sichtbar und für die Sammlung folgenlos — er passiert aber unverändert.
- **OFFEN — `.DE`-Chart-Link:** `stockanalysis.com/quote/etr/{SYMBOL ohne .DE}/`
  ist **Best-Guess** (`docs/index.html` `chartUrl`), nie live geöffnet. US-Muster
  `/stocks/{lower}/`.
- **OFFEN — `.DE`-Live-Quote:** der Worker `quote-proxy.easywebb.workers.dev`
  erlaubt nur Origin `easywebb911.github.io`; ein echter `SAP.DE`-Quote-Check steht
  aus (localhost trifft nur den Fail-soft-Pfad = grauer Punkt).
- **OFFEN — Recalculate-Live-Test (inkl. Status-Banner dieser PR):** Token hinterlegen
  (Fine-grained, **Actions: write**) → Recalculate → in *Actions* muss ein Lauf
  erscheinen, UND das neue **Status-Banner** „Neuberechnung läuft … N s" muss laufen,
  bei fertigem Lauf automatisch die frischen Daten rendern (grünes „fertig" + Toast,
  kein manueller Reload). Real-POST + Report-Stand-Polling in der Sandbox CORS-/Netz-
  geblockt; **offline voll durchgespielt** (Playwright: läuft/fertig/Timeout/Feiertag,
  Mock-Report altert → Poll erkennt). **Endbeweis = echter Recalculate durch Easy.**
- **OFFEN — Token-Session am echten iPhone (#26/dieser PR):** einmal Master-PW →
  danach Recalculate/Watchlist-Speichern **ohne** erneutes PW (28 Tage) → „Sperren"
  fragt sofort wieder. Offline vollständig durchgespielt (Playwright 14/15, secure
  context http://localhost); die **iOS-ITP-Realität** (räumt Safari nach ~7 Tagen
  Inaktivität die Website-Daten, ist die Session früher weg → PW-Dialog) ist nur
  am echten Gerät beobachtbar.
- **OFFEN — Watchlist-Live-Test:** Ticker add/remove → **Auto-Sync** (seit diesem PR,
  Token zusätzlich **Contents: write**) → nach ~3 s Debounce PUT auf
  `watchlist_personal.json` (Toast „✓ Watchlist gesynct") → nach Lauf erscheint die
  **volle** (analysierte) Karte. Live zu prüfen: echter PUT am Gerät, gesperrte-Session-
  Dialog, „noch nicht gesynct"-Chip bei Offline. **Teil-Entschärft (dieser PR,
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
- **OFFEN — Score-Alert >90 live beobachten (dieser PR):** greift erst, wenn ein
  Kandidat real **>90** erreicht. **Frequenz-Messung über die GESAMTE committete
  Report-Historie (Universum 361): 0 Kandidaten je >90**, Höchststand **89,84**
  (PANW, aktueller Lauf) — also **de facto stumm** (aligned mit „bewusst fast
  stumm", KEIN Mini-Stopp nötig). Scharfschalten = dasselbe Secret **`NTFY_TOPIC`**
  wie #22. Zustellung aus der Sandbox nicht testbar (Netz).
- **TEILWEISE — Lauf-Status-Ansicht:** der #19-Dispatch-Lauf (`8a7d390`) hat
  `report.json` **mit** `diag` committet → die Ansicht sollte jetzt echte Zahlen
  zeigen (im UI noch gegenzuprüfen).
- **OFFEN — Health-Check Stufe 2 im echten Lauf (dieser PR):** nach dem Merge
  `daily.yml` dispatchen und nachtragen: **welche Regeln real feuerten (Soll:
  keine)**, **Laufzeit-Delta** (erwartet ~0 — die Prüfung ist ein Baum-Durchlauf
  über ~80 KB, plus EIN zusätzlicher `write_report`) und ein **Beweis-Lauf mit
  künstlich injiziertem NaN**, dass die Prüfung `crit` meldet. Offline
  vorbereitet: die Regeln wurden über die **letzten 15 committeten Reports
  zurückgespielt → 0 Fehlalarme**, der synthetische Voll-Lauf meldet `ok`, und
  der UI-Block ist headless in allen Zuständen (ok/warn/crit/gated/legacy)
  belegt. **Push-Zustellung** braucht wie #22/#24 das Secret **`NTFY_TOPIC`** —
  ohne Topic ist der Health-Check **still**, aber der `health`-Block im
  Lauf-Status zeigt den Zustand trotzdem (bewusst: Sichtbarkeit hängt nicht am
  Push).

---

## 4. WARTESCHLANGE / ROADMAP (Stand 08.08.2026)

**P0 — liegt bei Easy, nichts zu bauen:** *leer.* Alle PRs bis #89 sind gemergt.

**P1 — messen, nicht bauen (läuft von allein, braucht nur einen Zuruf):**

1. **Auswertung des Mess-Workflows**, sobald zwei bis drei **ertragreiche**
   Handelstage vorliegen. Die Sonde schreibt seit **07.08. 19:57 UTC**
   (`data/source_timing_probe.jsonl`); der erste Messtag zeigte für beide
   Märkte `last_bar_date 2026-08-07` bei `tickers_at_last_bar 10/10` — für eine
   Cron-Entscheidung ist das **ein** Tag, also zu früh. Ergebnis ist die
   Entscheidungsgrundlage für eine Verschiebung der Tageslauf-Cron; **erst
   danach** darf jemand an `45 21 * * 1-5` rühren, und *das* gehört dann in die
   Registry, nicht die Messung selbst.
2. **Aufräumen nach der Messung:** `.github/workflows/source_timing_probe.yml`,
   `scripts/source_timing_probe.py`, `tests/test_source_timing_probe.py` und
   `data/source_timing_probe.jsonl` löschen. Schaltet sich am **21.08.2026**
   ohnehin selbst ab (no-op + Logzeile mit dem Löschweg) — der Löschweg ist
   trotzdem zu gehen, sonst bleibt toter Code liegen.

**P2 — der letzte offene Fahrplan-Punkt:**

3. **Invalidierungs-Abstand** — gleiches Muster wie der Zonen-Abstand (#70),
   dieselbe **neutrale** Farbe (kein Grün/Rot beim Risiko-Wert). Nichts
   begonnen.

**P3 — Hygiene-Backlog, vorgemerkt ohne Auftrag:**

4. ~~**Rückfallwerte in `notify.py` können still divergieren**~~ — **erledigt in
   #88** (08.08.): `scripts/repo_path.py` ist der eine Pfad-Baustein,
   `health_check` und `notify` melden jeden Rückfall jetzt **laut**, und
   `SCORE_REVIEW_BY` unterscheidet „nicht auffindbar" (Fehler) von „bewusst
   `None`" (Abschaltung). Belegkette im Archiv.

   **NACHFOLGER, neu und ehrlich gezählt:** der `sys.path`-Block stand
   **neunmal** in `scripts/`; #88 hat **zwei** davon abgelöst, **sieben**
   Eigenkopien stehen noch (`elliott_pipeline` · `evaluate` · `in_session` ·
   `mark_in_session_creation` · `collect_in_session_evidence` ·
   `mark_stale_market_records` · `source_timing_probe`). Sie sind **schon
   auseinandergelaufen**: `source_timing_probe` ohne Dubletten-Schutz,
   `mark_stale_market_records` nur `scripts/` statt beider Verzeichnisse (heute
   unschädlich — es importiert `config` nicht). Der Umbau ist **ein Einzeiler je
   Datei**, gehört aber in einen eigenen Auftrag, weil `elliott_pipeline.py` im
   **Messlauf-Pfad** liegt. `repo_path.py` führt die sieben namentlich, und ein
   Test hält die Liste an der Wirklichkeit fest.

4b. ~~**`eval_prices.yml` ohne `timeout-minutes`**~~ (Inventur-Fund C4) —
   **erledigt in #89** (08.08.): der einzige Workflow ohne Job-Deckel lief sonst
   im Hängefall bis zum GitHub-Default von **6 Stunden**. Wert **20 min**, aus
   echten Laufzeiten hergeleitet (Belegkette im Archiv). Damit haben **alle
   fünf** Workflows einen Deckel: ci 10 · staleness 5 · probe 10 · eval_prices
   20 · daily 30.

4c. ~~**`requests` nur transitiv über yfinance**~~ (Fund 1 der Selbstwartungs-
   Diagnose 08.08.) — **erledigt in #90**: die Sendeschicht **aller** ntfy-Pushes
   (`notify._post`) war in `requirements.txt` **nicht deklariert** und kam nur
   über yfinance mit, dessen Abhängigkeiten sich innerhalb `<0.3` bewegen dürfen
   (0.2.66 nutzt bereits `curl_cffi`). Wäre `requests` je herausgefallen, hätte
   **jeder** Push still sterben können — und die Meldung darüber hätte durch
   dieselbe kaputte Schicht gemusst. Jetzt `requests>=2.31,<3`; Auflösung
   nachweislich unverändert. Belegkette im Archiv.

5. **`forward_collection.market_regimes` baut die MultiIndex-Reduktion inline
   nach** (offener Nit aus #64), statt `_normalize_columns` zu importieren.
   Vorbestehend; liegt im **Sammlungs**-Pfad, Aufräumen dort braucht den Beweis,
   dass sich die Population nicht verschiebt.
6. **Namens-Überlappung `series_summary` / `_count_from_series`** (kosmetischer
   Nit aus #74, bewusst nicht umbenannt — Test-Churn in einem sonst additiven
   PR).

**Aufräum-Schuld, klein aber real:** auf dem Remote liegen rund **zwanzig alte
Feature-Zweige** aus längst gemergten PRs (darunter `claude/wiederhol-abruf` zum
**geschlossenen** PR #76). **Der Git-Proxy dieser Umgebung weist Lösch-Pushes
mit HTTP 403 ab** — mehrfach erprobt, zuletzt am 08.08.; am iPhone ist es je ein
Fingertipp. Nichts hängt daran.

**Push-Paket spätere Stufen (geparkt):** die **Invalidierungs-Riss-Pushes** bleiben
bewusst **weg** (Rauschen); erst wieder aufgreifen, wenn Easy es ausdrücklich will.

**GEPARKT (mit Datum):**

> **Lit-Check-Liste damit LEER.** Beide aus dem Literatur-Abgleich geparkten Punkte
> sind gebaut: **Punkt a (Konfluenz-Marker)** = #30, **Punkt b (W5→A-Nachprüfung)** =
> dieser PR. Kein offener Lit-Check-Punkt mehr.

- **KI-Agent** — Easy 23.07.: **weglassen**. Zuschnitts-Optionen für später
  notieren: (a) reiner Kommentator je Karte, (b) Research-Digest-Lauf, (c)
  Chat-Q&A über den Report. Keine Score-Beeinflussung.
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
- **Universum (`config.py`, statisch):** **US 236** (S&P-Breite) · **DE 117**
  (DAX/MDAX/SDAX, `.DE`) = **353** (Stand 25.07., nach Hygiene-PR: 8 tote `empty_data`-
  Symbole entfernt, vorher 361). Dual-Class nur einmal (GOOGL/FOXA/NWSA,
  BRK-B). Ticker-Meta `data/ticker_meta.json` (Name+Sektor, 353/353 = 100 %,
  fail-soft).
- **Ranking:** `sort key = (-score_heuristic, ticker)`, dann `[:TOP_N]` (`TOP_N=5`).
- **Report-Felder:** `schema_version` (**=1**, additiv), `run_timestamp_utc`,
  `generated_in_seconds` (nur `main`), `markets[US|DE]` (`candidates` + `diag`
  {reason_counts, higher_degree_count, top_count, **dead_tickers**}),
  **`watchlist`** {entries, diag}. Kandidat trägt u. a. `count_label`,
  `invalidation_price`, `target_zone(_extended)`, `score_heuristic`,
  `chart_points`, `count_wave_labels`, `higher_degree`, `appearance_count`
  (in `main` gesetzt), **`confluence`**{target,invalidation}, `status="heuristisch
  · unvalidiert"`.
- **Konfluenz (Markt + Watchlist, dieser PR):** `compute_confluence(closes,
  target_zone, invalidation)` in `build_candidate` (NACH dem Score) — Crowd-Marken
  `52w_high`/`200d`/`round` vs. Zielzone/Invalidierung innerhalb
  `CONFLUENCE_TOLERANCE_PCT=1 %`. 52w/200d = Band-Mitgliedschaft; `round` nur an
  den Kanten (dicht), Stufen `CONFLUENCE_ROUND_STEPS`. Aus den geladenen `closes`
  (keine neuen Fetches). **Kein Score/Ranking** (nach `score_setup`). In der
  Sammlung point-in-time eingefroren (`_new_record` → `confluence`); reines
  Mess-Feld (Registry 23.07.).
- **W5→A-Nachprüfung (NUR Forward-Sammlung, dieser PR):** `observe_a_correction(rec,
  dates, closes, now_iso)` in `forward_collection.py`, aufgerufen im **separaten 3.
  Durchgang** von `update_forward_collection` (nach der Reifungs-Schleife, damit die
  Reifung byte-identisch bleibt). Misst NUR für gereifte, nicht `is_excluded`-
  end_of_w4-`target_hit`-Records: Episoden-Hoch = `max` der Reifungs-10 (`fwd`);
  W5-Strecke = Hoch − `_p4_price` (chart_point mit `count_wave_labels.wave==4`);
  A-Fenster = die `A_OBSERVE_DAYS=10` Schlusskurse NACH dem Hoch; `a_correction_
  observed=true`, sobald `min(A-Fenster) ≤ Hoch − A_RETRACE_MIN·W5-Strecke`
  (`A_RETRACE_MIN=0.382`), `false` bei vollem Fenster ohne Trigger, `null` = offen.
  Schreibt **ausschließlich** `a_correction_observed`/`a_retrace_pct`/`a_observe_until`
  (Test `test_only_a_fields_touched`), deterministisch/idempotent. Braucht Kurse
  ÜBER `HORIZON_DAYS` hinaus, die über die Läufe akkumulieren (`price_sink` hält alle
  Universum-Closes). **Nie in `build_report`** → report.json/Score/Ranking unberührt.
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
- **„Ziel erreicht/überschritten" je Zeitebene (dieser PR, reines Frontend):**
  jede Zeitebenen-Zeile mit `target_zone` trägt einen kompakten `.tf-hint`-Chip
  (`data-tf-hint`, `data-zl`/`data-zh`). Schwellen **identisch** zum #28-Zonen-Badge
  (`_setZoneBadge`): Bezugskurs ≥ `ziel.low` → „Ziel erreicht", ≥ `ziel.high` →
  „Ziel überschritten", sonst `hidden`. `tfPanel(tf, structure, cardClose)` bekommt
  den Karten-Kurs als 3. Arg (Anfangszustand = Lauf-Schlusskurs `c.close`); `quotePatch`
  aktualisiert live via `card.querySelectorAll('[data-tf-hint]')` → `_setTfHint`
  (Zwilling von `_setZoneBadge`). EXT braucht **keinen** eigenen Chip: `ext.high ≥
  ziel.high`, ein Kurs ≥ `ext.high` zeigt also ohnehin „Ziel überschritten". Motiv:
  Pivot-Bestätigungs-Trägheit (Monatskerzen ±5 Balken) → alte Zählung zeigt „W3
  erwartet", obwohl der Kurs die Projektion längst durchlaufen hat (Live-Fall AMAT
  25.07.: Monat Ziel 296–391 bei Kurs 536). Methodik-Legende um genau diese
  Erklärung ergänzt. Revert = `.tf-hint`-CSS + Chip-Zweig in `tfPanel` + `_setTfHint`
  + die eine `quotePatch`-Zeile raus, `cardClose`-Arg entfällt.
- **Struktur-Befund (NUR Watchlist, #35):** additives Feld `structure`
  {`day`,`week`,`month`}, je Ebene `null` **oder** {`state`,`label`,
  `invalidation_price`,`mark_label`,`orientation_price`,`direction`}.
  `_classify_structure(prices, close)` (reine Logik, direkt testbar) → 5 `state`:
  `long_setup` / `impulse_running` / `impulse_complete` / `short_structure` /
  `no_structure`. Priorität kompletter Impuls (letzte 6 Pivots, `validate_impulse`)
  → Teil-Impuls bis W4 (5, `validate_partial_to_w4`) → Ende W2 (3). `_analyze_from_fetch`
  holt je Ebene EINEN Fetch und liefert (Long-Count, Struktur) — **kein** Doppelabruf.
  Gesetzt **nur** in `build_watchlist_entry` (+ Default in `_wl_base_entry`) →
  `build_market`/Score/Ranking/Sammlung unberührt (Tests). Frontend:
  `tfPanel(tf, structure)` zeigt bei null-Count den Struktur-Befund statt „kein Count".
- **Marke präzisiert + A-Orientierung (dieser PR):** `invalidation_price` = struktureller
  **Zählungs-Ungültigkeitspunkt**; `mark_label` sagt WELCHER Pivot das ist
  (`Impuls-Start` = P0 bei complete, `W1-Hoch` = P1 bei W4, `W1-Start` = P0 bei W2)
  — die nackte Zahl allein (z. B. PANW 155,73, > 50 % unter Kurs) wirkte sonst wie eine
  nahe Orientierung. Bei **`impulse_complete`** zusätzlich `orientation_price` = **W4-
  Extrem** (P4) als nahe **A-Ziel-Region** (typisches erstes Ziel der erwarteten
  Korrektur A; für PANW 320,59 — Kurs stand schon dort). Frontend `tfPanel` zeigt
  `mark_label`+Wert (statt nacktem „Marke") und, wenn vorhanden, „A-Ziel-Region ~<W4>".
  Ehrlichkeits-Sprache, **keine Wahrscheinlichkeit**.
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
  (menschlich, **07.12.2026**), `STATUS_REVIEW_WEEKDAY=0`, `EVAL_MIN_N=100`,
  `STALENESS_HOURS=30`.
  **VORMERKUNG für die Score-Überprüfung am 07.12.2026** (Befund 31.07.2026,
  read-only erhoben, nichts davon geändert): der **Invalidierungs-Bonus steht
  bei 55,4 % aller Kandidaten am Anschlag**, bei den Spitzenkandidaten
  praktisch immer — zwei der drei Score-Komponenten sind dort also konstant,
  und die **gesamte Streuung an der Spitze kommt allein aus dem
  Fibonacci-Bonus**. Der Score diskriminiert oben deutlich schwächer, als drei
  Komponenten vermuten lassen. Dazu: `end_of_c` steht in
  `SETUP_BASE_POINTS`, wird von `classify_setup` aber **nie erzeugt**.
- **Score-Alert typ-relativ (#24, berichtigt 31.07.2026):** IM Daily-Lauf, in `elliott_pipeline.main()`
  **nach** `update_forward_collection` (Episoden existieren) und **vor**
  `write_collection` (Flag persistiert). `fc.score_alert_edges(coll, report, run_date)`
  findet Kandidaten, die in ihrer Episode **neu** an der Schwelle IHRES
  Setup-Typs sind (`>=`, berechnet aus `config.score_alert_threshold(typ)`) (Record mit `last_seen == run_date`, Flag
  `score_alert_fired` noch None → feuern + Flag setzen), gebündelt →
  `notify.send_score_alert(NTFY_TOPIC, edges)` = **1 Push/Lauf**. Flanke,
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
- **Watchlist-Auto-Sync (dieser PR, ersetzt den #17-Button):** add/remove → lokal +
  `_wlScheduleSync` (Debounce `WL_SYNC_DEBOUNCE_MS=3000` → EIN Commit). `_wlSyncNow`
  ist **idempotent** (`JSON.stringify(_wlArr) === _wlSyncedJson` → kein PUT) und ruft
  `_ensureToken(_wlDoPut)`; gesperrte Session → Passwort-/Setup-Dialog (wie Recalculate),
  Änderung bleibt lokal + `#wl-sync`-Chip „noch nicht gesynct", synct beim nächsten
  Gelingen. `_wlDoPut` snapshot-basiert (PUT genau die erfasste Liste; 409/422 → sha
  frisch + **1× Retry**), setzt `_wlSyncedJson` erst bei `r.ok`; Erfolg = kurzer Toast
  „✓ Watchlist gesynct", Fehler → Chip bleibt, kein Retry-Sturm, kein Datenverlust.
  Baseline `_wlSyncedJson` = letzter Lauf (kein Auto-PUT beim Laden). Kein Button,
  kein Erklär-Absatz mehr (Hinweise situativ; Sofortkarte erklärt „nächster Lauf").
- **Watchlist-Kompakt-Grid (Squeeze-Vorbild, seit dieser PR):** `#wl-cards` ist ein
  `.wl-grid` aus `.wl-tile`-Kacheln (`wlTile`). Jede Kachel: `.wl-thead` (Mini-Donut
  `wlMiniDonut`/„—", Ticker, Trend-Punkt) + `.wl-tbody` mit der **vollen** Karte
  (`watchlistCard`/`_wlInstantCard`, unverändert). **Default eingeklappt**; Aufklappen
  setzt `[data-open]` (Kachel spannt die Reihe, kompakter Kopf ausgeblendet, „▴
  Einklappen"-Leiste). Zustand in `localStorage['elliott_wl_expanded']` (Ticker-Set);
  `_wlToggle` schaltet den DOM direkt (kein Re-Render) und ruft beim Öffnen
  `drawAllSparklines`. **Poll-Einheit bleibt `.card[data-ticker]`** (im Body) — der
  Tile-Wrapper trägt nur `data-tile`, also kein Doppel-Poll; der Trend-Punkt im Kopf
  ist statisch (nicht live). Neuer Ticker startet aufgeklappt (Sofortkarte #25).
  Kein-valider-Count → Kopf zeigt „—" (kein Fake-Score). Toggle/Remove via Delegation
  auf `#wl-cards` (`data-wl-toggle`/`data-wl-remove`).
- **Top-5-Historie in der Kachel (dieser PR):** `.wl-hist[data-hist]`-Platzhalter im
  Tile-Body; nach Collection-Load werden die Records in `_wlColl` gecacht und via
  `_wlInjectHistory` gefüllt (`_wlEpisodesFor` → neueste zuerst, max 3, `_wlHistRow`
  mit `episodeStatus`-Symbolen). Klick (`data-ep-i`) → `openEpisodeFromWatchlist` →
  bestehende `showEpisodeDetail`; „…N weitere" → `openBacktesting`. Kein Karten-Re-
  Render (Quotes/Expand bleiben); fail-soft ohne Episoden. `tfPanel(tf, structure)`
  zeigt bei null-Count den Struktur-Befund (Part B) statt „kein valider Long-Count".
- **Menü (☰, 7 Punkte, Squeeze-analog):** `☰`-Button sitzt **oben rechts**
  (Squeeze-Position) neben Titel/Stand-Zeile (`.head-row` flex), das `.menu-panel`
  öffnet **rechtsbündig** (`position:fixed; top:64px; right:12px`). Reihenfolge
  `mi-reload` (**NEU**, primär hervorgehoben) · `mi-recalc` · `mi-backtesting` ·
  `mi-methodik` · `mi-validierung` · `mi-laufstatus` · Trenner · `mi-lock`
  („Sperren", abgesetzt am Fuß). Jeder Eintrag = abgerundete **Icon-Kachel** (`.mi-tile`, Sparkline-Grün
  `--grn`) + `.mi-label`; Icons als **inline-SVG** (lucide-Vorbild, keine externe
  Lib). **`mi-reload`** ruft `refresh({announce:true})` (Cache-Buster/no-store) —
  der frühere Header-Button „↻ Neu laden" ist **entfallen** (`refresh` hält den
  optionalen `#reload`-Button-Block fail-soft). `_setRecalcBtn` ändert nur noch das
  `.mi-label` (Kachel bleibt). Escape-Priorität: Token-Modal > Menü > Info-Overlay
  > Backtesting.
- **Recalculate-Status-Banner (`#recalc-banner`, seit dieser PR):** nach 204 startet
  `_startRecalcWatch` einen **eigenen** Poll-/Tick-Timer (`_rcPollTimer`/`_rcTick`,
  getrennt von `quotePollers`). Fertig-Erkennung über den **Report-Stand**
  (`run_timestamp_utc` ≠ Baseline `_lastReportTs`), nicht die Actions-API (tokenlos).
  Konstanten `RECALC_POLL_MS=10000` / `RECALC_TIMEOUT_MS=600000`. Erfolg →
  `_renderReport(r)` (dieselbe In-place-Render-Funktion wie `refresh()`, gesetzt auch
  `_lastReportTs`). Feiertags-Kurzschluss über `MARKET_FULL_CLOSURE`;
  visibilitychange-Pause; alles fail-soft.
- **Konstanten:** `EVAL_MIN_N = 100`, `COLLECTION_START = '22.07.2026'` (N×-Tooltip,
  an die Präregistrierung gebunden), `STALENESS_HOURS`-Banner bei > 30 h.
- **Disclaimer (seit dieser PR):** kein Banner oben mehr — **statischer Footer-Text
  am Seitenende** (`<footer>`, gedämpft, zentriert): Informationszwecke · keine
  Anlageberatung · Scores heuristisch·unvalidiert. Kein Einklapp-Mechanismus,
  `elliott_disc_collapsed`/`.disclaimer`/`.disc-*` + JS entfallen. (Vorher #23:
  einklappbarer Kopf-Banner.)
- **Chart-Link:** `chartUrl` — US `/stocks/{lower}/`, DE `/quote/etr/{ohne .DE}/`
  (Best-Guess, unverifiziert).

### Merge-Policy & QS-Kette
- **Draft-PR → Guardian-Zweitblick (bei Workflow/Schema/Score/Filter/Pipeline) →
  Manual-Merge durch Easy → Live-Verify.** **Keine Vorschau-Screenshots zur
  Optik-Freigabe mehr** (Easy-Regel 25.07., s. Abschnitt 8) — Optik am Live-Deploy.
  Reine Doku-/Daten-PRs: kein Guardian; Doku-only darf bei grünem CI self-merge.
- Guardian = **Zweitblick, kein Gatekeeper** (Urteil OK / Nits / Blocker).
- **QS-Kette:** CI (`test`, required empfohlen) + Guardian + Easy.
- **Grün ist erst grün, wenn Lauf-ID und Head-SHA genannt sind und der SHA der
  aktuelle Zweigkopf ist** — ein PR kann **ungeprüft-leer** dastehen statt
  ungeprüft-rot (Easy-Regel 07.08., s. Abschnitte 7 und 8).
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
- **Populations-Regel „veralteter Kurs-Stand" (05.08.2026, Registry-Eintrag):**
  hängt ein Markt hinter dem letzten erwarteten Handelstag zurück, legt der Lauf
  für **diesen Markt** keine neuen Episoden an — ein Setup, das es bei aktuellen
  Kursen nicht gäbe, gehört nicht in die Population. Bestehende Episoden laufen
  über den Tag hinweg **durch** (markt-bewusste Anker), die Reifung bleibt
  bewusst **ungegated** (idempotent, korrigiert sich am Folgetag selbst).
- **✅ AUFGELÖST am 08.08.2026 — die Marker-Entscheidung ist gefallen
  (Registry-Eintrag 08.08.).** Bis dahin galt hier: „zwei Marker warten auf EINE
  Entscheidung, vor der ersten Auswertung" (`episode_split_suspect` #68 und
  `stale_market_suspect` 05.08.; ab 07.08. kam `in_session_creation` als dritter
  dazu). **Neu und verbindlich: der Stichtag berichtet ZWEI Rechnungen** —
  **(a)** Primärauswertung über **alle** auswertbaren Records und **(b)**
  Sensitivitätsauswertung über dieselben Records **ohne jeden**, der
  mindestens **einen** Marker trägt. Beide **nebeneinander**; eine Abweichung im
  Verdikt wird ausgewiesen und **nicht** nachträglich zugunsten einer Seite
  entschieden. **Keine weiteren Varianten post hoc.** Entschieden bei **15 von
  100** auswertbaren Records, **vor** Sichtbarkeit jeder Ergebniszahl — damit
  die Regel nicht in Sichtweite der Ergebnisse zurechtgelegt werden kann
  (Vorbild: Sensitivitätsanalysen in klinischen Studien werden vorab
  festgeschrieben). **Künftige Marker fallen automatisch unter dieselbe Regel**,
  ohne neue Wiedervorlage. Kein Record wird entfernt oder verändert; alle Marker
  bleiben zählungs-neutral, `evaluate.py` ist als v1 eingefroren.
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

**AUSWERTUNGS-PROGRAMM (v1, 28.07.2026, blind gebaut):** `scripts/evaluate.py`
setzt genau dieses Register um. Aufruf:

```bash
python3 scripts/evaluate.py                 # offiziell — verweigert unter n<100
python3 scripts/evaluate.py --vorschau      # Zwischenstand, ausdrücklich NICHT gültig
python3 scripts/evaluate.py --kurse-holen   # NUR die Kursbasis des Benchmarks holen
```

Standardpfade: Sammlung `data/forward_collection.json`, Kursbasis
`data/eval_prices.json`, Ergebnis `data/evaluation/ergebnis.json`. Es läuft
**nie** im Tageslauf, sendet **keinen** Push und schreibt weder Sammlung noch
Report. Ohne Kursbasis meldet der Zufalls-Vergleich „nicht durchführbar“ —
und ohne ihn kann ein Ergebnis nie „belegt“ lauten. Seed `20260728` fest,
zwei Läufe ergeben dieselbe Datei. Details + die zwei bewusst getroffenen
Operationalisierungen (Kursbasis, Holm auf ein Intervall-Kriterium) stehen im
Registry-Eintrag vom 28.07.

**Datumsanker:** Sammlungs-Beginn/`COLLECTION_START` **22.07.2026**; **Universums-
Wechsel 23.07.2026** (99→361, Zählweise unverändert, im Register geloggt).

**Aktueller Zählerstand:** committete `forward_collection.json` = **0 Records** bis
zum ersten Lauf nach dem Persistenz-Fix (#21). Ab #21 akkumuliert die Sammlung —
der erste echte Lauf schreibt ~10 Records, danach wächst n Lauf für Lauf. (Live-
Beleg = Abschnitt 3.)

---

## 7. LESSONS (teuer gelernt)

- **CSS-Klassennamen kollidieren still** (28.07., Validierungs-Seite):
  Eine neue Regel `.val-note` traf zusätzlich ein **bestehendes** Element
  im Validierungs-Panel der Hauptseite (`<span class="val-note">`) — die
  alte Regel war `.validation .val-note` gescopet, die neue nicht. Im
  Headless-Test fiel es auf, weil der Selektor den falschen Text zurückgab.
  Konsequenz wie bei den SVG-ids in #48: **neue Klassen bekommen ein
  eigenes Präfix** (hier `vsum-`), statt sich auf ein freies Wort zu
  verlassen. Vor jeder neuen Klasse einmal greppen.

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
- **FLACHER KLON IN DER SANDBOX (07.08.2026) — `git fetch --unshallow` VOR
  jeder Historien-Analyse.** Die Sandbox klont mit `--depth 1`. `git log -- data/report.json`
  zeigt dann **22 statt 70** Ständen, `data/forward_collection.json` **24 statt
  64** — und zwar **ohne Fehler, ohne Warnung, ohne Lücke im Ergebnis**. Jede
  Replay-Rechnung läuft still auf einem Drittel der Daten und liefert eine
  plausible, falsche Zahl. Das ist **exakt die #68-Falle**, nur eine Ebene
  weiter: dort klonte `actions/checkout` flach und der Split-Replay fand einen
  Stand statt 44; behoben wurde damals `ci.yml` (`fetch-depth: 0`) — die
  **Sandbox** blieb flach und hat es beim In-Session-Befund prompt wieder
  getan. Prüfen mit `git rev-parse --is-shallow-repository`. Wer eine
  Historien-Zahl nennt, nennt auch die Zahl der gesehenen Stände. Die beiden
  Skripte `mark_in_session_creation.py --verify-history` und
  `collect_in_session_evidence.py` brechen unter 40 sichtbaren Ständen mit
  Grund ab, statt zu rechnen; die zugehörigen Tests **überspringen mit Grund**
  statt still leer grün zu sein (`braucht_historie`).
- **MUTATIONSPROBEN: `__pycache__` VOR JEDEM LAUF WEG (07.08.2026).** Eine
  Probe meldete **17 von 17 rot** — falsch. Die Mutation
  `"close": (16, 0)` → `(20, 0)` ist **längengleich**, und das Zurückspielen
  der Sicherungskopie ergab dieselbe mtime-Sekunde: Python hielt den
  **mutierten Bytecode** für gültig und lud ihn weiter, obwohl die Quelle
  längst wieder korrekt war. Sichtbar wurde es erst, weil danach 20 fremde
  Tests umfielen, während `git diff` auf `scripts/` **leer** war — Quelle
  `(16, 0)`, Laufzeit `(20, 0)`. Wäre es umgekehrt gelaufen, hätte eine
  überlebende Mutation als „rot" gegolten und eine echte Testlücke verdeckt.
  **Regel:** vor jeder Mutationsreihe
  `find . -name __pycache__ -type d -not -path './.git/*' -exec rm -rf {} +`
  und die Reihe mit **`PYTHONDONTWRITEBYTECODE=1`** fahren. Der Neulauf ergab
  dann das ehrliche Bild (17 rot, 2 äquivalent, 1 selbst falsch gebaut).
  **Verallgemeinert:** eine Mess-Vorrichtung, die ihr eigenes Ergebnis
  verfälschen kann, gehört genauso geprüft wie das Gemessene.
- **EINE ÜBERLEBENDE MUTATION KANN VON EINER ZWEITEN LAUTEN STELLE VERDECKT
  WERDEN (08.08.2026, #88).** Die Probe „`warne_bei_import_fehler()` aus
  `notify.main()` entfernt" blieb **grün**, obwohl der Ende-zu-Ende-Test genau
  diese Meldung prüft — weil `review_due` bei fehlendem `SCORE_REVIEW_BY`
  **seinerseits** warnt und dieselben Wörter (`WARNUNG`, der Grund, der
  Feldname) schon lieferte. Der Test prüfte also „irgendwer meldet es", nicht
  „**diese** Stelle meldet es". **Regel:** Wenn zwei Stellen dasselbe melden
  können, muss die Zusicherung an einer **Zeichenfolge hängen, die nur die
  geprüfte Stelle erzeugen kann** — hier der Sammel-Bericht über
  `forward_collection` und die Ersatzwert-Liste. Nachgezogen, Probe danach rot.
  **Verallgemeinert:** Redundante Sicherungen sind gut fürs System und
  gefährlich für den Test — sie machen Zusicherungen unschärfer, ohne dass es
  auffällt.
- **EINE AUFZÄHLUNG IM KOMMENTAR ALTERT LAUTLOS (08.08.2026, #88).** Mein
  erster Entwurf von `repo_path.py` schrieb „drei Kopien" — nachgezählt waren es
  **neun**. Wer die Zahl nicht nachzählt, schreibt eine falsche Zusage ins Repo,
  und die nächste Session glaubt sie. Konsequenz: die Liste steht jetzt in einem
  maschinenlesbaren Block (`EIGENKOPIEN-ANFANG`/`-ENDE`), und ein Test
  vergleicht sie mit den tatsächlichen Dateien. **Regel:** Jede Zahl oder Liste
  in einer Dokumentation, die aus dem Code ableitbar ist, wird entweder aus dem
  Code abgeleitet oder von einem Test festgehalten — sonst gehört sie nicht hin.
- **Proxy-Rechte:** `workflow_dispatch` geht; Branch-Delete / Branch-Protection-
  Änderungen → **403**. Nicht dagegen anrennen.
- **Sandbox erreicht kein Yahoo/EDGAR/externe Hosts** → alles Externe bleibt
  **Live-Verify durch Easy** (Abschnitt 3); Playwright-Tests mocken die GitHub-API.
- **iOS-Cache:** Design-Änderungen greifen sofort, **Daten** hängen im Safari-Cache
  → `cache:'no-store'` + Cache-Buster; **kein Service Worker**. `localStorage`
  räumt iOS-WebKit nach **~7 Tagen** Inaktivität (Token/Watchlist ggf. neu setzen).
- **Sequenz-Regel:** pro Runde **ein** Anzeige-/Optik-PR (Review-Last klein halten).
- **Keine Vorschau-Screenshots mehr (Easy-Regel 25.07.):** Es werden **keine**
  Vorschau-Screenshots/Renderings zur Optik-**Freigabe** mehr erzeugt und an Easy
  geschickt — die Optik wird am **Live-Deploy** beurteilt. Verifikations-Renders
  (Playwright) für die **eigenen** Checks bleiben erlaubt, wandern aber **nicht** in
  den Chat. Optik-PRs laufen als Draft → Manual-Merge durch Easy → Live-Verify.
  (Ersetzt die frühere „Draft-Bild-Freigabe"-Runde.)
- **Alert-Flanke statt Zustand (Schwester-Repo PR #471, 23.07.):** Cooldowns/
  Schwellen ohne **Flanken-Logik** re-alarmieren, solange der Zustand anhält →
  Push-Flut. Regel: edge-triggered (einmal je Episode, Flag), NICHT
  level-triggered. Beim Score-Alert an die vorhandene Episoden-Erkennung koppeln,
  **kein** zweites State-System.
- **Determinismus:** `report.json` byte-identisch belassen (Realdaten macht nur CI);
  nicht-deterministische Felder (`generated_in_seconds`, `appearance_count`) nur in
  `main` setzen, nicht in `build_report` (Tests bleiben deterministisch).
- **Ein Test, dessen Ergebnis davon abhängt, WO er läuft, ist kein Test**
  (06./07.08.2026). Die CI auf `main` war wochenlang dauerrot, ohne dass es
  auffiel — der grüne Haken hängt am PR, und niemand sieht sich die Push-Läufe
  an. Ursache war kein Produktionsfehler, sondern ein **Umgebungsleck im Test**
  (`GITHUB_REF` → Herzschlag feuerte mitten im Unit-Test). Merksätze: (1)
  Umgebungsvariablen des Produktionscodes gehören **zentral** neutralisiert
  (autouse-Fixture in `conftest.py`), nicht je Testdatei; (2) ein Wächter gegen
  die Wiederholung muss die **Sprache** kennen (AST), nicht nur ein Muster; (3)
  wo eine statische Prüfung nicht hinreicht, muss sie **laut** werden statt
  still Vollständigkeit zu behaupten; (4) der Regressionstest muss die echte
  Bedingung tragen — hier ein **Kindprozess** mit gesetzter Variable.
  <sub>Volle Herleitung samt Zahlen und Mutationsproben: Archiv.</sub>
- **Ein leeres CI-Feld heißt nicht „läuft noch"** (07.08.2026). Zwei Draft-PRs
  standen 16 bzw. 8 Stunden ohne einen einzigen Lauf da. Meine beiden
  Ursachen-Erklärungen waren **falsch** und wurden binnen Minuten widerlegt.
  Belegt ist nur die Beobachtung, nicht die Ursache. Die Falle liegt im
  **Ablesen**: `get_status` liest die *Commit-Status*-API, `ci.yml` erzeugt aber
  *Check-Runs* — `total_count: 0` heißt dort „falsche Frage gestellt", und
  `mergeable_state: unstable` sieht aus wie „Checks laufen noch", heißt aber „es
  gibt keine". Verlässlich sind die nach `branch` gefilterte Lauf-Liste und
  `git ls-remote`. Steht ein PR ohne Lauf da: Push auf den Zweig **oder**
  Schließen + sofortiges Wiederöffnen erzeugt ihn.
  <sub>Volle Zeitleiste: Archiv.</sub>

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
- **Ready-Meldung nur mit Lauf-ID, Head-SHA und Zweigkopf-Abgleich (Easy-Regel
  07.08., stehend):** Wer einen PR als geprüft meldet, nennt **die Lauf-ID**, **den
  Head-SHA, gegen den die CI gelaufen ist**, und **bestätigt, dass dieser SHA der
  aktuelle Zweigkopf ist** (`git ls-remote origin refs/heads/<zweig>`). Ohne alle
  drei Angaben ist es keine Ready-Meldung.
  **Grund (am 07.08. teuer gelernt, s. Abschnitt 7):** ein PR kann **ungeprüft-leer**
  dastehen statt ungeprüft-rot — am 06.08. abends über Stunden, aus einer Ursache,
  die von hier aus nicht feststellbar ist. `mergeable_state: unstable` und ein leeres
  Ampelfeld sehen dabei aus wie „Checks laufen noch", heißen aber „es gibt keine".
  Ein grüner Lauf gegen einen **überholten** SHA ist derselbe Trugschluss in der
  zweiten Form. Die Regel greift, **ohne** dass man die Ursache kennen muss.
- **Absolute Vorsicht, kein Risiko:** additiv, fail-soft, `report.json`/Score/
  Ranking/Population unberührt, Revert-Weg im PR-Text.

---

*Pflege: bei jedem Merge Abschnitte 2–4 (mind.) aktualisieren. Siehe README.*
