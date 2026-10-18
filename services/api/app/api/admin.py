"""Platform administration: users, plans, credit burn, content reload."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import CurrentPrincipal, Session, require
from app.auth.rbac import Perm
from app.content.loader import ContentError
from app.content.seed import seed_content
from app.engine.usage import today_ist
from app.gateway.router import credit_pool_usd
from app.models import RoleAssignment, Run, UsageEntry, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def users(principal: CurrentPrincipal, session: Session, q: str | None = None, limit: int = 50):
    require(principal, Perm.USERS_VIEW)
    stmt = select(User).order_by(User.created_at.desc()).limit(min(limit, 200))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.display_name).like(like)))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {"id": str(u.id), "email": u.email, "display_name": u.display_name, "college": u.college, "plan": u.plan,
         "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None, "xp": u.xp,
         "roles": [{"role": r.role, "scope_type": r.scope_type, "scope_id": str(r.scope_id) if r.scope_id else None,
                    "id": str(r.id)} for r in u.roles],
         "created_at": u.created_at.isoformat(), "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None}
        for u in rows
    ]


class PlanChange(BaseModel):
    plan: str
    days: int | None = None


@router.patch("/users/{user_id}/plan")
async def set_plan(user_id: uuid.UUID, body: PlanChange, principal: CurrentPrincipal, session: Session):
    require(principal, Perm.USERS_VIEW)
    if body.plan not in {"free", "pro"}:
        raise HTTPException(422, "plan must be free or pro")
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    u.plan = body.plan
    u.plan_expires_at = datetime.now(UTC) + timedelta(days=body.days) if body.days else None
    await session.commit()
    return {"ok": True}


@router.get("/usage")
async def usage(principal: CurrentPrincipal, session: Session, days: int = 14):
    require(principal, Perm.USAGE_VIEW)
    since = today_ist() - timedelta(days=days - 1)
    daily = (await session.execute(
        select(UsageEntry.day, UsageEntry.role, UsageEntry.deployment, func.sum(UsageEntry.cost_usd),
               func.sum(UsageEntry.input_tokens), func.sum(UsageEntry.output_tokens), func.count(),
               func.sum(func.cast(UsageEntry.cache_hit, type_=func.count().type)))
        .where(UsageEntry.day >= since)
        .group_by(UsageEntry.day, UsageEntry.role, UsageEntry.deployment).order_by(UsageEntry.day)
    )).all()
    total_spent = float((await session.execute(select(func.coalesce(func.sum(UsageEntry.cost_usd), 0.0)))).scalar_one())
    active = (await session.execute(
        select(func.count(func.distinct(UsageEntry.user_id))).where(UsageEntry.day >= since)
    )).scalar_one()
    runs = (await session.execute(
        select(Run.status, func.count()).where(Run.created_at >= datetime.now(UTC) - timedelta(days=days))
        .group_by(Run.status)
    )).all()
    pool = credit_pool_usd()
    last7 = [r for r in daily if r[0] >= today_ist() - timedelta(days=6)]
    burn_7d = sum(float(r[3] or 0) for r in last7) / 7
    return {
        "credit_pool_usd": pool,
        "spent_total_usd": round(total_spent, 2),
        "remaining_usd": round(pool - total_spent, 2),
        "burn_per_day_7d_usd": round(burn_7d, 2),
        "runway_days": round((pool - total_spent) / burn_7d) if burn_7d > 0 else None,
        "active_learners": active,
        "cost_per_active_learner_usd": round(sum(float(r[3] or 0) for r in daily) / active, 4) if active else None,
        "runs_by_status": {s: n for s, n in runs},
        "daily": [
            {"day": d.isoformat(), "role": role, "deployment": dep, "cost_usd": round(float(c or 0), 4),
             "input_tokens": int(i or 0), "output_tokens": int(o or 0), "calls": n, "cache_hits": int(h or 0)}
            for d, role, dep, c, i, o, n, h in daily
        ],
    }


@router.post("/content/reload")
async def reload_content(principal: CurrentPrincipal, session: Session):
    require(principal, Perm.CONTENT_RELOAD)
    try:
        return await seed_content(session)
    except ContentError as exc:
        raise HTTPException(422, {"problems": exc.problems}) from exc


@router.get("/stats")
async def stats(principal: CurrentPrincipal, session: Session):
    require(principal, Perm.USERS_VIEW)
    week = datetime.now(UTC) - timedelta(days=7)
    return {
        "users": (await session.execute(select(func.count()).select_from(User))).scalar_one(),
        "weekly_active": (await session.execute(
            select(func.count()).select_from(User).where(User.last_seen_at >= week))).scalar_one(),
        "pro_users": (await session.execute(
            select(func.count()).select_from(User).where(User.plan == "pro"))).scalar_one(),
        "staff": (await session.execute(
            select(func.count(func.distinct(RoleAssignment.user_id))).where(RoleAssignment.scope_type == "platform")
        )).scalar_one(),
    }
