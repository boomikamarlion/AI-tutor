from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, Session
from app.api.serializers import lab_public, lab_summary
from app.auth.rbac import Perm, Principal
from app.config import get_settings
from app.content.loader import load_content
from app.engine.usage import has_pro
from app.models import Attempt, ConceptCard, Event, Lab, Module, Rubric, Technique

router = APIRouter(tags=["course"])


def module_unlocked(principal: Principal, module: Module) -> bool:
    return module.tier == "free" or has_pro(principal) or principal.can(Perm.CONTENT_PREVIEW)


async def lab_unlocked(session, principal: Principal, lab: Lab) -> bool:
    module = await session.get(Module, lab.module_id)
    if module and module_unlocked(principal, module):
        return True
    event_ids = principal.scope_ids("learner", "event")
    if event_ids:
        events = (await session.execute(select(Event).where(Event.id.in_(event_ids)))).scalars()
        return any(lab.id in e.lab_ids for e in events)
    return False


async def _best_attempts(session, user_id) -> dict[str, Attempt]:
    best: dict[str, Attempt] = {}
    for a in (await session.execute(select(Attempt).where(Attempt.user_id == user_id))).scalars():
        if a.lab_id not in best or (a.best_score or 0) > (best[a.lab_id].best_score or 0):
            best[a.lab_id] = a
    return best


@router.get("/course")
async def course(principal: CurrentPrincipal, session: Session):
    bundle_course = load_content(get_settings().content_dir).course
    modules = (await session.execute(select(Module).order_by(Module.order))).scalars().all()
    labs = (await session.execute(select(Lab).order_by(Lab.position))).scalars().all()
    best = await _best_attempts(session, principal.id)
    out = []
    for m in modules:
        mlabs = [lab for lab in labs if lab.module_id == m.id]
        out.append({
            "id": m.id,
            "order": m.order,
            "title": m.title,
            "summary": m.data.get("summary"),
            "design_stage": m.data.get("design_stage"),
            "tier": m.tier,
            "unlocked": module_unlocked(principal, m),
            "estimated_minutes": m.data.get("estimated_minutes"),
            "techniques": m.data.get("techniques", []),
            "labs_total": len(mlabs),
            "labs_passed": sum(1 for lab in mlabs if best.get(lab.id) and best[lab.id].passed),
        })
    return {
        "id": bundle_course.id,
        "title": bundle_course.title,
        "summary": bundle_course.summary,
        "product_case": bundle_course.product_case,
        "modules": out,
    }


@router.get("/modules/{module_id}")
async def module_detail(module_id: str, principal: CurrentPrincipal, session: Session):
    m = await session.get(Module, module_id)
    if m is None:
        raise HTTPException(404, "Module not found")
    cards = (await session.execute(
        select(ConceptCard).where(ConceptCard.module_id == module_id).order_by(ConceptCard.position)
    )).scalars().all()
    labs = (await session.execute(
        select(Lab).where(Lab.module_id == module_id).order_by(Lab.position)
    )).scalars().all()
    best = await _best_attempts(session, principal.id)
    unlocked = module_unlocked(principal, m)
    return {
        **m.data,
        "unlocked": unlocked,
        # Concept cards are always visible: they are the free "trailer" for a pro module.
        "cards": [c.data for c in cards],
        "labs": [lab_summary(lab, best.get(lab.id)) for lab in labs],
    }


@router.get("/cards")
async def cards_by_technique(technique: str, session: Session, principal: CurrentPrincipal):
    rows = (await session.execute(select(ConceptCard).where(ConceptCard.technique_id == technique))).scalars()
    return [c.data for c in rows]


@router.get("/techniques")
async def techniques(session: Session, principal: CurrentPrincipal):
    rows = (await session.execute(select(Technique).order_by(Technique.category, Technique.name))).scalars()
    return [t.data for t in rows]


@router.get("/labs/{lab_id}")
async def lab_detail(lab_id: str, principal: CurrentPrincipal, session: Session):
    lab = await session.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(404, "Lab not found")
    if not await lab_unlocked(session, principal, lab):
        raise HTTPException(402, "This lab is part of the Pro plan")
    data = lab_public(lab, include_hidden=principal.can(Perm.CONTENT_PREVIEW))
    rubric = await session.get(Rubric, data["rubric"]["base"])
    data["criteria"] = [*(rubric.data["criteria"] if rubric else []), *data["rubric"]["extra_criteria"]]
    return data
