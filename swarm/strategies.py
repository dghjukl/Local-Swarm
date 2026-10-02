"""Reasoning strategies a worker can be given.

Adapted from the strategy library in MCP/reasoning-mcp (types_.py STRATEGIES, which in turn
consolidates sequential-thinking, think-strategies and advanced-reasoning-mcp). The MCP offers
them as step-by-step tool calls; small models are poor at driving multi-turn tool use, so the
swarm uses the same strategies as short written instructions: the worker writes its reasoning
in a `reasoning` field first, following the method, and only then gives its answer and claims.

Strategies that only make sense with tools or trade-offs (react, rewoo, trilemma) and the code
strategy are kept for later domains; they are not offered for evidence-based research.
"""
from __future__ import annotations

# name -> (short label, how to reason, written for a model answering from evidence passages)
STRATEGIES: dict[str, tuple[str, str]] = {
    "direct": ("Direct", ""),  # no reasoning step: the original worker behaviour
    "linear": ("Linear", (
        "Go step by step in order: (1) find the passages that are about the question, "
        "(2) write down the facts they state, (3) check those facts actually answer the question, "
        "(4) only then answer.")),
    "chain_of_thought": ("Chain of thought", (
        "State what the passages establish, then derive the answer one step at a time. "
        "Each step must follow from the previous one and name the passage id it relies on. "
        "Finish by checking the conclusion traces back to the passages.")),
    "self_ask": ("Self-ask", (
        "Break the question into 2-4 smaller questions that must be answered first "
        "(who/what exactly, when, what was found, how strong is the evidence). "
        "Answer each one from the passages, then combine the answers.")),
    "step_back": ("Step back", (
        "First step back: say what kind of question this is and what a good answer to that kind "
        "must contain (for a new finding: what exactly was found, by whom, and how certain it is). "
        "Then apply that checklist to these passages.")),
    "self_consistency": ("Self-consistency", (
        "Reason two independent ways. Path A: answer from the single most direct passage. "
        "Path B: answer from the other passages, ignoring Path A. Compare them: keep only what both "
        "paths support, and note any disagreement as uncertainty.")),
    "tree_of_thoughts": ("Tree of thoughts", (
        "List 2-3 candidate answers or readings the passages could support, including easily "
        "confused things (a similar name, a different study, a different planet). Test each candidate "
        "against the passages, drop the weak ones and say why, then keep the best-supported one.")),
    "scratchpad": ("Scratchpad", (
        "First jot down, freely, every name, number, date and caveat in the passages that might "
        "matter. Then pick out what actually answers the question.")),
    # The model's own trained thinking mode (Qwen3.5, Gemma 4, ...): no written method, the chat
    # template's thinking switch is turned on instead. Only works for models trained to think; the
    # worker record's `thought_chars` shows whether any thinking actually happened.
    "native": ("Built-in thinking", ""),
}

NATIVE = "native"

RESEARCH_STRATEGIES = [s for s in STRATEGIES if s not in ("direct", NATIVE)]


def label(name: str) -> str:
    return STRATEGIES.get(name, (name, ""))[0]


def instruction(name: str | None) -> str:
    """Extra system-prompt text for a strategy ('' for direct/unknown)."""
    if not name or name not in STRATEGIES or not STRATEGIES[name][1]:
        return ""
    return ("\n\nHow to think: " + STRATEGIES[name][1] +
            "\nWrite this thinking in the `reasoning` field first, in under 120 words. "
            "The answer and claims come after it and must agree with it.")
