"""The canvas: attempts, immutable prompt versions, runs (streamed), predictions, coach."""

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.api.course import lab_unlocked
from app.api.deps import Arq, CurrentPrincipal, Session
from app.api.serializers import attempt_view, run_view
from app.auth.rbac import Principal
from app.content.schema import LabSpec
from app.engine import gamification
from app.engine.channel import channel_name, snapshot
from app.engine.features import prompt_features
from app.engine.render import cache_key, render_prompt
from app.engine.runner import new_run_cases
from app.engine.usage import check_budget
from app.gateway.router import role_config
from app.models import Attempt, Event, Lab, PredictionAnswer, PromptVersion, Rubric, Run, RunCache, Technique

router = APIRouter(tags=["workspace"])

MAX_PROMPT_CHARS = 8000


async def _own_attempt(session, principal: Principal, attempt_id: uuid.UUID) -> Attempt:
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None or attempt.user_id != principal.id:
        raise HTTPException(404, "Attempt not found")
    return attempt


async def _attempt_payload(session, attempt: Attempt) -> dict:
    await session.refresh(attempt, ["prompts"])
    prompt_ids = [p.id for p in attempt.prompts]
    runs = (await session.execute(
        select(Run).where(Run.prompt_version_id.in_(prompt_ids)).order_by(Run.created_at)
    )).scalars().all() if prompt_ids else []
    by_prompt: dict = {}
    for r in runs:
        by_prompt.setdefault(r.prompt_version_id, []).append(r)
    return attempt_view(attempt, by_prompt)


@router.post("/labs/{lab_id}/attempt")
async def open_attempt(lab_id: str, principal: CurrentPrincipal, session: Session, event_id: uuid.UUID | None = None):
    """Get or create the learner's canvas for a lab (optionally inside a hackathon event)."""
    lab = await session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(404, "Lab not found")
    if not await lab_unlocked(session, principal, lab):
        raise HTTPException(402, "This lab is part of the Pro plan")
    if event_id is not None:
        event = await session.get(Event, event_id)
        if event is None or event_id not in principal.scope_ids("learner", "event") or lab_id not in event.lab_ids:
            raise HTTPException(403, "Not a participant of this event lab")
    attempt = (await session.execute(select(Attempt).where(
        Attempt.user_id == principal.id, Attempt.lab_id == lab_id,
        Attempt.event_id.is_(None) if event_id is None else Attempt.event_id == event_id,
    ))).scalar_one_or_none()
    if attempt is None:
        attempt = Attempt(user_id=principal.id, lab_id=lab_id, event_id=event_id)
        session.add(attempt)
        await session.commit()
    return await _attempt_payload(session, attempt)


