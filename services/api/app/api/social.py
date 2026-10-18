"""The light social layer: a live, anonymised feed of improvements and weekly leaderboards."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import CurrentPrincipal, Session
from app.auth.rbac import Perm
from app.models import Attempt, Cohort, Lab, PromptVersion, RoleAssignment, Run, Technique, User, XpEntry

router = APIRouter(tags=["social"])


@router.get("/feed")
async def feed(principal: CurrentPrincipal, session: Session):
    since = datetime.now(UTC) - timedelta(hours=24)
    rows = (await session.execute(
        select(Run.delta, Run.score, Run.finished_at, Lab.id, Lab.data["title"].astext, PromptVersion.technique_id)
        .join(PromptVersion, Run.prompt_version_id == PromptVersion.id)
        .join(Attempt, PromptVersion.attempt_id == Attempt.id)
        .join(Lab, Attempt.lab_id == Lab.id)
        .where(Run.status == "done", Run.finished_at >= since, Run.delta > 0)
        .order_by(Run.finished_at.desc()).limit(30)
    )).all()
    names = {t.id: t.name for t in (await session.execute(select(Technique))).scalars()}
    activity = [
        {"lab_id": lab_id, "lab_title": title, "delta": delta, "score": score,
         "technique": names.get(tech) if tech else None, "at": at.isoformat()}
        for delta, score, at, lab_id, title, tech in rows
    ]
    counts = (await session.execute(
        select(Attempt.lab_id, func.count(func.distinct(Run.user_id)))
        .join(PromptVersion, PromptVersion.attempt_id == Attempt.id)
        .join(Run, Run.prompt_version_id == PromptVersion.id)
        .where(Run.created_at >= since).group_by(Attempt.lab_id)
    )).all()
    trending = (await session.execute(
        select(PromptVersion.technique_id, func.count())
        .join(Run, Run.prompt_version_id == PromptVersion.id)
        .where(Run.created_at >= since, PromptVersion.technique_id.is_not(None), Run.delta > 0)
        .group_by(PromptVersion.technique_id).order_by(func.count().desc()).limit(5)
    )).all()
    return {
        "activity": activity,
        "learners_today_by_lab": {lab_id: n for lab_id, n in counts},
        "trending_techniques": [{"id": t, "name": names.get(t, t), "improvements": n} for t, n in trending],
    }


@router.get("/leaderboard")
async def leaderboard(principal: CurrentPrincipal, session: Session, cohort_id: uuid.UUID | None = None):
    """Weekly XP. Global, or within a cohort the caller belongs to / mentors."""
    since = datetime.now(UTC) - timedelta(days=7)
    q = (select(User.id, User.display_name, User.college, func.sum(XpEntry.amount).label("xp"))
         .join(XpEntry, XpEntry.user_id == User.id).where(XpEntry.created_at >= since))
    if cohort_id is not None:
        cohort = await session.get(Cohort, cohort_id)
        if cohort is None:
            raise HTTPException(404, "Cohort not found")
        member = cohort_id in principal.scope_ids("learner", "cohort")
        if not (member or principal.can(Perm.COHORT_VIEW, [("cohort", cohort_id), ("org", cohort.org_id)])):
            raise HTTPException(403, "Not a member of this cohort")
        members = select(RoleAssignment.user_id).where(
            RoleAssignment.scope_type == "cohort", RoleAssignment.scope_id == cohort_id,
            RoleAssignment.role == "learner")
        q = q.where(User.id.in_(members))
    rows = (await session.execute(q.group_by(User.id).order_by(func.sum(XpEntry.amount).desc()).limit(50))).all()
    return [
        {"rank": i + 1, "display_name": name or "Learner", "college": college, "xp": int(xp),
         "is_me": uid == principal.id}
        for i, (uid, name, college, xp) in enumerate(rows)
    ]
