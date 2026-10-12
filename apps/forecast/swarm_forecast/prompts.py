"""Prompts and schemas for the forecast stages."""
from __future__ import annotations

FORECAST_SCHEMA = {
    "type": "object",
    "properties": {
        "probability": {"type": "number"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "key_uncertainty": {"type": "string"},
        "market_may_be_missing": {"type": "string"},
    },
    "required": ["probability", "reasons", "key_uncertainty"],
}

FORECAST_SYSTEM = """You turn a researcher's findings into one calibrated probability that a question resolves YES.
Rules:
- Use only the findings you are given plus ordinary base rates; do not invent facts.
- Answer exactly the question and rules as written (dates, thresholds, who decides).
- Use the full range. If the evidence points one way, say 0.05 or 0.95, not 0.5. If the evidence is thin, stay near the base rate for this kind of event.
- 'reasons': 2 to 4 short statements, each tied to a finding or a base rate.
- 'key_uncertainty': the one thing most likely to change the answer.
- 'market_may_be_missing': only if a market price was shown to you: what the market might be missing, else empty.
Reply with the JSON object only."""

SELECT_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "answerable": {"type": "integer"},
                       "tag": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["id", "answerable", "tag", "reason"]}}},
    "required": ["items"],
}

SELECT_SYSTEM = """You screen forecasting questions for a research team. For each question rate 1 to 5 how well
the team could forecast it by searching the web for evidence available today: 5 = clear public evidence exists
(scheduled events, published data, official statements); 1 = essentially a coin flip or random, or unknowable
from public sources. 'tag' is one word for the topic. 'reason' is one short sentence on what evidence could be found
(or why none can). Do not guess the outcome. Reply with the JSON object only, one item per question id."""


def research_question(q: dict, mode: str) -> str:
    rules = (q.get("rules") or "").strip()
    if len(rules) > 1500:
        rules = rules[:1500] + " ..."
    text = (f"FORECASTING QUESTION (today is {q['today']}). Will this resolve YES? {q['question']}\n"
            f"Resolution rules: {rules or '(none given)'}\nIt resolves by {q.get('end_date') or 'an unstated date'}.\n"
            "Research what is known now: the current situation, recent developments, the schedule of events before "
            "the end date, and how often similar events have happened before. Then estimate the probability that it "
            "resolves YES. If the evidence is thin, say so.")
    if mode == "informed":
        ms = q.get("market_state") or {}
        ya, na = ms.get("yes_ask"), ms.get("no_ask")
        if ya is not None:
            text += (f"\nA prediction market currently asks {ya * 100:.0f} cents for YES"
                     + (f" and {na * 100:.0f} cents for NO" if na is not None else "")
                     + ". The market is usually well informed. Look for what it might be missing, or confirm it is "
                       "right. Do not just repeat the price.")
    return text


def extraction_user(q: dict, mode: str, answer: str, notes: list[str]) -> str:
    parts = [f"Question: {q['question']}", f"Resolution rules: {(q.get('rules') or '')[:1500]}",
             f"Today: {q['today']}. Resolves by: {q.get('end_date')}",
             "Researcher's answer:\n" + (answer or "(none)")[:3000],
             "Findings:\n" + "\n".join(f"- {n}" for n in notes[:15]) if notes else "Findings: (none recorded)"]
    parts.append("The probability must be the probability that the market question resolves YES, not the probability of a person, event, or alternative outcome.")
    if mode == "informed":
        ms = q.get("market_state") or {}
        if ms.get("yes_ask") is not None:
            parts.append(f"Market price shown: YES asks {ms['yes_ask'] * 100:.0f} cents. Say what it may be missing.")
    return "\n\n".join(parts)
