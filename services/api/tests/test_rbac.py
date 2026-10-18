"""Role-based access: platform admin, org_admin, mentor, judge, learner."""

from datetime import UTC, datetime, timedelta

from tests.conftest import auth, run_now

ADMIN = auth("admin@ecosys.test", "Admin")


async def _signin(client, email):
    h = auth(email, email.split("@")[0])
    await client.get("/me", headers=h)
    return h


async def test_bootstrap_admin_and_learner_denied(client):
    me = (await client.get("/me", headers=ADMIN)).json()
    assert "admin" in me["roles"]["platform"]
    learner = await _signin(client, "plain@ecosys.test")
    assert (await client.post("/orgs", headers=learner, json={"name": "X College"})).status_code == 403
    assert (await client.get("/admin/usage", headers=learner)).status_code == 403
    assert (await client.post("/admin/content/reload", headers=learner)).status_code == 403


async def test_org_cohort_mentor_flow(client):
    org = (await client.post("/orgs", headers=ADMIN, json={"name": "American College"})).json()
    other = (await client.post("/orgs", headers=ADMIN, json={"name": "Lady Doak College"})).json()

    oa = await _signin(client, "orgadmin@ecosys.test")
    r = await client.post("/role-assignments", headers=ADMIN, json={
        "email": "orgadmin@ecosys.test", "role": "org_admin", "scope_type": "org", "scope_id": org["id"]})
    assert r.status_code == 200

    cohort = (await client.post(f"/orgs/{org['id']}/cohorts", headers=oa, json={"name": "BCA 2nd year"})).json()
    assert cohort["join_code"].startswith("C")
    assert (await client.post(f"/orgs/{other['id']}/cohorts", headers=oa, json={"name": "nope"})).status_code == 403

    # org_admin may appoint a mentor in their org, but not a platform admin
    await _signin(client, "mentor@ecosys.test")
    assert (await client.post("/role-assignments", headers=oa, json={
        "email": "mentor@ecosys.test", "role": "mentor", "scope_type": "cohort", "scope_id": cohort["id"]
    })).status_code == 200
    assert (await client.post("/role-assignments", headers=oa, json={
        "email": "mentor@ecosys.test", "role": "admin", "scope_type": "platform"})).status_code == 403
    mentor = auth("mentor@ecosys.test")

    # two learners join; only the consenting one is visible to the mentor
    s1 = await _signin(client, "s1@ecosys.test")
    s2 = await _signin(client, "s2@ecosys.test")
    for h in (s1, s2):
        joined = (await client.post("/me/join", headers=h, json={"code": cohort["join_code"]})).json()
        assert joined["joined"] == "cohort"
    await client.post("/me/consents", headers=s1, json={"scope": "cohort_sharing", "granted": True})
    prog = (await client.get(f"/cohorts/{cohort['id']}/progress", headers=mentor)).json()
    assert prog["members"] == 2 and prog["sharing"] == 1
    assert prog["learners"][0]["display_name"] == "s1"

    assert (await client.get(f"/cohorts/{cohort['id']}/progress", headers=s1)).status_code == 403
    board = (await client.get(f"/leaderboard?cohort_id={cohort['id']}", headers=s2))
    assert board.status_code == 200


async def test_hackathon_event_judging(client, redis):
    org = (await client.post("/orgs", headers=ADMIN, json={"name": "Thiagarajar College"})).json()
    now = datetime.now(UTC)
    event = (await client.post(f"/orgs/{org['id']}/events", headers=ADMIN, json={
        "name": "Prompt Hackathon — TCE", "starts_at": now.isoformat(),
        "ends_at": (now + timedelta(hours=8)).isoformat(),
        "lab_ids": ["m00-lab-leave-letter", "m05-lab-fest-schedule"], "grants_pro_days": 30,
    })).json()
    assert event["join_code"].startswith("H")

    p = await _signin(client, "hacker@ecosys.test")
    joined = (await client.post("/me/join", headers=p, json={"code": event["join_code"]})).json()
    assert joined["joined"] == "event"
    me = (await client.get("/me", headers=p)).json()
    assert me["has_pro"] is True  # event grants pro access

    attempt = (await client.post(f"/labs/m00-lab-leave-letter/attempt?event_id={event['id']}", headers=p)).json()
    v1 = (await client.post(f"/attempts/{attempt['id']}/prompts", headers=p,
                            json={"text": "Write a leave letter."})).json()
    run = (await client.post(f"/prompts/{v1['id']}/runs", headers=p)).json()
    await run_now(redis, run["id"])

    # judges are scoped to the event
    await _signin(client, "judge@ecosys.test")
    await client.post("/role-assignments", headers=ADMIN, json={
        "email": "judge@ecosys.test", "role": "judge", "scope_type": "event", "scope_id": event["id"]})
    judge = auth("judge@ecosys.test")
    trails = (await client.get(f"/events/{event['id']}/trails", headers=judge)).json()
    assert trails and trails[0]["attempts"][0]["trail"][0]["version"] == 1
    assert (await client.get(f"/events/{event['id']}/trails", headers=p)).status_code == 403

    uid = trails[0]["user_id"]
    assert (await client.put(f"/events/{event['id']}/judge-scores/{uid}", headers=judge,
                             json={"craft": 8, "reasoning": 7})).status_code == 200
    board = (await client.get(f"/events/{event['id']}/leaderboard", headers=p)).json()["board"]
    assert board[0]["judge_score"] == 15 and board[0]["is_me"]

    outsider = await _signin(client, "outsider@ecosys.test")
    assert (await client.get(f"/events/{event['id']}/leaderboard", headers=outsider)).status_code == 403
    csv = await client.get(f"/events/{event['id']}/export.csv", headers=ADMIN)
    assert csv.status_code == 200 and csv.text.startswith("rank,")


async def test_admin_usage_dashboard(client):
    usage = (await client.get("/admin/usage", headers=ADMIN)).json()
    assert usage["credit_pool_usd"] == 50000
    assert "daily" in usage
