"""Executes one run: the learner's prompt on every pinned test case, then the critique.

Each test case streams independently (the canvas shows each as its own card); the cache
serves the standard path instantly; the critic grades all outputs together.
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.schema import LabSpec, RubricSpec
from app.engine import gamification
from app.engine.channel import RunChannel
from app.engine.critic import (
    CritiqueResult,
    build_critic_prompt,
    effective_criteria,
    weighted_total,
)
from app.engine.render import cache_key, render_prompt
from app.engine.usage import record_usage
from app.gateway.providers import ModelProvider, StreamResult, Usage
from app.gateway.router import RoleConfig, role_config
from app.models import Attempt, Critique, Lab, PromptVersion, Rubric, Run, RunCache, RunCase, Technique, User

log = logging.getLogger(__name__)


def critic_role_for(lab: Lab) -> str:
    return "capstone_critique" if lab.data.get("difficulty") == 3 and lab.module_id.startswith("m11") else "critique"


async def _cached(session: AsyncSession, key: str) -> RunCache | None:
    return await session.get(RunCache, key)


async def _stream_with_fallback(
    provider: ModelProvider, cfg: RoleConfig, prompt: str, source: str, on_chunk
) -> tuple[str, Usage, str]:
    """Stream from the role's deployment; if it fails before producing text, use the fallback."""
    deployments = [cfg.deployment] + ([cfg.fallback] if cfg.fallback else [])
    last_exc: Exception | None = None
    for dep in deployments:
        dcfg = RoleConfig(cfg.role, dep, None, cfg.reasoning_effort, cfg.max_output_tokens, cfg.seed)
        produced = []
        try:
            result: StreamResult = provider.stream_text(dcfg, prompt, source=source)
            async for chunk in result.chunks:
                produced.append(chunk)
                await on_chunk(chunk)
            return "".join(produced), result.usage, dep
        except Exception as exc:  # noqa: BLE001 — provider errors vary by SDK
            if produced:
                raise
            last_exc = exc
            log.warning("deployment %s failed, trying fallback: %s", dep, exc)
    raise RuntimeError(f"all deployments failed: {last_exc}")


async def execute_run(session: AsyncSession, redis: Redis, provider: ModelProvider, run_id: uuid.UUID) -> None:
    run = await session.get(Run, run_id)
    if run is None or run.status not in {"queued", "failed"}:
        return
    channel = RunChannel(redis, run.id)
    try:
        await _execute(session, channel, provider, run)
    except Exception as exc:
        log.exception("run %s failed", run_id)
        await session.rollback()
        run = await session.get(Run, run_id)
        assert run is not None
        run.status = "failed"
        run.error = str(exc)[:2000]
        await session.commit()
        await channel.status("failed", error="The model call failed. Please try again in a moment.")


