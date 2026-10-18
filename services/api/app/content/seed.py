"""Project content/ into Postgres.  Usage: python -m app.content.seed"""

import asyncio
import sys

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.content.loader import ContentError, load_content
from app.db import dispose_engine, sessionmaker
from app.models import ConceptCard, Lab, Module, Rubric, Technique


async def _upsert(session: AsyncSession, model, rows: list[dict], key: str = "id") -> None:
    if not rows:
        return
    stmt = insert(model).values(rows)
    cols = {c: stmt.excluded[c] for c in rows[0] if c != key}
    await session.execute(stmt.on_conflict_do_update(index_elements=[key], set_=cols))


async def seed_content(session: AsyncSession) -> dict[str, int]:
    bundle = load_content(get_settings().content_dir)

    await _upsert(session, Technique, [
        {"id": t.id, "name": t.name, "category": t.category, "data": t.model_dump()} for t in bundle.techniques
    ])
    await _upsert(session, Rubric, [{"id": r.id, "version": r.version, "data": r.model_dump()} for r in bundle.rubrics])

    module_rows = []
    for m in bundle.modules:
        data = m.model_dump()
        data["course_id"] = bundle.course.id
        module_rows.append({
            "id": m.id, "course_id": bundle.course.id, "order": m.order, "title": m.title, "tier": m.tier,
            "data": data,
        })
    await _upsert(session, Module, module_rows)

    # Cards carry no learner data, so they are replaced wholesale.
    await session.execute(delete(ConceptCard))
    card_rows = []
    for m in bundle.modules:
        for pos, cid in enumerate(m.cards):
            card = bundle.cards[cid]
            card_rows.append({
                "id": cid, "module_id": m.id, "technique_id": card.technique, "position": pos,
                "data": card.model_dump(),
            })
    await _upsert(session, ConceptCard, card_rows)

    # Labs are upserted (attempts reference them); version changes when the brief/test set changes.
    lab_rows = []
    for m in bundle.modules:
        for pos, lid in enumerate(m.labs):
            lab = bundle.labs[lid]
            lab_rows.append({
                "id": lid, "module_id": m.id, "position": pos, "version": lab.content_version(),
                "data": lab.model_dump(),
            })
    await _upsert(session, Lab, lab_rows)
    await session.commit()

    count = (await session.execute(select(Lab.id))).all()
    return {"modules": len(module_rows), "cards": len(card_rows), "labs": len(count)}


async def _main() -> None:
    try:
        async with sessionmaker()() as session:
            print(await seed_content(session))
    except ContentError as exc:
        print("Content problems:\n" + "\n".join(f"  - {p}" for p in exc.problems), file=sys.stderr)
        sys.exit(1)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
