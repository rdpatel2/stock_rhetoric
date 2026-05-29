"""Ollama wrapper — produces prose around the computed numbers.

The prompt sends fully-structured numeric facts and asks for prose only. The render
layer prints **our** numbers, not the LLM's. This separates facts from interpretation.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

import ollama


_DEBUG_DIR = Path.home() / ".cache" / "stock_rhetoric" / "llm_debug"

from .aggregator import SentimentBundle
from .financials import Financials
from .peers import PeerSet
from .risk import RiskFlag
from .scoring import Scorecard
from .trends import TrendReport

load_dotenv()

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Hard ceiling on the LLM call. If the model is large or the hardware slow,
# the prose is skipped rather than holding the report hostage.
OLLAMA_TIMEOUT_S = float(os.environ.get("OLLAMA_TIMEOUT_S", "90"))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")


@dataclass
class Narrative:
    executive_summary: str
    bullish: list[str]
    bearish: list[str]
    valuation_paragraph: str
    balance_sheet_paragraph: str
    cash_flow_paragraph: str
    competitive_paragraph: str
    direction: str          # "BUY" | "HOLD" | "SELL"
    confidence: str         # "Low" | "Medium" | "High"
    rationale: str

    @classmethod
    def empty(cls, reason: str = "LLM unavailable") -> "Narrative":
        return cls(
            executive_summary=f"[{reason}]",
            bullish=[],
            bearish=[],
            valuation_paragraph="",
            balance_sheet_paragraph="",
            cash_flow_paragraph="",
            competitive_paragraph="",
            direction="HOLD",
            confidence="Low",
            rationale=f"Narrative skipped: {reason}.",
        )


SYSTEM_PROMPT = """You are an equity research writer. Given pre-computed numbers and
headlines for one company, write a concise synthesis. Never invent numbers.

Output EXACTLY this format, nothing else (no preamble, no markdown):

SUMMARY: <2-3 sentences>
BULL: <one bullet>
BULL: <one bullet>
BULL: <one bullet>
BEAR: <one bullet>
BEAR: <one bullet>
BEAR: <one bullet>
DIRECTION: <BUY or HOLD or SELL>
CONFIDENCE: <Low or Medium or High>
RATIONALE: <one sentence>
"""

PARAGRAPHS_PROMPT = """You are an equity research writer. Given pre-computed numbers,
write four short paragraphs. Never invent numbers. Output EXACTLY:

