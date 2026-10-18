"""Organisations, cohorts, hackathon events, judging and role assignment (RBAC-gated)."""

import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import CurrentPrincipal, Session, require
from app.auth.rbac import ALL_ROLES, ORG_ASSIGNABLE, PLATFORM_ROLES, Perm, Principal
from app.models import (
    Attempt,
    Cohort,
    Consent,
    Event,
    JudgeScore,
    Lab,
    Organization,
    PromptVersion,
    RoleAssignment,
    Run,
    User,
)

router = APIRouter(tags=["manage"])

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code(prefix: str) -> str:
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(6))


# ---------------------------------------------------------------- organisations


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: str = "college"
    city: str | None = "Madurai"


@router.post("/orgs")
async def create_org(body: OrgIn, principal: CurrentPrincipal, session: Session):
    require(principal, Perm.ORG_MANAGE)  # platform admins only (no scope yet)
    org = Organization(**body.model_dump())
    session.add(org)
    await session.commit()
    return {"id": str(org.id), **body.model_dump()}


@router.get("/orgs")
async def list_orgs(principal: CurrentPrincipal, session: Session):
    q = select(Organization).order_by(Organization.name)
    if not principal.is_admin:
        q = q.where(Organization.id.in_(principal.scope_ids("org_admin", "org")))
    return [{"id": str(o.id), "name": o.name, "kind": o.kind, "city": o.city}
            for o in (await session.execute(q)).scalars()]


# ---------------------------------------------------------------- cohorts


class CohortIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


@router.post("/orgs/{org_id}/cohorts")
async def create_cohort(org_id: uuid.UUID, body: CohortIn, principal: CurrentPrincipal, session: Session):
    require(principal, Perm.COHORT_MANAGE, [("org", org_id)])
    if await session.get(Organization, org_id) is None:
        raise HTTPException(404, "Organisation not found")
    cohort = Cohort(org_id=org_id, name=body.name, join_code=new_code("C"))
    session.add(cohort)
    await session.commit()
    return {"id": str(cohort.id), "name": cohort.name, "join_code": cohort.join_code}


