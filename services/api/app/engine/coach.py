"""The coach: a Socratic tutor agent (Microsoft Agent Framework) with read-only tools over the
learner's lab, latest critique and the concept-card library. It never writes the prompt for them."""

from typing import Annotated

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import Principal
from app.content.schema import LabSpec
from app.engine.usage import check_budget, record_usage
from app.gateway.providers import FakeProvider, get_provider
from app.gateway.router import role_config
from app.models import Attempt, ConceptCard, Critique, Lab, PromptVersion, Run, Technique

COACH_INSTRUCTIONS = """You are a warm, sharp prompt-engineering coach for Indian college students.
Use the tools to look at the learner's brief, their latest prompt and its critique before answering.
Rules:
- Never write or rewrite the learner's prompt, and never give a finished prompt — not even "for example".
- Ask at most one guiding question, then give one concrete direction tied to a named technique.
- Point to the concept card that explains the technique when one exists.
- Keep answers under 120 words. Plain English. No flattery."""


async def _context(session: AsyncSession, attempt: Attempt) -> dict:
    lab = LabSpec(**(await session.get(Lab, attempt.lab_id)).data)  # type: ignore[union-attr]
    latest = (await session.execute(
        select(PromptVersion).where(PromptVersion.attempt_id == attempt.id).order_by(PromptVersion.version.desc())
    )).scalars().first()
    critique = None
    if latest:
        critique = (await session.execute(
            select(Critique).join(Run, Run.id == Critique.run_id).where(Run.prompt_version_id == latest.id)
            .order_by(Critique.created_at.desc())
        )).scalars().first()
    cards = {c.id: c.data for c in (await session.execute(select(ConceptCard))).scalars()}
    techniques = {t.id: t.data for t in (await session.execute(select(Technique))).scalars()}
    return {"lab": lab, "prompt": latest, "critique": critique, "cards": cards, "techniques": techniques}


async def ask_coach(session: AsyncSession, principal: Principal, attempt: Attempt, question: str) -> str:
    ctx = await _context(session, attempt)
    budget = await check_budget(session, principal)
    if not budget.allowed or budget.cache_only:
        return _offline_answer(ctx)
    provider = get_provider()
    if isinstance(provider, FakeProvider):
        return _offline_answer(ctx)

    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient

    lab: LabSpec = ctx["lab"]

    def get_brief() -> str:
        """Return the lab brief and its success criteria."""
        return lab.brief + "\n\nSuccess criteria:\n" + "\n".join(f"- {s}" for s in lab.success_criteria)

    def get_latest_prompt_and_critique() -> str:
        """Return the learner's latest prompt and the critic's scores and diagnoses for it."""
        p, c = ctx["prompt"], ctx["critique"]
        if p is None:
            return "The learner has not written a prompt yet."
        out = f"Prompt v{p.version}:\n{p.text}\n"
        if c is not None:
            out += f"\nScore {c.total}/100. {c.summary}\n"
            for cid, s in c.scores.items():
                out += f"- {cid}: {s['score']}/4 — {s['prompt_diagnosis']}\n"
        return out

    def find_concept_card(technique_id: Annotated[str, "A technique id from the vocabulary"]) -> str:
        """Return the concept card(s) that teach a technique, plus its definition."""
        t = ctx["techniques"].get(technique_id)
        cards = [c for c in ctx["cards"].values() if c.get("technique") == technique_id]
        if not t:
            return "Unknown technique. Known ids: " + ", ".join(ctx["techniques"])
        return f"{t['name']}: {t['definition']}\nCards: " + "; ".join(f"{c['title']} — {c['takeaway']}" for c in cards)

    cfg = role_config("coach")
    client = FoundryChatClient(project_endpoint=provider._endpoint, model=cfg.deployment,  # type: ignore[attr-defined]
                               credential=provider._credential)  # type: ignore[attr-defined]
    agent = Agent(client=client, instructions=COACH_INSTRUCTIONS, name="coach",
                  tools=[get_brief, get_latest_prompt_and_critique, find_concept_card])
    options = {"max_tokens": cfg.max_output_tokens, "store": False}
    if cfg.reasoning_effort:
        options["reasoning"] = {"effort": cfg.reasoning_effort}
    response = await agent.run(question, options=options)
    usage = response.usage_details or {}
    record_usage(session, user_id=principal.id, role="coach", deployment=cfg.deployment,
                 input_tokens=int(usage.get("input_token_count") or 0),
                 output_tokens=int(usage.get("output_token_count") or 0), cache_hit=False)
    await session.commit()
    return response.text


def _offline_answer(ctx: dict) -> str:
    c = ctx["critique"]
    if c is None:
        return ("Start by reading the brief twice: who is it for, and what exactly must come out? "
                "Write a first prompt and run it — the critique will show you where to focus.")
    weakest = min(c.scores.items(), key=lambda kv: kv[1]["score"], default=None)
    focus = c.next_focus or ""
    t = ctx["techniques"].get(focus, {})
    card = next((x for x in ctx["cards"].values() if x.get("technique") == focus), None)
    msg = ""
    if weakest:
        msg += f"Your weakest criterion is **{weakest[0].replace('_', ' ')}** ({weakest[1]['score']}/4). "
        msg += f"The critic says: {weakest[1]['prompt_diagnosis']} "
    if t:
        msg += f"Try **{t['name']}** — {t['definition']} "
    if card:
        msg += f"The card “{card['title']}” shows how."
    return msg.strip()