@router.get("/attempts/{attempt_id}")
async def get_attempt(attempt_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    return await _attempt_payload(session, await _own_attempt(session, principal, attempt_id))


class NewPrompt(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    technique_id: str | None = None
    reflection: str | None = Field(default=None, max_length=1000)
    client_lint: dict | None = None


@router.post("/attempts/{attempt_id}/prompts")
async def add_prompt(attempt_id: uuid.UUID, body: NewPrompt, principal: CurrentPrincipal, session: Session):
    attempt = await _own_attempt(session, principal, attempt_id)
    await session.refresh(attempt, ["prompts"])
    version = (attempt.prompts[-1].version + 1) if attempt.prompts else 1
    if body.technique_id:
        if await session.get(Technique, body.technique_id) is None:
            raise HTTPException(422, "Unknown technique")
    elif version > 1:
        raise HTTPException(422, "Name the technique you applied in this revision")
    pv = PromptVersion(
        attempt_id=attempt.id, version=version, text=body.text, technique_id=body.technique_id,
        reflection=body.reflection, lint={"server": prompt_features(body.text), "client": body.client_lint or {}},
    )
    session.add(pv)
    await session.commit()
    return {"id": str(pv.id), "version": version, "lint": pv.lint}


@router.post("/prompts/{prompt_id}/runs", status_code=202)
async def start_run(prompt_id: uuid.UUID, principal: CurrentPrincipal, session: Session, arq: Arq):
    pv = await session.get(PromptVersion, prompt_id)
    if pv is None:
        raise HTTPException(404, "Prompt not found")
    attempt = await _own_attempt(session, principal, pv.attempt_id)
    lab_row = await session.get(Lab, attempt.lab_id)
    assert lab_row is not None
    lab = LabSpec(**lab_row.data)

    active = (await session.execute(select(Run).where(
        Run.user_id == principal.id, Run.status.in_(["queued", "running", "critiquing"])
    ))).scalars().all()
    if len(active) >= 3:
        raise HTTPException(429, "You already have 3 runs in flight — let one land first")

    cfg = role_config("run")
    budget = await check_budget(session, principal)
    if not budget.allowed:
        raise HTTPException(429, {"message": "You've used today's AI budget. It resets at midnight IST.",
                                  "budget": budget.as_dict()})
    if budget.cache_only:
        keys = [cache_key("run", cfg.deployment, cfg.settings(), render_prompt(pv.text, tc.input))
                for tc in lab.test_cases]
        if any(await session.get(RunCache, k) is None for k in keys):
            raise HTTPException(429, {"message": "You're near today's AI budget, so only previously-run prompts "
                                                 "can run until midnight IST.", "budget": budget.as_dict()})

    rubric = await session.get(Rubric, lab.rubric.base)
    assert rubric is not None
    run = Run(
        prompt_version_id=pv.id, user_id=principal.id, lab_version=lab_row.version, rubric_version=rubric.version,
        run_deployment=cfg.deployment, run_settings=cfg.settings(),
    )
    session.add(run)
    await session.flush()
    session.add_all(new_run_cases(run, lab))
    await session.commit()
    await arq.enqueue_job("run_job", str(run.id), _job_id=f"run:{run.id}")
    return {"id": str(run.id), "status": run.status}


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    run = await session.get(Run, run_id)
    if run is None or run.user_id != principal.id:
        raise HTTPException(404, "Run not found")
    return run_view(run)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: uuid.UUID, request: Request, principal: CurrentPrincipal, session: Session):
    """Server-sent events: snapshot, then status/delta/case_done/critique/awards events until done."""
    run = await session.get(Run, run_id)
    if run is None or run.user_id != principal.id:
        raise HTTPException(404, "Run not found")
    case_ids = [c.test_case_id for c in run.cases]
    redis = request.app.state.redis
    final_view = run_view(run) if run.status in {"done", "failed"} else None

    async def events():
        if final_view is not None:
            yield {"event": "final", "data": json.dumps(final_view)}
            return
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel_name(run_id))
        try:
            snap = await snapshot(redis, run_id, case_ids)
            yield {"event": "snapshot", "data": json.dumps(snap)}
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                data = msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]
                evt = json.loads(data)
                yield {"event": evt["type"], "data": data}
                if evt["type"] == "status" and evt["status"] in {"done", "failed"}:
                    break
        finally:
            await pubsub.unsubscribe(channel_name(run_id))
            await pubsub.aclose()

    return EventSourceResponse(events())


class PredictionChoice(BaseModel):
    prediction_id: str
    choice: int = Field(ge=0)


@router.post("/runs/{run_id}/predictions")
async def answer_prediction(run_id: uuid.UUID, body: PredictionChoice, principal: CurrentPrincipal,
                            session: Session):
    run = await session.get(Run, run_id)
    if run is None or run.user_id != principal.id:
        raise HTTPException(404, "Run not found")
    pv = await session.get(PromptVersion, run.prompt_version_id)
    attempt = await session.get(Attempt, pv.attempt_id)  # type: ignore[union-attr]
    lab = LabSpec(**(await session.get(Lab, attempt.lab_id)).data)  # type: ignore[union-attr]
    pred = next((p for p in lab.predictions if p.id == body.prediction_id), None)
    if pred is None or body.choice >= len(pred.options):
        raise HTTPException(422, "Unknown prediction")
    existing = (await session.execute(select(PredictionAnswer).where(
        PredictionAnswer.run_id == run_id, PredictionAnswer.prediction_id == pred.id
    ))).scalar_one_or_none()
    if existing is None:
        correct = body.choice == pred.answer
        session.add(PredictionAnswer(run_id=run_id, user_id=principal.id, prediction_id=pred.id,
                                     choice=body.choice, correct=correct))
        if correct:
            await gamification.award_prediction(session, principal.user, str(run_id))
        await session.commit()
    else:
        correct = existing.correct
    # The UI holds this until the output lands — prediction before reveal.
    return {"correct": correct, "answer": pred.answer, "explanation": pred.explanation}


class CoachQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@router.post("/attempts/{attempt_id}/coach")
async def coach(attempt_id: uuid.UUID, body: CoachQuestion, principal: CurrentPrincipal, session: Session):
    from app.engine.coach import ask_coach

    attempt = await _own_attempt(session, principal, attempt_id)
    try:
        answer = await asyncio.wait_for(ask_coach(session, principal, attempt, body.question), timeout=60)
    except TimeoutError as exc:
        raise HTTPException(504, "The coach is taking too long — try again") from exc
    return {"answer": answer}
