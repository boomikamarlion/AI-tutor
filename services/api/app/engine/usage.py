"""Entitlements, per-learner budgets and the usage ledger."""

import uuid
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Principal
from app.gateway import router
from app.models import UsageEntry, User

IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> date:
    return datetime.now(IST).date()


def has_pro(principal: Principal) -> bool:
    if principal.is_staff:
        return True
    return user_has_pro(principal.user)


def user_has_pro(user: User) -> bool:
    if user.plan != "pro":
        return False
    return user.plan_expires_at is None or user.plan_expires_at > datetime.now(UTC)


def budget_tier(principal: Principal) -> str:
    if principal.is_staff:
        return "staff"
    return "pro" if has_pro(principal) else "free"


async def spent_today(session: AsyncSession, user_id: uuid.UUID) -> float:
    q = select(func.coalesce(func.sum(UsageEntry.cost_usd), 0.0)).where(
        UsageEntry.user_id == user_id, UsageEntry.day == today_ist()
    )
    return float((await session.execute(q)).scalar_one())


class BudgetDecision:
    def __init__(self, allowed: bool, cache_only: bool, spent: float, soft: float, hard: float):
        self.allowed, self.cache_only, self.spent, self.soft, self.hard = allowed, cache_only, spent, soft, hard

    def as_dict(self) -> dict:
        return {"spent_usd": round(self.spent, 4), "soft_usd": self.soft, "hard_usd": self.hard,
                "cache_only": self.cache_only, "allowed": self.allowed}


async def check_budget(session: AsyncSession, principal: Principal) -> BudgetDecision:
    soft, hard = router.budget(budget_tier(principal))
    spent = await spent_today(session, principal.id)
    return BudgetDecision(allowed=spent < hard, cache_only=spent >= soft, spent=spent, soft=soft, hard=hard)


def record_usage(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    role: str,
    deployment: str,
    input_tokens: int,
    output_tokens: int,
    cache_hit: bool,
) -> float:
    cost = 0.0 if cache_hit else router.price(deployment).cost(input_tokens, output_tokens)
    session.add(UsageEntry(
        user_id=user_id, day=today_ist(), role=role, deployment=deployment, input_tokens=input_tokens,
        output_tokens=output_tokens, cost_usd=cost, cache_hit=cache_hit,
    ))
    return cost
