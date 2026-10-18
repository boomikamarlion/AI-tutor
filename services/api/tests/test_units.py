from pathlib import Path

from app.auth.rbac import Perm, build_principal
from app.content.loader import load_content
from app.engine.features import length_limit, prompt_features
from app.engine.gamification import level_for
from app.engine.render import render_prompt
from app.gateway.router import price, role_config
from app.models import RoleAssignment, User

REPO = Path(__file__).resolve().parents[3]


def test_content_tree_is_valid():
    bundle = load_content(REPO / "content")
    assert len(bundle.modules) == 12
    assert all(len(m.labs) >= 2 for m in bundle.modules)
    for lab in bundle.labs.values():
        assert 3 <= len(lab.test_cases) <= 4, lab.id


def test_render_prompt_placeholder_and_fallback():
    assert render_prompt("Tag: {{input}}", " hi ") == "Tag: hi"
    assert render_prompt("Tag this", "hi").endswith("<input>\nhi\n</input>")


def test_features_and_limits():
    weak = prompt_features("summarise")
    strong = prompt_features(
        "You are an editor. Summarise the review below for college students in at most 3 bullets. "
        "Use only the text; say 'not stated' if missing.\n<review>{{input}}</review>"
    )
    assert strong["score"] > weak["score"]
    assert length_limit("in at most 3 bullets") == (3, "bullet")


def test_routing_and_pricing():
    assert role_config("run").deployment == "gpt-6-luna"
    assert role_config("critique").deployment == "gpt-6.1-sol"
    assert price("gpt-6.1-sol").cost(1_000_000, 1_000_000) == 12.0


def test_rbac_scopes():
    import uuid

    org, other = uuid.uuid4(), uuid.uuid4()
    u = User(id=uuid.uuid4(), external_id="x")
    u.roles = [RoleAssignment(role="org_admin", scope_type="org", scope_id=org)]
    p = build_principal(u)
    assert p.can(Perm.EVENT_MANAGE, [("org", org)])
    assert not p.can(Perm.EVENT_MANAGE, [("org", other)])
    assert not p.can(Perm.USAGE_VIEW)
    admin = build_principal(User(id=uuid.uuid4(), external_id="y", roles=[]), token_roles=["admin"])
    assert admin.can(Perm.USAGE_VIEW)


def test_levels():
    assert level_for(0) == 1 and level_for(50) == 2 and level_for(200) == 3
