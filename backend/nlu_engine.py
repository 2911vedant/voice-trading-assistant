"""
nlu_engine.py
Multilingual (English / Hindi / Marathi / Hinglish) Natural Language
Understanding engine for the trading assistant.

Uses Groq's LLM (llama-3.3-70b-versatile) as the reasoning core instead of
a fixed-grammar parser, so it generalizes to free-form phrasing rather than
matching hardcoded command templates.

Set GROQ_API_KEY in your environment (see .env.example).
"""

import json
import os
import re

from groq import Groq

_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a Natural Language Understanding engine for a stock
trading voice assistant used in India. Users speak in English, Hindi,
Marathi, or Hinglish (mixed Hindi-English), and phrasing is NOT fixed —
you must generalize, not pattern-match.

Your job: read the user's utterance (already transcribed from speech) and
return ONLY a single JSON object, nothing else — no markdown fences, no
preamble, no explanation text outside the JSON.

JSON schema:
{
  "action": "BUY" | "SELL" | "MODIFY" | "CANCEL" | "UNKNOWN",
  "quantity": <integer or null>,
  "asset": "<uppercase normalized stock/company name, or null>",
  "condition": {
     "type": "price" | "none",
     "operator": "<" | "<=" | ">" | ">=" | "==" | null,
     "value": <number or null>,
     "currency": "INR"
  } | null,
  "raw_language_detected": "en" | "hi" | "mr" | "hinglish",
  "confidence": <float 0-1>,
  "ambiguous_fields": [<list of field names you were unsure about, empty if none>]
}

Rules:
- "if", "only if", "under", "less than", "below", "kam", "se kam", "khali
  keval" type phrases all mean a conditional order — set condition.type
  to "price" and pick the correct operator. "under 500" and "less than
  500" both mean operator "<". "at or below 500" means "<=".
- If no explicit condition is spoken, condition should be null and the
  order is treated as a plain market order.
- Normalize company/stock names to their common uppercase short form,
  e.g. "Tata Motors" -> "TATA MOTORS", "Reliance" -> "RELIANCE", "TCS"
  stays "TCS", "Infosys" -> "INFY", "HDFC Bank" -> "HDFC BANK", "SBI" ->
  "SBIN", "Wipro" -> "WIPRO". If you don't recognize the company, still
  return your best-guess uppercase normalization.
- Numbers may be spoken as words ("twenty shares", "paanch sau rupaye" =
  500 rupees) or digits/symbols ("₹500", "500rs"). Always resolve to a
  plain number.
- currency is always "INR" for this system.
- If quantity is not mentioned, set it to null (do not guess a default).
- If you genuinely cannot classify the action, set action to "UNKNOWN"
  and lower confidence accordingly. Never invent an asset or price you
  did not see evidence for.
- Return ONLY the JSON object.
"""


def _extract_json(text: str) -> dict:
    """Groq sometimes wraps JSON in fences despite instructions; strip them."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def parse_command(utterance: str) -> dict:
    """
    Main entry point. Takes a raw transcribed utterance (any supported
    language / Hinglish mix) and returns structured trade intent JSON.
    """
    if not utterance or not utterance.strip():
        return {
            "action": "UNKNOWN",
            "quantity": None,
            "asset": None,
            "condition": None,
            "raw_language_detected": "unknown",
            "confidence": 0.0,
            "ambiguous_fields": ["utterance"],
            "error": "empty utterance",
        }

    resp = _client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": utterance},
        ],
    )
    raw = resp.choices[0].message.content

    try:
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, AttributeError) as e:
        return {
            "action": "UNKNOWN",
            "quantity": None,
            "asset": None,
            "condition": None,
            "raw_language_detected": "unknown",
            "confidence": 0.0,
            "ambiguous_fields": ["parse_error"],
            "error": f"LLM did not return valid JSON: {e}",
            "raw_model_output": raw,
        }

    parsed["utterance"] = utterance
    return parsed


def explain_execution(parsed_order: dict, executed_price: float) -> str:
    """
    Human-readable explanation shown after a conditional trade fires.
    Kept rule-based (not another LLM call) so explanations are fast,
    deterministic, and auditable.
    """
    action = parsed_order.get("action", "TRADE")
    asset = parsed_order.get("asset", "the asset")
    qty = parsed_order.get("quantity")
    condition = parsed_order.get("condition")

    qty_str = f"{qty} share(s) of " if qty else ""

    if not condition or condition.get("type") == "none":
        return f"{action} order for {qty_str}{asset} executed immediately as a market order at ₹{executed_price}."

    op_words = {
        "<": "dropped below",
        "<=": "reached or dropped below",
        ">": "rose above",
        ">=": "reached or rose above",
        "==": "hit exactly",
    }
    op_word = op_words.get(condition.get("operator"), "met the condition of")
    threshold = condition.get("value")

    return (
        f"Trade executed: {action} {qty_str}{asset} because the price "
        f"{op_word} ₹{threshold} (current price: ₹{executed_price})."
    )
