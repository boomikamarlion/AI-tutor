"""XP, levels, streaks and technique mastery.

One mechanic, aligned with learning: XP comes from *measured improvement attributed to a
named technique*, not from clicking. Mastery of a technique = it produced a real gain on two
different labs.
"""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.usage import today_ist
from app.models import Attempt, Lab, TechniqueMastery, User, XpEntry

PASS_SCORE = 70.0
XP_RUN = 5
XP_RUN_DAILY_CAP = 10  # runs per day that earn the flat run XP
XP_IMPROVEMENT_CAP = 40
XP_FIRST_PASS = 50
XP_MODULE_COMPLETE = 100
XP_MASTERY = 30
XP_PREDICTION = 3
MASTERY_DELTA = 5.0
MASTERY_LABS = 2


def level_for(xp: int) -> int:
    return int(math.sqrt(max(xp, 0) / 50)) + 1


def xp_for_level(level: int) -> int:
    return 50 * (level - 1) ** 2


async def _grant(session: AsyncSession, user: User, amount: int, reason: str, ref: str | None) -> int:
    if amount <= 0:
        return 0
    session.add(XpEntry(user_id=user.id, amount=amount, reason=reason, ref=ref))
    user.xp += amount
    return amount


def touch_streak(user: User) -> None:
    today = today_ist()
    if user.streak_last_date == today:
        return
    if user.streak_last_date == today - timedelta(days=1):
        user.streak_days += 1
    else:
        user.streak_days = 1
    user.streak_last_date = today


async def award_for_run(
    session: AsyncSession,
    *,
    user: User,
    attempt: Attempt,
    lab: Lab,
    run_ref: str,
    score: float,
    delta: float | None,
    technique_id: str | None,
    was_passed: bool,
) -> list[dict]:
    """Returns the list of awards (for the UI's reveal)."""
    awards: list[dict] = []

    runs_today = (await session.execute(
        select(func.count()).select_from(XpEntry).where(
            XpEntry.user_id == user.id, XpEntry.reason == "run",
            XpEntry.created_at >= datetime.now(UTC) - timedelta(hours=24),
        )
    )).scalar_one()
    if runs_today < XP_RUN_DAILY_CAP and await _grant(session, user, XP_RUN, "run", run_ref):
        awards.append({"kind": "run", "xp": XP_RUN})

    if delta is not None and delta > 0 and technique_id:
        gain = min(XP_IMPROVEMENT_CAP, round(delta))
        if await _grant(session, user, gain, "improvement", run_ref):
            awards.append({"kind": "improvement", "xp": gain, "technique": technique_id, "delta": delta})

    if technique_id:
        awards.extend(await _update_mastery(session, user, technique_id, lab.id, delta))

    if score >= PASS_SCORE and not was_passed:
        attempt.passed = True
        await _grant(session, user, XP_FIRST_PASS, "lab_pass", lab.id)
        awards.append({"kind": "lab_pass", "xp": XP_FIRST_PASS, "lab_id": lab.id})
        if await _module_complete(session, user, lab):
            await _grant(session, user, XP_MODULE_COMPLETE, "module_complete", lab.module_id)
            awards.append({"kind": "module_complete", "xp": XP_MODULE_COMPLETE, "module_id": lab.module_id})

    touch_streak(user)
    return awards


async def _update_mastery(
    session: AsyncSession, user: User, technique_id: str, lab_id: str, delta: float | None
) -> list[dict]:
    m = await session.get(TechniqueMastery, (user.id, technique_id))
    if m is None:
        m = TechniqueMastery(user_id=user.id, technique_id=technique_id, uses=0, improving_uses=0, labs=[],
                             best_delta=0.0)
        session.add(m)
    m.uses += 1
    if delta is not None and delta >= MASTERY_DELTA:
        m.improving_uses += 1
        if lab_id not in m.labs:
            m.labs = [*m.labs, lab_id]
        m.best_delta = max(m.best_delta, delta)
    if m.mastered_at is None and len(m.labs) >= MASTERY_LABS:
        m.mastered_at = datetime.now(UTC)
        await _grant(session, user, XP_MASTERY, "mastery", technique_id)
        return [{"kind": "mastery", "xp": XP_MASTERY, "technique": technique_id}]
    return []


async def _module_complete(session: AsyncSession, user: User, lab: Lab) -> bool:
    lab_ids = (await session.execute(select(Lab.id).where(Lab.module_id == lab.module_id))).scalars().all()
    passed = (await session.execute(
        select(func.count(func.distinct(Attempt.lab_id))).where(
            Attempt.user_id == user.id, Attempt.lab_id.in_(lab_ids), Attempt.passed.is_(True)
        )
    )).scalar_one()
    return passed >= len(lab_ids)


async def award_prediction(session: AsyncSession, user: User, run_ref: str) -> int:
    return await _grant(session, user, XP_PREDICTION, "prediction", run_ref)