@router.get("/orgs/{org_id}/cohorts")
async def list_cohorts(org_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    rows = (await session.execute(select(Cohort).where(Cohort.org_id == org_id))).scalars().all()
    visible = [c for c in rows if principal.can(Perm.COHORT_VIEW, [("cohort", c.id), ("org", org_id)])]
    return [{"id": str(c.id), "name": c.name, "join_code": c.join_code} for c in visible]


@router.get("/mentor/cohorts")
async def mentor_cohorts(principal: CurrentPrincipal, session: Session):
    ids = principal.scope_ids("mentor", "cohort")
    org_ids = principal.scope_ids("org_admin", "org")
    q = select(Cohort)
    if not principal.is_admin:
        q = q.where((Cohort.id.in_(ids)) | (Cohort.org_id.in_(org_ids)))
    return [{"id": str(c.id), "name": c.name, "org_id": str(c.org_id), "join_code": c.join_code}
            for c in (await session.execute(q)).scalars()]


@router.get("/cohorts/{cohort_id}/progress")
async def cohort_progress(cohort_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    """Mentor view. Only learners with active `cohort_sharing` consent are included."""
    cohort = await session.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(404, "Cohort not found")
    require(principal, Perm.COHORT_VIEW, [("cohort", cohort_id), ("org", cohort.org_id)])
    members = select(RoleAssignment.user_id).where(
        RoleAssignment.scope_type == "cohort", RoleAssignment.scope_id == cohort_id, RoleAssignment.role == "learner")
    consenting = select(Consent.user_id).where(Consent.scope == "cohort_sharing", Consent.revoked_at.is_(None))
    users = (await session.execute(
        select(User).where(User.id.in_(members), User.id.in_(consenting)).order_by(User.display_name)
    )).scalars().all()
    total_members = (await session.execute(select(func.count()).select_from(members.subquery()))).scalar_one()
    out = []
    for u in users:
        stats = (await session.execute(
            select(func.count(), func.sum(func.cast(Attempt.passed, type_=func.count().type)),
                   func.avg(Attempt.best_score - Attempt.first_score))
            .where(Attempt.user_id == u.id)
        )).one()
        out.append({
            "user_id": str(u.id), "display_name": u.display_name, "xp": u.xp, "streak_days": u.streak_days,
            "labs_attempted": stats[0], "labs_passed": int(stats[1] or 0),
            "avg_improvement": round(float(stats[2]), 1) if stats[2] is not None else None,
            "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
        })
    return {"cohort": {"id": str(cohort.id), "name": cohort.name}, "members": total_members,
            "sharing": len(out), "learners": out}


# ---------------------------------------------------------------- events (hackathons)


class EventIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    starts_at: datetime
    ends_at: datetime
    lab_ids: list[str]
    grants_pro_days: int = Field(default=30, ge=0, le=365)
    entry_fee_inr: int = 200
    prize_inr: int = 10000


@router.post("/orgs/{org_id}/events")
async def create_event(org_id: uuid.UUID, body: EventIn, principal: CurrentPrincipal, session: Session):
    require(principal, Perm.EVENT_MANAGE, [("org", org_id)])
    labs = (await session.execute(select(Lab.id).where(Lab.id.in_(body.lab_ids)))).scalars().all()
    if set(labs) != set(body.lab_ids):
        raise HTTPException(422, "Unknown lab ids: " + ", ".join(sorted(set(body.lab_ids) - set(labs))))
    event = Event(org_id=org_id, join_code=new_code("H"), **body.model_dump())
    session.add(event)
    await session.commit()
    return _event_view(event)


def _event_view(e: Event) -> dict:
    return {"id": str(e.id), "org_id": str(e.org_id) if e.org_id else None, "name": e.name,
            "join_code": e.join_code, "starts_at": e.starts_at.isoformat(), "ends_at": e.ends_at.isoformat(),
            "lab_ids": e.lab_ids, "grants_pro_days": e.grants_pro_days, "entry_fee_inr": e.entry_fee_inr,
            "prize_inr": e.prize_inr}


@router.get("/orgs/{org_id}/events")
async def list_events(org_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    require(principal, Perm.EVENT_MANAGE, [("org", org_id)])
    rows = (await session.execute(select(Event).where(Event.org_id == org_id).order_by(Event.starts_at))).scalars()
    return [_event_view(e) for e in rows]


async def _event_for(session, principal: Principal, event_id: uuid.UUID, perm: Perm) -> Event:
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    require(principal, perm, [("event", event.id), ("org", event.org_id)])
    return event


@router.get("/events/{event_id}/leaderboard")
async def event_leaderboard(event_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    """Ranked on the iteration trail — best improvement and number of reflected revisions — not luck."""
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    participant = event_id in principal.scope_ids("learner", "event")
    if not (participant or principal.can(Perm.EVENT_JUDGE, [("event", event_id), ("org", event.org_id)])):
        raise HTTPException(403, "Not part of this event")
    rows = await _trail_stats(session, event_id)
    judge = (await session.execute(
        select(JudgeScore.user_id, func.avg(JudgeScore.craft + JudgeScore.reasoning))
        .where(JudgeScore.event_id == event_id).group_by(JudgeScore.user_id)
    )).all()
    judge_by_user = {u: float(s) for u, s in judge}
    board = []
    for r in rows:
        trail_score = round(0.6 * (r["best_improvement"] or 0) + 0.25 * (r["best_score"] or 0)
                            + 3 * min(r["reflected_revisions"], 5), 1)
        j = judge_by_user.get(r["user_id"])
        board.append({**r, "trail_score": trail_score, "judge_score": j,
                      "final": round(trail_score + (j * 2 if j is not None else 0), 1),
                      "is_me": r["user_id"] == principal.id})
    board.sort(key=lambda x: x["final"], reverse=True)
    for i, b in enumerate(board):
        b["rank"] = i + 1
        b["user_id"] = str(b["user_id"])
    return {"event": _event_view(event), "board": board}


async def _trail_stats(session, event_id: uuid.UUID) -> list[dict]:
    attempts = (await session.execute(select(Attempt).where(Attempt.event_id == event_id))).scalars().all()
    by_user: dict[uuid.UUID, dict] = {}
    for a in attempts:
        u = by_user.setdefault(a.user_id, {"user_id": a.user_id, "best_improvement": 0.0, "best_score": 0.0,
                                           "reflected_revisions": 0, "labs": 0})
        u["labs"] += 1
        if a.first_score is not None and a.best_score is not None:
            u["best_improvement"] = max(u["best_improvement"], a.best_score - a.first_score)
        u["best_score"] = max(u["best_score"], a.best_score or 0)
        u["reflected_revisions"] += sum(1 for p in a.prompts if p.version > 1 and p.technique_id)
    users = {u.id: u for u in (await session.execute(select(User).where(User.id.in_(by_user)))).scalars()}
    for uid, stats in by_user.items():
        stats["display_name"] = users[uid].display_name if uid in users else "Learner"
        stats["college"] = users[uid].college if uid in users else None
    return list(by_user.values())


@router.get("/events/{event_id}/trails")
async def event_trails(event_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    """Judge view: every participant's v1 → vN trail with scores and reflections."""
    await _event_for(session, principal, event_id, Perm.EVENT_JUDGE)
    attempts = (await session.execute(select(Attempt).where(Attempt.event_id == event_id))).scalars().all()
    prompt_ids = [p.id for a in attempts for p in a.prompts]
    runs = (await session.execute(
        select(Run).where(Run.prompt_version_id.in_(prompt_ids), Run.status == "done")
    )).scalars().all() if prompt_ids else []
    best_run = {}
    for r in runs:
        if r.prompt_version_id not in best_run or (r.score or 0) > (best_run[r.prompt_version_id].score or 0):
            best_run[r.prompt_version_id] = r
    users = {u.id: u for u in (await session.execute(
        select(User).where(User.id.in_({a.user_id for a in attempts}))
    )).scalars()} if attempts else {}
    mine = {s.user_id: s for s in (await session.execute(
        select(JudgeScore).where(JudgeScore.event_id == event_id, JudgeScore.judge_id == principal.id)
    )).scalars()}
    out: dict[uuid.UUID, dict] = {}
    for a in attempts:
        u = users.get(a.user_id)
        entry = out.setdefault(a.user_id, {
            "user_id": str(a.user_id), "display_name": u.display_name if u else "", "college": u.college if u else None,
            "attempts": [],
            "my_score": None if a.user_id not in mine else {
                "craft": mine[a.user_id].craft, "reasoning": mine[a.user_id].reasoning, "notes": mine[a.user_id].notes},
        })
        entry["attempts"].append({
            "lab_id": a.lab_id, "first_score": a.first_score, "best_score": a.best_score,
            "trail": [{
                "version": p.version, "text": p.text, "technique_id": p.technique_id, "reflection": p.reflection,
                "score": best_run[p.id].score if p.id in best_run else None,
                "delta": best_run[p.id].delta if p.id in best_run else None,
            } for p in a.prompts],
        })
    return list(out.values())


class JudgeScoreIn(BaseModel):
    craft: int = Field(ge=0, le=10)
    reasoning: int = Field(ge=0, le=10)
    notes: str | None = Field(default=None, max_length=2000)


@router.put("/events/{event_id}/judge-scores/{user_id}")
async def put_judge_score(event_id: uuid.UUID, user_id: uuid.UUID, body: JudgeScoreIn,
                          principal: CurrentPrincipal, session: Session):
    await _event_for(session, principal, event_id, Perm.EVENT_JUDGE)
    if user_id == principal.id:
        raise HTTPException(422, "Judges cannot score themselves")
    row = (await session.execute(select(JudgeScore).where(
        JudgeScore.event_id == event_id, JudgeScore.judge_id == principal.id, JudgeScore.user_id == user_id
    ))).scalar_one_or_none()
    if row is None:
        row = JudgeScore(event_id=event_id, judge_id=principal.id, user_id=user_id, **body.model_dump())
        session.add(row)
    else:
        row.craft, row.reasoning, row.notes = body.craft, body.reasoning, body.notes
    await session.commit()
    return {"ok": True}


@router.get("/events/{event_id}/export.csv")
async def export_event(event_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    from fastapi.responses import PlainTextResponse

    await _event_for(session, principal, event_id, Perm.EVENT_MANAGE)
    board = (await event_leaderboard(event_id, principal, session))["board"]
    lines = ["rank,name,college,best_improvement,best_score,reflected_revisions,trail_score,judge_score,final"]
    for b in board:
        name = (b["display_name"] or "").replace(",", " ")
        college = (b["college"] or "").replace(",", " ")
        lines.append(f'{b["rank"]},{name},{college},{b["best_improvement"]:.1f},{b["best_score"]:.1f},'
                     f'{b["reflected_revisions"]},{b["trail_score"]},{b["judge_score"] or ""},{b["final"]}')
    return PlainTextResponse("\n".join(lines), media_type="text/csv")


# ---------------------------------------------------------------- role assignment


class RoleAssignmentIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$", max_length=320)
    role: str
    scope_type: str
    scope_id: uuid.UUID | None = None


async def _scope_org(session, scope_type: str, scope_id: uuid.UUID | None) -> uuid.UUID | None:
    if scope_type == "org":
        return scope_id
    if scope_type == "cohort":
        c = await session.get(Cohort, scope_id)
        return c.org_id if c else None
    if scope_type == "event":
        e = await session.get(Event, scope_id)
        return e.org_id if e else None
    return None


@router.post("/role-assignments")
async def assign_role(body: RoleAssignmentIn, principal: CurrentPrincipal, session: Session):
    if body.role not in ALL_ROLES:
        raise HTTPException(422, "Unknown role")
    if (body.role in PLATFORM_ROLES) != (body.scope_type == "platform"):
        raise HTTPException(422, "admin/author are platform roles; other roles need an org, cohort or event scope")
    if body.scope_type != "platform" and body.scope_id is None:
        raise HTTPException(422, "scope_id is required")
    if body.scope_type == "platform":
        require(principal, Perm.ROLES_ASSIGN)  # admins only
    else:
        org_id = await _scope_org(session, body.scope_type, body.scope_id)
        if org_id is None and not principal.is_admin:
            raise HTTPException(404, "Scope not found")
        require(principal, Perm.ROLES_ASSIGN, [("org", org_id)])
        if not principal.is_admin and body.role not in ORG_ASSIGNABLE:
            raise HTTPException(403, "Org admins can only assign mentor, judge, learner or org_admin")
    user = (await session.execute(
        select(User).where(func.lower(User.email) == body.email.lower())
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "No user with that email has signed in yet")
    exists = (await session.execute(select(RoleAssignment).where(
        RoleAssignment.user_id == user.id, RoleAssignment.role == body.role,
        RoleAssignment.scope_type == body.scope_type, RoleAssignment.scope_id == body.scope_id,
    ))).scalar_one_or_none()
    if exists is None:
        exists = RoleAssignment(user_id=user.id, role=body.role, scope_type=body.scope_type,
                                scope_id=body.scope_id, granted_by=principal.id)
        session.add(exists)
        await session.commit()
    return {"id": str(exists.id)}


@router.get("/role-assignments")
async def list_role_assignments(principal: CurrentPrincipal, session: Session, scope_type: str | None = None,
                                scope_id: uuid.UUID | None = None):
    q = select(RoleAssignment, User.email, User.display_name).join(User, User.id == RoleAssignment.user_id)
    if scope_type:
        q = q.where(RoleAssignment.scope_type == scope_type)
    if scope_id:
        q = q.where(RoleAssignment.scope_id == scope_id)
    if not principal.is_admin:
        if scope_type is None or scope_id is None:
            raise HTTPException(422, "scope_type and scope_id are required")
        require(principal, Perm.ROLES_ASSIGN, [("org", await _scope_org(session, scope_type, scope_id))])
    rows = (await session.execute(q.order_by(RoleAssignment.created_at.desc()).limit(500))).all()
    return [{"id": str(ra.id), "email": email, "display_name": name, "role": ra.role, "scope_type": ra.scope_type,
             "scope_id": str(ra.scope_id) if ra.scope_id else None} for ra, email, name in rows]


@router.delete("/role-assignments/{assignment_id}")
async def revoke_role(assignment_id: uuid.UUID, principal: CurrentPrincipal, session: Session):
    ra = await session.get(RoleAssignment, assignment_id)
    if ra is None:
        raise HTTPException(404, "Not found")
    if ra.scope_type == "platform":
        require(principal, Perm.ROLES_ASSIGN)
    else:
        require(principal, Perm.ROLES_ASSIGN, [("org", await _scope_org(session, ra.scope_type, ra.scope_id))])
    await session.delete(ra)
    await session.commit()
    return {"ok": True}


# keep PromptVersion imported for typing of Attempt.prompts in trail views
__all__ = ["router", "PromptVersion"]
