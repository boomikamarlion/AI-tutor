"""Static prompt features — the server-side mirror of apps/web/lib/lint/rules.ts.

Used by the fake provider and fake critic, and stored with each prompt version so
analytics can correlate lint signals with rubric scores. Keep rule ids in sync with the web.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    pattern: re.Pattern[str]
    weight: int


_I = re.IGNORECASE | re.MULTILINE

RULES: list[Rule] = [
    Rule("role", "Role", re.compile(r"\b(you are|act as|you're an?|as an? (expert|experienced|senior))\b", _I), 2),
    Rule("task", "Clear task", re.compile(
        r"^\s*(please\s+)?(write|create|generate|draft|summari[sz]e|classify|extract|list|rewrite|translate|"
        r"analy[sz]e|explain|tag|answer|grade|evaluate|plan|convert|compare|identify|produce|suggest|design|"
        r"review|turn|reply|respond)\b|\b(your task is|you will|i need you to)\b", _I), 3),
    Rule("audience", "Audience", re.compile(
        r"\b(audience|reader|for (college )?students|for customers|for beginners|target(ed)? (at|to)|"
        r"aimed at|who (are|is) (new|reading))\b", _I), 1),
    Rule("context", "Context", re.compile(r"\b(context|background|situation|goal is|because|we are|our )\b", _I), 1),
    Rule("constraints", "Constraints", re.compile(
        r"\b(\d+\s*(words?|sentences?|bullets?|characters?|lines?|items?|points?|paragraphs?)|at most|no more than|"
        r"under \d+|maximum|must|do not|don't|avoid|only)\b", _I), 2),
    Rule("format", "Output format", re.compile(
        r"\b(format|json|table|bullet|numbered|markdown|headings?|sections?|csv|schema|columns?|template|"
        r"return (only|exactly))\b", _I), 2),
    Rule("examples", "Examples", re.compile(r"\b(example|e\.g\.|for instance|sample)\b|^\s*(input|output)\s*:", _I), 1),
    Rule("delimiters", "Delimiters", re.compile(r"(```|\"\"\"|<[a-z_]+>|^#{2,}\s|\{\{input\}\}|---)", _I), 1),
    Rule("uncertainty", "Allows 'not stated'", re.compile(
        r"(not stated|don't know|do not know|unknown|insufficient|if (any|the) .{0,40}(missing|unclear)|"
        r"only (use|the) (information|facts|text)|do not (invent|make up|guess))", _I), 1),
    Rule("reasoning", "Reasoning guidance", re.compile(
        r"\b(step[- ]by[- ]step|first,? .{0,60}then|think (through|carefully)|plan|criteria|"
        r"check (your|each))\b", _I), 1),
]

RULE_IDS = [r.id for r in RULES]


def prompt_features(prompt: str) -> dict:
    hits = {r.id: bool(r.pattern.search(prompt)) for r in RULES}
    total = sum(r.weight for r in RULES)
    score = sum(r.weight for r in RULES if hits[r.id]) / total
    words = len(prompt.split())
    return {"hits": hits, "score": round(score * 100), "words": words}


_LIMIT = re.compile(
    r"(?:at most|no more than|under|maximum|max|within|in)\s*(\d+)\s*(words?|sentences?|bullets?|points?|items?)",
    re.IGNORECASE,
)
_LIMIT_PLAIN = re.compile(r"\b(\d+)\s*(words?|sentences?|bullets?|points?|items?)\b", re.IGNORECASE)


def length_limit(prompt: str) -> tuple[int, str] | None:
    m = _LIMIT.search(prompt) or _LIMIT_PLAIN.search(prompt)
    if not m:
        return None
    unit = m.group(2).lower().rstrip("s")
    return int(m.group(1)), unit
