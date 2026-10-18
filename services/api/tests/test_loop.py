"""End-to-end core loop: brief → v1 → run → critique → v2 (named technique) → visible delta + XP."""

from sqlalchemy import select

from app.content.schema import LabSpec
from app.db import sessionmaker
from app.models import Lab, UsageEntry, User
from tests.conftest import auth, run_now

LAB = "m00-lab-canteen-feedback"


async def _lab_spec() -> LabSpec:
    async with sessionmaker()() as s:
        return LabSpec(**(await s.get(Lab, LAB)).data)


async def test_requires_auth(client):
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_course_locks_and_hides_reference(client):
    h = auth("learner1@ecosys.test")
    course = (await client.get("/course", headers=h)).json()
    assert len(course["modules"]) == 12
    by_id = {m["id"]: m for m in course["modules"]}
    assert by_id["m00-orientation"]["unlocked"] and not by_id["m05-reasoning"]["unlocked"]

    lab = (await client.get(f"/labs/{LAB}", headers=h)).json()
    assert "reference_prompt" not in lab
    assert all("answer" not in p for p in lab["predictions"])
    assert lab["criteria"] and lab["test_cases"]

    pro_lab = (await client.get("/modules/m05-reasoning", headers=h)).json()["labs"][0]["id"]
    assert (await client.get(f"/labs/{pro_lab}", headers=h)).status_code == 402

    author = auth("author@ecosys.test", roles=["author"])
    full = (await client.get(f"/labs/{pro_lab}", headers=author)).json()
    assert "reference_prompt" in full


async def test_full_loop_with_delta_and_xp(client, redis):
    h = auth("loop@ecosys.test", "Loop Learner")
    spec = await _lab_spec()
    attempt = (await client.post(f"/labs/{LAB}/attempt", headers=h)).json()

    weak = "Summarise this feedback."
    v1 = (await client.post(f"/attempts/{attempt['id']}/prompts", headers=h, json={"text": weak})).json()
    assert v1["version"] == 1 and "server" in v1["lint"]
    r1 = (await client.post(f"/prompts/{v1['id']}/runs", headers=h)).json()

    # prediction-before-reveal while the run is in flight
    if spec.predictions:
        p = spec.predictions[0]
        res = (await client.post(f"/runs/{r1['id']}/predictions", headers=h,
                                 json={"prediction_id": p.id, "choice": p.answer})).json()
        assert res["correct"] is True

    await run_now(redis, r1["id"])
    run1 = (await client.get(f"/runs/{r1['id']}", headers=h)).json()
    assert run1["status"] == "done", run1
    assert len(run1["cases"]) == len(spec.test_cases)
    assert all(c["output"] for c in run1["cases"])
    assert run1["critique"]["scores"] and run1["delta"] is None

    # revisions must name a technique
    bad = await client.post(f"/attempts/{attempt['id']}/prompts", headers=h, json={"text": spec.reference_prompt})
    assert bad.status_code == 422
    v2 = (await client.post(f"/attempts/{attempt['id']}/prompts", headers=h, json={
        "text": spec.reference_prompt, "technique_id": "constraints", "reflection": "Added limits and format",
    })).json()
    r2 = (await client.post(f"/prompts/{v2['id']}/runs", headers=h)).json()
    await run_now(redis, r2["id"])
    run2 = (await client.get(f"/runs/{r2['id']}", headers=h)).json()
    assert run2["status"] == "done"
    assert run2["score"] > run1["score"]
    assert run2["delta"] == round(run2["score"] - run1["score"], 1)
    assert run2["xp_awarded"] > 0

    me = (await client.get("/me", headers=h)).json()
    assert me["xp"] >= run1["xp_awarded"] + run2["xp_awarded"]
    assert me["streak_days"] == 1

    full = (await client.get(f"/attempts/{attempt['id']}", headers=h)).json()
    assert [p["version"] for p in full["prompts"]] == [1, 2]

    # finished runs stream a single final event
    async with client.stream("GET", f"/runs/{r2['id']}/stream", headers=h) as resp:
        body = (await resp.aread()).decode()
    assert "event: final" in body

    # rerunning the same prompt is served from cache (and costs nothing)
    r3 = (await client.post(f"/prompts/{v2['id']}/runs", headers=h)).json()
    await run_now(redis, r3["id"])
    run3 = (await client.get(f"/runs/{r3['id']}", headers=h)).json()
    assert all(c["cache_hit"] for c in run3["cases"])
    assert run3["score"] == run2["score"]

    feed = (await client.get("/feed", headers=h)).json()
    assert any(a["lab_id"] == LAB for a in feed["activity"])


async def test_other_users_cannot_see_attempts(client):
    a = auth("owner@ecosys.test")
    b = auth("snoop@ecosys.test")
    attempt = (await client.post(f"/labs/{LAB}/attempt", headers=a)).json()
    assert (await client.get(f"/attempts/{attempt['id']}", headers=b)).status_code == 404


async def test_budget_hard_cap(client):
    h = auth("broke@ecosys.test")
    await client.get("/me", headers=h)
    async with sessionmaker()() as s:
        user = (await s.execute(select(User).where(User.email == "broke@ecosys.test"))).scalar_one()
        from app.engine.usage import today_ist

        s.add(UsageEntry(user_id=user.id, day=today_ist(), role="run", deployment="gpt-6-luna", cost_usd=1.0))
        await s.commit()
    attempt = (await client.post(f"/labs/{LAB}/attempt", headers=h)).json()
    v1 = (await client.post(f"/attempts/{attempt['id']}/prompts", headers=h, json={"text": "Do it"})).json()
    assert (await client.post(f"/prompts/{v1['id']}/runs", headers=h)).status_code == 429


async def test_consent_grant_and_revoke(client):
    h = auth("consent@ecosys.test")
    r = (await client.post("/me/consents", headers=h, json={"scope": "cohort_sharing", "granted": True})).json()
    assert "cohort_sharing" in r["consents"]
    r = (await client.post("/me/consents", headers=h, json={"scope": "cohort_sharing", "granted": False})).json()
    assert "cohort_sharing" not in r["consents"]
    assert (await client.post("/me/consents", headers=h, json={"scope": "x", "granted": True})).status_code == 422
