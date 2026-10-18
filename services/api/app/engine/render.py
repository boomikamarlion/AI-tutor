import hashlib
import json

PLACEHOLDER = "{{input}}"


def render_prompt(prompt: str, test_input: str) -> str:
    """Fill the learner's prompt with one pinned test-case input."""
    if PLACEHOLDER in prompt:
        return prompt.replace(PLACEHOLDER, test_input.strip())
    return f"{prompt.rstrip()}\n\n<input>\n{test_input.strip()}\n</input>"


def cache_key(kind: str, deployment: str, settings: dict, *parts: str) -> str:
    payload = json.dumps({"k": kind, "d": deployment, "s": settings, "p": parts}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
