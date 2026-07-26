"""Agent-Kommentar v1 (KI-Entscheidung Easy 26.07.2026) — nächtlicher LLM-Kommentar
je Markt-Top-5-Karte: Klartext-Lesart + stärkstes Gegenargument + Concern-Level.

REINE KOMMENTAR-EBENE — beweisbar KEIN Score-/Ranking-/Filter-Effekt:
- Der Schritt läuft NACH `build_report` (also nach Sortierung, Top-N-Schnitt und
  allen Filtern) und schreibt ausschließlich das additive Feld `agent_comment`.
- Nur die FINALEN Markt-Top-5 (~10 Aufrufe/Lauf). Watchlist ausdrücklich AUSGENOMMEN.

Adaption der Squeeze-KI unter Elliott-Disziplin. Bewusst NICHT übernommen:
Agent-Boost ins Ranking (Squeeze-Re-Test: kein Edge), KI-Score, Stunden-Ticks.
NEU gegenüber Squeeze: das Urteil wird MESSBAR eingefroren (`agent_concern_level`
bei Episoden-Anlage) — die n≥100-Auswertung prüft, ob agent-kritisierte Setups
schlechter treffen.

FAIL-SOFT TOTAL (ntfy-Muster): fehlendes `ANTHROPIC_API_KEY` → no-op + Log-Zeile;
jeder API-/Parse-Fehler → `agent_comment = None`, der Lauf läuft normal weiter.
Der Key wird NIE geloggt (nur ein „gesetzt/fehlt"-Hinweis).

Der Prompt ist eine DATIERTE DEFINITION (siehe docs/validation_registry.md,
„Agent-Kommentar v1") — Änderungen erzeugen eine neue, datierte Version.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

# --- Benannte Konstanten (Registry-relevant) --------------------------------
AGENT_MODEL = "claude-haiku-4-5-20251001"   # günstig genug für 3 Sätze
AGENT_TEMPERATURE = 0.0                      # mildert Nichtdeterminismus (garantiert ihn nicht)
AGENT_MAX_TOKENS = 500
AGENT_TIMEOUT_S = 30
AGENT_PARSE_RETRIES = 1                      # 1 Retry bei Parse-Fehler, dann null
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CONCERN_LEVELS = ("none", "low", "high")

# Der WÖRTLICHE Prompt (datierte Definition — nie stillschweigend ändern).
SYSTEM_PROMPT = (
    "Du bist ein nüchterner Elliott-Wellen-Analyst und kommentierst eine bereits "
    "fertig berechnete Zählung. Du bewertest NICHT neu und vergibst KEINE Punkte — "
    "du erklärst und widersprichst. Sprich Klartext auf Deutsch, ohne Werbe- oder "
    "Empfehlungssprache, ohne Wahrscheinlichkeits- oder Trefferquoten-Behauptungen, "
    "ohne Kauf-/Verkaufsempfehlung. Nutze AUSSCHLIESSLICH die gelieferten Zahlen; "
    "erfinde keine Kurse, Nachrichten oder Fundamentaldaten. "
    "Antworte NUR mit einem JSON-Objekt, ohne Markdown-Codefence, mit exakt den "
    "Schlüsseln: lesart (2-3 Sätze: was diese Zählung im Klartext behauptet), "
    "gegenargument (1-2 Sätze: der stärkste Einwand, der sich AUS DEN DATEN ergibt "
    "— z. B. Mehrdeutigkeit, schwaches W3-Volumen, weite Invalidierung, fehlende "
    "Alternation), concern_level (genau einer der Werte \"none\", \"low\", \"high\" — "
    "wie stark die Daten der Zählung widersprechen)."
)

USER_TEMPLATE = (
    "Kommentiere diese Elliott-Zählung. Alle Angaben stammen aus unserer eigenen "
    "Pipeline (heuristisch, unvalidiert):\n\n{facts}"
)


def _log(msg: str) -> None:
    print(f"[agent] {msg}", flush=True)


# Dünne HTTP-Schicht — Tests ersetzen sie ohne Netz (wie notify._post).
def _post(url: str, payload: Dict, headers: Dict, timeout: int) -> Dict:  # pragma: no cover
    import urllib.request  # noqa: WPS433 — stdlib, keine neue Dependency

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_facts(entry: Dict) -> Dict:
    """Die AN DAS LLM gegebenen Fakten — ausschließlich eigene Pipeline-Felder
    des Kandidaten (keine externen Fetches in v1). Kompakt und stabil sortiert."""
    tz = entry.get("target_zone") or {}
    ez = entry.get("target_zone_extended") or {}
    alt = entry.get("alt_count_v2") or entry.get("alt_count") or {}
    facts = {
        "ticker": entry.get("ticker"),
        "name": entry.get("company_name") or entry.get("name"),
        "sektor": entry.get("sector"),
        "kurs": entry.get("close"),
        "tagesveraenderung_pct": entry.get("change_pct"),
        "zaehlung": entry.get("count_label"),
        "invalidierung": entry.get("invalidation_price"),
        "zielzone": [tz.get("low"), tz.get("high")] if tz else None,
        "extension": [ez.get("low"), ez.get("high")] if ez else None,
        "score_heuristisch": entry.get("score_heuristic"),
        "valide_zaehlungen_v2": entry.get("valid_count_total_v2"),
        "alternative_zaehlung": alt.get("count_label"),
        "volumen_w3_zu_w1": entry.get("vol_ratio_w3_w1"),
        "volumen_w4_zu_w3": entry.get("vol_ratio_w4_w3"),
        "volumen_w2_zu_w1": entry.get("vol_ratio_w2_w1"),
        "konfluenz": entry.get("confluence"),
        "top5_erscheinungen": entry.get("appearance_count"),
    }
    # Alternation (W2/W4-Charakter) aus DENSELBEN eingefrorenen Pivots wie die
    # Sammlung — geteilte Definition statt zweiter Rechenweg. Fail-soft.
    try:
        import forward_collection as _fc  # noqa: WPS433 — lazy, hält Tests leicht

        a = _fc._alternation_fields(entry.get("chart_points"),
                                    entry.get("count_wave_labels"))
        facts["w2_retrace_pct"] = a.get("w2_retrace_pct")
        facts["w4_retrace_pct"] = a.get("w4_retrace_pct")
        facts["alternation_beobachtet"] = a.get("alternation_observed")
    except Exception:  # noqa: BLE001 — Fakten sind additiv, nie kritisch
        pass
    return {k: v for k, v in facts.items() if v is not None}


def _parse_reply(raw: str) -> Optional[Dict]:
    """Erzwingt die Struktur: JSON mit lesart/gegenargument/concern_level.
    Toleriert einen versehentlichen Markdown-Codefence. None = Parse-Fehler."""
    txt = (raw or "").strip()
    if txt.startswith("```"):
        txt = txt.split("```")[1] if "```" in txt[3:] else txt[3:]
        txt = txt[4:] if txt.lower().startswith("json") else txt
        txt = txt.strip()
    try:
        obj = json.loads(txt)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, dict):
        return None
    lesart = obj.get("lesart")
    gegen = obj.get("gegenargument")
    level = obj.get("concern_level")
    if not isinstance(lesart, str) or not lesart.strip():
        return None
    if not isinstance(gegen, str) or not gegen.strip():
        return None
    if level not in CONCERN_LEVELS:
        return None
    return {"lesart": lesart.strip(), "gegenargument": gegen.strip(),
            "concern_level": level}


def comment_for(entry: Dict, api_key: str, now_iso: str) -> Tuple[Optional[Dict], int, int]:
    """EIN Aufruf je Kandidat. Rückgabe (agent_comment|None, in_tokens, out_tokens).

    Parse-Fehler → AGENT_PARSE_RETRIES Wiederholung(en), dann None. Jeder Fehler
    ist fail-soft (None) und bricht den Lauf NIE."""
    payload = {
        "model": AGENT_MODEL,
        "max_tokens": AGENT_MAX_TOKENS,
        "temperature": AGENT_TEMPERATURE,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": USER_TEMPLATE.format(
            facts=json.dumps(build_facts(entry), ensure_ascii=False, sort_keys=True))}],
    }
    headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
    tin = tout = 0
    for attempt in range(AGENT_PARSE_RETRIES + 1):
        try:
            resp = _post(ANTHROPIC_URL, payload, headers, AGENT_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 — API-Fehler bricht NIE den Lauf
            _log(f"{entry.get('ticker')}: API-Fehler (fail-soft): {type(exc).__name__}: {exc}")
            return None, tin, tout
        usage = (resp or {}).get("usage") or {}
        tin += int(usage.get("input_tokens") or 0)
        tout += int(usage.get("output_tokens") or 0)
        blocks = (resp or {}).get("content") or []
        raw = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        parsed = _parse_reply(raw)
        if parsed is not None:
            parsed.update({"model": AGENT_MODEL, "generated_at": now_iso})
            return parsed, tin, tout
        _log(f"{entry.get('ticker')}: Parse-Fehler (Versuch {attempt + 1})")
    return None, tin, tout


def annotate_agent_comments(report: Dict, api_key: Optional[str], now_iso: str) -> Dict:
    """Setzt `agent_comment` auf den FINALEN Markt-Top-5 (Watchlist ausgenommen).

    Läuft NACH dem Ranking und ist rein additiv — Score/Ranking/Filter/Population
    bleiben unberührt. Ohne Key: no-op (Feld gar nicht gesetzt) + Log-Zeile.
    Rückgabe: Diag-Zähler (auch fürs Kosten-Log)."""
    diag = {"kandidaten": 0, "kommentare": 0, "input_tokens": 0, "output_tokens": 0}
    if not api_key:
        _log("kein ANTHROPIC_API_KEY gesetzt → kein Agent-Kommentar (graceful).")
        return diag
    for mk, market in (report.get("markets") or {}).items():
        for entry in (market.get("candidates") or []):
            diag["kandidaten"] += 1
            try:
                comment, tin, tout = comment_for(entry, api_key, now_iso)
            except Exception as exc:  # noqa: BLE001 — doppelt genäht
                _log(f"{entry.get('ticker')}: unerwarteter Fehler (fail-soft): "
                     f"{type(exc).__name__}: {exc}")
                comment, tin, tout = None, 0, 0
            diag["input_tokens"] += tin
            diag["output_tokens"] += tout
            entry["agent_comment"] = comment
            if comment is not None:
                diag["kommentare"] += 1
    _log(f"Kommentare {diag['kommentare']}/{diag['kandidaten']} · Tokens "
         f"in={diag['input_tokens']} out={diag['output_tokens']} · Modell {AGENT_MODEL}")
    return diag
