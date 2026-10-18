"""Response shaping. Learner-facing views never include reference prompts or prediction answers."""

from typing import Any

from app.content.schema import LabSpec
from app.models import Attempt, Lab, PromptVersion, Run

HIDDEN_LAB_FIELDS = {"reference_prompt"}


def lab_public(lab: Lab, *, include_hidden: bool = False) -> dict[str, Any]:
    spec = LabSpec(**lab.data)
    data = spec.model_dump()
    if not include_hidden:
        for f in HIDDEN_LAB_FIELDS:
            data.pop(f, None)
        data["predictions"] = [
            {k: v for k, v in p.items() if k not in {"answer", "explanation"}} for p in data["predictions"]
        ]
    data["module_id"] = lab.module_id
    data["version"] = lab.version
    return data


def lab_summary(lab: Lab, attempt: Attempt | None = None) -> dict[str, Any]:
    d = lab.data
    return {
        "id": lab.id,
        "title": d["title"],
        "difficulty": d["difficulty"],
        "estimated_minutes": d.get("estimated_minutes"),
        "techniques_targeted": d.get("techniques_targeted", []),
        "uses_product_case": d.get("uses_product_case", False),
        "best_score": attempt.best_score if attempt else None,
        "passed": attempt.passed if attempt else False,
        "attempt_id": str(attempt.id) if attempt else None,
    }


def run_view(run: Run) -> dict[str, Any]:
    c = run.critique
    return {
        "id": str(run.id),
        "prompt_version_id": str(run.prompt_version_id),
        "status": run.status,
        "error": "The model call failed. Please try again." if run.status == "failed" else None,
        "score": run.score,
        "delta": run.delta,
        "xp_awarded": run.xp_awarded,
        "deployment": run.run_deployment,
        "settings": run.run_settings,
        "lab_version": run.lab_version,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "cases": [
            {"test_case_id": rc.test_case_id, "output": rc.output, "status": rc.status, "cache_hit": rc.cache_hit,
             "latency_ms": rc.latency_ms}
            for rc in run.cases
        ],
        "critique": None if c is None else {
            "total": c.total,
            "summary": c.summary,
            "scores": c.scores,
            "prompt_spans": c.prompt_spans,
            "detected_techniques": c.detected_techniques,
            "next_focus": c.next_focus,
            "deployment": c.deployment,
        },
    }


def prompt_view(p: PromptVersion, runs: list[Run]) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "version": p.version,
        "text": p.text,
        "lint": p.lint,
        "technique_id": p.technique_id,
        "reflection": p.reflection,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "runs": [run_view(r) for r in runs],
    }


def attempt_view(attempt: Attempt, runs_by_prompt: dict) -> dict[str, Any]:
    return {
        "id": str(attempt.id),
        "lab_id": attempt.lab_id,
        "event_id": str(attempt.event_id) if attempt.event_id else None,
        "first_score": attempt.first_score,
        "best_score": attempt.best_score,
        "passed": attempt.passed,
        "prompts": [prompt_view(p, runs_by_prompt.get(p.id, [])) for p in attempt.prompts],
    }