VALUATION: <2 sentences>
BALANCE_SHEET: <2 sentences>
CASH_FLOW: <2 sentences>
COMPETITIVE: <2 sentences>
"""


def _pct(v: Optional[float]) -> Optional[str]:
    return None if v is None else f"{v * 100:.2f}%"


def _build_facts(
    fin: Financials,
    trends: TrendReport,
    peers: Optional[PeerSet],
    scorecard: Scorecard,
    flags: list[RiskFlag],
    sentiment: SentimentBundle,
) -> dict:
    """Compact facts dict for the LLM. Kept small to keep generation fast."""
    s = fin.stats
    peer_pe = peers.medians.get("pe") if peers else None
    peer_om = peers.medians.get("operating_margin") if peers else None
    return {
        "co": f"{fin.company.name} ({fin.company.ticker}) — {fin.company.industry or fin.company.sector or ''}",
        "metrics": {
            "pe": s.pe,
            "fwd_pe": s.forward_pe,
            "peg": s.peg,
            "ev_ebitda": s.ev_ebitda,
            "p_to_s": s.price_to_sales,
            "fcf_yield": _pct(s.fcf_yield),
            "gross_margin": _pct(s.gross_margin),
            "op_margin": _pct(s.operating_margin),
            "net_margin": _pct(s.net_margin),
            "roe": _pct(s.roe),
            "roic": _pct(s.roic),
            "d_e": s.debt_to_equity,
            "current_ratio": s.current_ratio,
            "div_yield": _pct(s.dividend_yield),
        },
        "vs_peer": {
            "pe_vs_peer": f"{s.pe:.1f} vs {peer_pe:.1f}" if (s.pe and peer_pe) else None,
            "op_margin_vs_peer": f"{s.operating_margin * 100:.1f}% vs {peer_om * 100:.1f}%" if (s.operating_margin and peer_om) else None,
        },
        "trends": {
            "rev_yoy": _pct(trends.revenue.yoy),
            "rev_cagr_3y": _pct(trends.revenue.cagr_3y),
            "eps_yoy": _pct(trends.eps_diluted.yoy),
            "fcf_yoy": _pct(trends.free_cash_flow.yoy),
            "op_margin_dir": trends.operating_margin.direction,
        },
        "scores": {
            "overall": round(scorecard.overall) if scorecard.overall is not None else None,
            "band": scorecard.band,
            "by_category": {c.name: round(c.score) if c.score is not None else None for c in scorecard.categories},
        },
        "risk_flags": [f.name for f in flags][:6],
        "coverage_tone": sentiment.tone_summary(),
        "headlines": [
            {"title": i.title[:120], "sentiment": i.sentiment_label}
            for i in sentiment.reliable[:4]
        ],
        "social_tone": [
            {"title": i.title[:120], "sentiment": i.sentiment_label}
            for i in sentiment.social[:2]
        ],
    }


def _call_groq_stream(
    system: str,
    user: str,
    model: str,
    timeout_s: float,
    num_predict: int,
    on_token: Optional[callable] = None,
) -> str:
    """Stream tokens from Groq API. Returns the full concatenated string."""
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY, timeout=timeout_s)
    parts: list[str] = []
    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        stream=True,
        max_tokens=num_predict,
        temperature=0.2,
    )
    for chunk in stream:
        tok = chunk.choices[0].delta.content or ""
        if tok:
            parts.append(tok)
            if on_token:
                on_token(tok)
    return "".join(parts)


def _call_ollama_stream(
    system: str,
    user: str,
    model: str,
    timeout_s: float,
    num_predict: int,
    on_token: Optional[callable] = None,
) -> str:
    """Stream tokens from Ollama. Returns the full concatenated string.

    Streaming + plain-text (no JSON-mode grammar constraint) is meaningfully faster
    on small CPU-bound models and gives the user visible progress.
    """
    client = ollama.Client(host=OLLAMA_HOST, timeout=timeout_s)
    parts: list[str] = []
    stream = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        stream=True,
        keep_alive="30m",  # keep model resident between tickers
        options={
            "temperature": 0.2,
            "num_predict": num_predict,
            "num_ctx": 4096,
        },
    )
    for chunk in stream:
        tok = _extract_chunk_content(chunk)
        if tok:
            parts.append(tok)
            if on_token:
                on_token(tok)
    return "".join(parts)


def _extract_chunk_content(chunk) -> str:
    """Pull the new-token text from an Ollama streaming chunk.

    ollama-python 0.6+ yields `ChatResponse` Pydantic models; older versions yielded
    dicts. Support both, plus the edge case where `message` may be a dict or model.
    """
    msg = None
    if hasattr(chunk, "message"):
        msg = chunk.message
    elif isinstance(chunk, dict):
        msg = chunk.get("message")
    if msg is None:
        return ""
    if hasattr(msg, "content"):
        return msg.content or ""
    if isinstance(msg, dict):
        return msg.get("content", "") or ""
    return ""


# Lenient line parser. Matches: optional markdown / list / numbering, the key, optional
# closing markdown, then a colon or dash. Case-insensitive — small models love lowercase.
_LINE_RE = re.compile(
    r"""^[\s>*#\-\d.\\]*               # leading markdown, bullets, numbers, escapes
        \*{0,2}\s*                     # optional bold open
        (?P<key>[A-Za-z_][A-Za-z_ ]{1,30}?)   # the key
        \s*\*{0,2}                     # optional bold close
        \s*[:\-–—]\s*                  # separator (colon, hyphen, en/em dash)
        (?P<val>.*)$
    """,
    re.VERBOSE,
)

# Map model output keys (case-insensitive) to our canonical names.
_KEY_ALIASES = {
    "summary": "SUMMARY", "executive summary": "SUMMARY", "exec summary": "SUMMARY",
    "bull": "BULL", "bullish": "BULL", "bull case": "BULL", "pros": "BULL",
    "bear": "BEAR", "bearish": "BEAR", "bear case": "BEAR", "cons": "BEAR",
    "direction": "DIRECTION", "recommendation": "DIRECTION", "verdict": "DIRECTION",
    "confidence": "CONFIDENCE", "confidence level": "CONFIDENCE",
    "rationale": "RATIONALE", "reasoning": "RATIONALE", "reason": "RATIONALE",
    "valuation": "VALUATION", "valuation paragraph": "VALUATION",
    "balance sheet": "BALANCE_SHEET", "balance_sheet": "BALANCE_SHEET",
    "cash flow": "CASH_FLOW", "cash_flow": "CASH_FLOW", "cashflow": "CASH_FLOW",
    "competitive": "COMPETITIVE", "competitive positioning": "COMPETITIVE",
}

_MULTI_KEYS = {"BULL", "BEAR"}


def _dump_debug(ticker: str, model: str, raw: str) -> None:
    """Save the raw LLM response when parsing fails, so the user can inspect it."""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = _DEBUG_DIR / f"{ts}-{ticker}-{model.replace(':', '_').replace('/', '_')}.txt"
        path.write_text(raw)
    except Exception:
        pass


def _pick_one(value: str, choices: tuple, default: str) -> str:
    """Find the first choice that appears in `value` (case-insensitive)."""
    upper = value.upper()
    for c in choices:
        if c.upper() in upper:
            return c
    return default


def _parse_structured(text: str) -> dict[str, str | list[str]]:
    """Lenient parse of the delimited response. Falls back to JSON if no keys match."""
    result: dict[str, str | list[str]] = {}
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        raw_key = m.group("key").strip().lower()
        # Strip trailing markdown asterisks
        raw_key = raw_key.rstrip("*").strip()
        key = _KEY_ALIASES.get(raw_key)
        if not key:
            continue
        value = m.group("val").strip().strip("*").strip()
        if not value:
            continue
        if key in _MULTI_KEYS:
            result.setdefault(key, []).append(value)  # type: ignore[union-attr]
        else:
            # First non-empty wins for single-value fields
            result.setdefault(key, value)
    if result:
        return result

    # Fallback 1: the model emitted JSON despite the instruction.
    json_obj = _extract_json(text)
    if json_obj:
        return _from_json_shape(json_obj)
    return {}


def _extract_json(text: str) -> Optional[dict]:
    """Find the first balanced top-level JSON object in `text` and parse it."""
    # Try a strict parse first.
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    # Otherwise search for the first { ... } substring with balanced braces.
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _from_json_shape(obj: dict) -> dict[str, str | list[str]]:
    """Map a JSON object to our canonical key dict. Accepts both old and new field names."""
    out: dict[str, str | list[str]] = {}

    def first(*keys):
        for k in keys:
            if k in obj and obj[k]:
                return obj[k]
        return None

    if (v := first("executive_summary", "summary", "SUMMARY")):
        out["SUMMARY"] = str(v)
    if (v := first("bullish", "bull", "BULL", "pros")):
        out["BULL"] = [str(x) for x in v] if isinstance(v, list) else [str(v)]
    if (v := first("bearish", "bear", "BEAR", "cons")):
        out["BEAR"] = [str(x) for x in v] if isinstance(v, list) else [str(v)]
    if (v := first("direction", "DIRECTION", "recommendation", "verdict")):
        out["DIRECTION"] = str(v)
    if (v := first("confidence", "CONFIDENCE")):
        out["CONFIDENCE"] = str(v)
    if (v := first("rationale", "RATIONALE", "reasoning")):
        out["RATIONALE"] = str(v)
    if (v := first("valuation_paragraph", "valuation", "VALUATION")):
        out["VALUATION"] = str(v)
    if (v := first("balance_sheet_paragraph", "balance_sheet", "BALANCE_SHEET")):
        out["BALANCE_SHEET"] = str(v)
    if (v := first("cash_flow_paragraph", "cash_flow", "CASH_FLOW")):
        out["CASH_FLOW"] = str(v)
    if (v := first("competitive_paragraph", "competitive", "COMPETITIVE")):
        out["COMPETITIVE"] = str(v)
    return out


def narrate(
    fin: Financials,
    trends: TrendReport,
    peers: Optional[PeerSet],
    scorecard: Scorecard,
    flags: list[RiskFlag],
    sentiment: SentimentBundle,
    model: Optional[str] = None,
    timeout_s: float = OLLAMA_TIMEOUT_S,
    include_paragraphs: bool = False,
    on_token: Optional[callable] = None,
) -> Narrative:
    model = model or DEFAULT_MODEL
    """Default mode generates only the core synthesis (summary + bull/bear + direction).
    The four deep-dive paragraphs are skipped by default because they roughly double
    output tokens, which dominates total LLM latency on CPU."""
    facts = _build_facts(fin, trends, peers, scorecard, flags, sentiment)
    user_msg = json.dumps(facts, default=str)

    try:
        if GROQ_API_KEY:
            raw = _call_groq_stream(SYSTEM_PROMPT, user_msg, GROQ_MODEL, timeout_s, 350, on_token)
        else:
            raw = _call_ollama_stream(SYSTEM_PROMPT, user_msg, model, timeout_s, 350, on_token)
    except Exception as e:
        return Narrative.empty(f"LLM error: {e!s}")

    if not raw.strip():
        # No tokens captured. Either the model returned nothing or chunk extraction failed.
        _dump_debug(fin.company.ticker, model, "(empty response from Ollama)")
        return Narrative.empty(
            "Ollama returned an empty response — check `ollama logs` and confirm the model can run"
        )

    data = _parse_structured(raw)
    bullish = data.get("BULL") if isinstance(data.get("BULL"), list) else []
    bearish = data.get("BEAR") if isinstance(data.get("BEAR"), list) else []

    # If structured/JSON parsing returned nothing, the model produced free-form prose.
    # Don't throw it away — use it as the executive summary and save the raw response
    # so we can inspect what the model actually said.
    summary = str(data.get("SUMMARY", "")).strip()
    if not summary and not bullish and not bearish:
        summary = raw.strip()[:600]
        _dump_debug(fin.company.ticker, model, raw)

    direction_raw = str(data.get("DIRECTION", "")).upper()
    confidence_raw = str(data.get("CONFIDENCE", "")).title()

    nar = Narrative(
        executive_summary=summary,
        bullish=[str(x) for x in bullish][:5],
        bearish=[str(x) for x in bearish][:5],
        valuation_paragraph="",
        balance_sheet_paragraph="",
        cash_flow_paragraph="",
        competitive_paragraph="",
        direction=_pick_one(direction_raw, ("BUY", "HOLD", "SELL"), default="HOLD"),
        confidence=_pick_one(confidence_raw, ("Low", "Medium", "High"), default="Low"),
        rationale=str(data.get("RATIONALE", "")),
    )

    if include_paragraphs:
        try:
            if GROQ_API_KEY:
                extras_raw = _call_groq_stream(
                    PARAGRAPHS_PROMPT, user_msg, GROQ_MODEL, timeout_s, 500, on_token,
                )
            else:
                extras_raw = _call_ollama_stream(
                    PARAGRAPHS_PROMPT, user_msg, model, timeout_s, 500, on_token,
                )
            extras = _parse_structured(extras_raw)
            nar.valuation_paragraph = str(extras.get("VALUATION", ""))
            nar.balance_sheet_paragraph = str(extras.get("BALANCE_SHEET", ""))
            nar.cash_flow_paragraph = str(extras.get("CASH_FLOW", ""))
            nar.competitive_paragraph = str(extras.get("COMPETITIVE", ""))
        except Exception:
            pass

    return nar