async def _execute(session: AsyncSession, channel: RunChannel, provider: ModelProvider, run: Run) -> None:
    prompt = await session.get(PromptVersion, run.prompt_version_id)
    assert prompt is not None
    attempt = await session.get(Attempt, prompt.attempt_id)
    assert attempt is not None
    lab_row = await session.get(Lab, attempt.lab_id)
    assert lab_row is not None
    lab = LabSpec(**lab_row.data)
    rubric_row = await session.get(Rubric, lab.rubric.base)
    assert rubric_row is not None
    rubric = RubricSpec(**rubric_row.data)
    user = await session.get(User, run.user_id)
    assert user is not None

    cfg = role_config("run")
    run.status = "running"
    await session.commit()
    await channel.status("running")

    case_rows = {c.test_case_id: c for c in run.cases}

    async def run_case(tc) -> tuple[str, str, Usage, str, bool, int]:
        rendered = render_prompt(prompt.text, tc.input)
        key = cache_key("run", cfg.deployment, cfg.settings(), rendered)
        started = time.monotonic()
        async with _session_lock:
            hit = await _cached(session, key)
            if hit:
                hit.hits += 1
                text, usage, dep = hit.output, Usage(hit.input_tokens, hit.output_tokens), hit.deployment
        if hit:
            await channel.append(tc.id, text)
            cached = True
        else:
            text, usage, dep = await _stream_with_fallback(
                provider, cfg, rendered, tc.input, lambda chunk: channel.append(tc.id, chunk)
            )
            cached = False
            async with _session_lock:
                if await _cached(session, key) is None:
                    session.add(RunCache(key=key, deployment=dep, output=text, input_tokens=usage.input_tokens,
                                         output_tokens=usage.output_tokens))
        latency = int((time.monotonic() - started) * 1000)
        await channel.case_done(tc.id, cache_hit=cached, latency_ms=latency)
        return tc.id, text, usage, dep, cached, latency

    _session_lock = asyncio.Lock()
    results = await asyncio.gather(*(run_case(tc) for tc in lab.test_cases))

    total_cost = 0.0
    outputs: list[tuple[str, str, str]] = []
    inputs = {tc.id: tc.input for tc in lab.test_cases}
    for cid, text, usage, dep, cached, latency in results:
        row = case_rows[cid]
        row.output, row.status, row.cache_hit, row.latency_ms = text, "done", cached, latency
        row.input_tokens, row.output_tokens = usage.input_tokens, usage.output_tokens
        total_cost += record_usage(session, user_id=user.id, role="run", deployment=dep,
                                   input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                                   cache_hit=cached)
        outputs.append((cid, inputs[cid], text))

    run.status = "critiquing"
    await session.commit()
    await channel.status("critiquing")

    # ---- critique
    criteria = effective_criteria(rubric, lab)
    technique_ids = list((await session.execute(select(Technique.id))).scalars())
    critic_prompt = build_critic_prompt(lab, criteria, prompt.text, outputs, technique_ids)
    ccfg = role_config(critic_role_for(lab_row))
    ckey = cache_key("critique", ccfg.deployment, ccfg.settings(), critic_prompt)
    cached_critique = await _cached(session, ckey)
    if cached_critique:
        result = CritiqueResult.model_validate_json(cached_critique.output)
        cached_critique.hits += 1
        cusage, cdep, chit = Usage(), cached_critique.deployment, True
    else:
        result, cusage, cdep = await _critique_with_fallback(provider, ccfg, critic_prompt)
        chit = False
        session.add(RunCache(key=ckey, deployment=cdep, output=result.model_dump_json(),
                             input_tokens=cusage.input_tokens, output_tokens=cusage.output_tokens))
    total_cost += record_usage(session, user_id=user.id, role=ccfg.role, deployment=cdep,
                               input_tokens=cusage.input_tokens, output_tokens=cusage.output_tokens,
                               cache_hit=chit)

    valid_ids = {c.id for c in criteria}
    scores = {s.criterion_id: s for s in result.criteria if s.criterion_id in valid_ids}
    total = weighted_total(criteria, {k: v.score for k, v in scores.items()})
    known = set(technique_ids)
    critique = Critique(
        run_id=run.id,
        deployment=cdep,
        scores={k: v.model_dump() for k, v in scores.items()},
        total=total,
        summary=result.summary,
        prompt_spans=[s.model_dump() for s in result.prompt_spans if s.criterion_id in valid_ids],
        detected_techniques=[t for t in result.detected_techniques if t in known],
        next_focus=result.next_focus if result.next_focus in known else None,
    )
    session.add(critique)

    # ---- delta vs the previous version's latest finished run
    prev_score = (await session.execute(
        select(Run.score)
        .join(PromptVersion, Run.prompt_version_id == PromptVersion.id)
        .where(PromptVersion.attempt_id == attempt.id, Run.status == "done", Run.id != run.id,
               PromptVersion.version < prompt.version)
        .order_by(PromptVersion.version.desc(), Run.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    delta = round(total - prev_score, 1) if prev_score is not None else None

    was_passed = attempt.passed
    if attempt.first_score is None:
        attempt.first_score = total
    attempt.best_score = max(attempt.best_score or 0.0, total)
    awards = await gamification.award_for_run(
        session, user=user, attempt=attempt, lab=lab_row, run_ref=str(run.id), score=total, delta=delta,
        technique_id=prompt.technique_id, was_passed=was_passed,
    )

    run.score, run.delta, run.cost_usd = total, delta, round(total_cost, 6)
    run.xp_awarded = sum(a["xp"] for a in awards)
    run.status, run.finished_at = "done", datetime.now(UTC)
    await session.commit()

    await channel.emit("critique", {
        "total": total, "delta": delta, "summary": critique.summary, "scores": critique.scores,
        "prompt_spans": critique.prompt_spans, "detected_techniques": critique.detected_techniques,
        "next_focus": critique.next_focus,
    })
    await channel.emit("awards", {"awards": awards, "xp": user.xp, "level": gamification.level_for(user.xp),
                                  "streak_days": user.streak_days})
    await channel.status("done")


async def _critique_with_fallback(provider: ModelProvider, cfg: RoleConfig, critic_prompt: str):
    from app.engine.critic import CRITIC_INSTRUCTIONS

    deployments = [cfg.deployment] + ([cfg.fallback] if cfg.fallback else [])
    last_exc: Exception | None = None
    for dep in deployments:
        dcfg = RoleConfig(cfg.role, dep, None, cfg.reasoning_effort, cfg.max_output_tokens, cfg.seed)
        try:
            result, usage = await provider.complete_json(dcfg, critic_prompt, CritiqueResult,
                                                         instructions=CRITIC_INSTRUCTIONS)
            return result, usage, dep
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("critic deployment %s failed: %s", dep, exc)
    raise RuntimeError(f"critic failed: {last_exc}")


def new_run_cases(run: Run, lab: LabSpec) -> list[RunCase]:
    return [RunCase(run_id=run.id, test_case_id=tc.id, position=i) for i, tc in enumerate(lab.test_cases)]
