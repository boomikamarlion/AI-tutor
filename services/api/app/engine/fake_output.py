"""Deterministic offline output generator used by FakeProvider.

It imitates how a model responds to prompt structure: a format request changes the shape,
a length limit is honoured, a role shifts the register, and with no grounding guidance it
"hallucinates" a confident invented fact. Good enough to make v1 → v2 deltas real offline.
"""

import json
import re

from app.engine.features import length_limit, prompt_features

_INPUT = re.compile(r"<input>\s*(.*?)\s*</input>", re.DOTALL)


def _source_text(prompt: str, source: str | None) -> str:
    m = _INPUT.search(prompt)
    text = source or (m.group(1) if m else prompt)
    return " ".join(text.split())


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if len(p.strip()) > 3]
    return parts or [text[:200]]


def fake_output(prompt: str, source: str | None = None) -> str:
    feats = prompt_features(prompt)["hits"]
    source = _source_text(prompt, source)
    sentences = _sentences(source)
    limit = length_limit(prompt)
    lower = prompt.lower()

    points = [s.rstrip(".") for s in sentences][:6]
    if limit and limit[1] in {"bullet", "point", "item", "sentence"}:
        points = points[: max(1, limit[0])]
    elif not feats["constraints"]:
        # Unconstrained prompts ramble: repeat and pad.
        points = points + ["It is also worth noting that " + points[0].lower()] + [
            "In conclusion, there are many important aspects to consider here"
        ]

    if "json" in lower:
        body = json.dumps(
            {"summary": points[0], "items": points[1:4], "confidence": "medium" if feats["uncertainty"] else "high"},
            indent=2,
        )
    elif feats["format"] and ("table" in lower or "column" in lower):
        rows = "\n".join(f"| {i + 1} | {p} |" for i, p in enumerate(points))
        body = "| # | Point |\n|---|---|\n" + rows
    elif feats["format"]:
        body = "\n".join(f"- {p}." for p in points)
    else:
        body = " ".join(p + "." for p in points)

    if feats["role"]:
        body = "Here is a focused response.\n\n" + body
    else:
        body = "Sure! Here's what I came up with.\n\n" + body
    if not (feats["uncertainty"] or "only" in lower):
        body += "\n\nFounded in 1962, it is widely recognised as the best in Tamil Nadu."

    if limit and limit[1] == "word":
        words = body.split()
        body = " ".join(words[: limit[0]])
    return body
