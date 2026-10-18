from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, Session
from app.engine.gamification import level_for, xp_for_level
from app.engine.usage import check_budget, has_pro
from app.models import (
    Attempt,
    Cohort,
    Consent,
    Event,
    Lab,
    Module,
    RoleAssignment,
    TechniqueMastery,
    XpEntry,
)

router = APIRouter(tags=["me"])

CONSENT_SCOPES = {
    "learner_analytics": "Use my activity to personalise my learning and show my progress dashboard.",
    "cohort_sharing": "Let mentors of cohorts I join see my progress in that cohort.",
    "hiring_share": "Let me create evidence links of my prompt trails to share with employers I choose.",
}
POLICY_VERSION = "2026-10"


async def _active_consents(session, user_id) -> dict[str, dict]:
    rows = (await session.execute(
        select(Consent).where(Consent.user_id == user_id, Consent.revoked_at.is_(None))
    )).scalars()
    return {c.scope: {"granted_at": c.granted_at.isoformat(), "policy_version": c.policy_version} for c in rows}


@router.get("/me")
async def me(principal: CurrentPrincipal, session: Session):
    u = principal.user
    budget = await check_budget(session, principal)
    level = level_for(u.xp)
    return {
        "id": str(u.id),
        "email": u.email,
        "display_name": u.display_name,
        "college": u.college,
        "interests": u.interests,
        "onboarded": u.onboarded,
        "plan": u.plan,
        "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
        "has_pro": has_pro(principal),
        "xp": u.xp,
        "level": level,
        "level_floor_xp": xp_for_level(level),
        "next_level_xp": xp_for_level(level + 1),
        "streak_days": u.streak_days,
        "roles": principal.roles_summary(),
        "consents": await _active_consents(session, u.id),
        "budget": budget.as_dict(),
    }


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    college: str | None = Field(default=None, max_length=200)
    interests: list[str] | None = None
    onboarded: bool | None = None


@router.patch("/me")
async def update_me(body: ProfileUpdate, principal: CurrentPrincipal, session: Session):
    u = principal.user
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(u, k, v)
    await session.commit()
    return {"ok": True}


@router.get("/consent-scopes")
async def consent_scopes():
    return {"policy_version": POLICY_VERSION, "scopes": CONSENT_SCOPES}


class ConsentChange(BaseModel):
    scope: str
    granted: bool


@router.post("/me/consents")
async def change_consent(body: ConsentChange, principal: CurrentPrincipal, session: Session):
    if body.scope not in CONSENT_SCOPES:
        raise HTTPException(422, "Unknown consent scope")
    active = (await session.execute(
        select(Consent).where(Consent.user_id == principal.id, Consent.scope == body.scope,
                              Consent.revoked_at.is_(None))
    )).scalars().all()
    if body.granted and not active:
        session.add(Consent(user_id=principal.id, scope=body.scope, policy_version=POLICY_VERSION))
    if not body.granted:
        for c in active:
            c.revoked_at = datetime.now(UTC)
    await session.commit()
    return {"consents": await _active_consents(session, principal.id)}


@router.get("/me/progress")
async def progress(principal: CurrentPrincipal, session: Session):
    attempts = (await session.execute(select(Attempt).where(Attempt.user_id == principal.id))).scalars().all()
    by_lab: dict[str, Attempt] = {}
    for a in attempts:  # an attempt per event context; keep the best
        if a.lab_id not in by_lab or (a.best_score or 0) > (by_lab[a.lab_id].best_score or 0):
            by_lab[a.lab_id] = a
    modules = (await session.execute(select(Module).order_by(Module.order))).scalars().all()
    labs = (await session.execute(select(Lab))).scalars().all()
    labs_by_module: dict[str, list[Lab]] = {}
    for lab in labs:
        labs_by_module.setdefault(lab.module_id, []).append(lab)
    mastery = (await session.execute(
        select(TechniqueMastery).where(TechniqueMastery.user_id == principal.id)
    )).scalars().all()
    recent_xp = (await session.execute(
        select(XpEntry).where(XpEntry.user_id == principal.id).order_by(XpEntry.created_at.desc()).limit(20)
    )).scalars().all()
    return {
        "modules": [
            {
                "id": m.id,
                "title": m.title,
                "labs_total": len(labs_by_module.get(m.id, [])),
                "labs_passed": sum(1 for lab in labs_by_module.get(m.id, []) if by_lab.get(lab.id)
                                   and by_lab[lab.id].passed),
            }
            for m in modules
        ],
        "mastery": [
            {"technique_id": t.technique_id, "uses": t.uses, "improving_uses": t.improving_uses,
             "labs": t.labs, "best_delta": t.best_delta,
             "mastered_at": t.mastered_at.isoformat() if t.mastered_at else None}
            for t in mastery
        ],
        "recent_xp": [
            {"amount": x.amount, "reason": x.reason, "ref": x.ref, "at": x.created_at.isoformat()} for x in recent_xp
        ],
    }


class JoinRequest(BaseModel):
    code: str = Field(min_length=3, max_length=20)


@router.post("/me/join")
async def join(body: JoinRequest, principal: CurrentPrincipal, session: Session):
    """Join a cohort or a hackathon event by its code."""
    code = body.code.strip().upper()
    user = principal.user
    event = (await session.execute(select(Event).where(Event.join_code == code))).scalar_one_or_none()
    if event:
        if event.ends_at < datetime.now(UTC):
            raise HTTPException(410, "This event has ended")
        await _ensure_role(session, user.id, "learner", "event", event.id)
        if event.grants_pro_days > 0:
            until = event.ends_at + timedelta(days=event.grants_pro_days)
            if user.plan != "pro" or (user.plan_expires_at and user.plan_expires_at < until):
                user.plan, user.plan_expires_at = "pro", until
        await session.commit()
        return {"joined": "event", "id": str(event.id), "name": event.name, "lab_ids": event.lab_ids}
    cohort = (await session.execute(select(Cohort).where(Cohort.join_code == code))).scalar_one_or_none()
    if cohort:
        await _ensure_role(session, user.id, "learner", "cohort", cohort.id)
        await session.commit()
        return {"joined": "cohort", "id": str(cohort.id), "name": cohort.name}
    raise HTTPException(404, "No cohort or event with that code")


async def _ensure_role(session, user_id, role, scope_type, scope_id) -> None:
    exists = (await session.execute(select(RoleAssignment).where(
        RoleAssignment.user_id == user_id, RoleAssignment.role == role,
        RoleAssignment.scope_type == scope_type, RoleAssignment.scope_id == scope_id,
    ))).scalar_one_or_none()
    if not exists:
        session.add(RoleAssignment(user_id=user_id, role=role, scope_type=scope_type, scope_id=scope_id))


@router.get("/me/events")
async def my_events(principal: CurrentPrincipal, session: Session):
    ids = principal.scope_ids("learner", "event") | principal.scope_ids("judge", "event")
    if not ids:
        return []
    events = (await session.execute(select(Event).where(Event.id.in_(ids)))).scalars().all()
    return [
        {"id": str(e.id), "name": e.name, "starts_at": e.starts_at.isoformat(), "ends_at": e.ends_at.isoformat(),
         "lab_ids": e.lab_ids, "is_judge": e.id in principal.scope_ids("judge", "event")}
        for e in events
    ]
