"""Role-based access control.

Roles
-----
Platform (scope_type="platform", or Entra app role in the token):
  admin   — everything
  author  — read hidden content (reference prompts), reload content, preview all modules
Scoped (stored in role_assignments):
  learner   @ cohort|event — member; implied for every signed-in user on their own data
  mentor    @ cohort       — view progress of consenting learners in the cohort
  judge     @ event        — view trails and score participants of an event
  org_admin @ org          — manage the org's cohorts and events, assign mentor/judge in the org

Permissions are checked against a scope chain, e.g. a cohort belongs to an org, so an
org_admin of that org may view the cohort.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.models import User

PLATFORM_ROLES = {"admin", "author"}
SCOPED_ROLES = {"learner", "mentor", "judge", "org_admin"}
ALL_ROLES = PLATFORM_ROLES | SCOPED_ROLES


class Perm(StrEnum):
    CONTENT_PREVIEW = "content.preview"  # see pro modules + hidden fields without a plan
    CONTENT_RELOAD = "content.reload"
    COHORT_VIEW = "cohort.view"
    COHORT_MANAGE = "cohort.manage"
    EVENT_JUDGE = "event.judge"
    EVENT_MANAGE = "event.manage"
    ORG_MANAGE = "org.manage"
    ROLES_ASSIGN = "roles.assign"
    USAGE_VIEW = "usage.view"
    USERS_VIEW = "users.view"


# Which roles grant which permissions, and at which scope type.
PLATFORM_GRANTS: dict[str, set[Perm]] = {
    "admin": set(Perm),
    "author": {Perm.CONTENT_PREVIEW, Perm.CONTENT_RELOAD},
}
SCOPED_GRANTS: dict[str, set[Perm]] = {
    "mentor": {Perm.COHORT_VIEW},
    "judge": {Perm.EVENT_JUDGE},
    "org_admin": {
        Perm.ORG_MANAGE,
        Perm.COHORT_VIEW,
        Perm.COHORT_MANAGE,
        Perm.EVENT_MANAGE,
        Perm.EVENT_JUDGE,
        Perm.ROLES_ASSIGN,
    },
    "learner": set(),
}
# Roles an org_admin may hand out inside their org (admins may hand out anything).
ORG_ASSIGNABLE = {"mentor", "judge", "learner", "org_admin"}

Scope = tuple[str, uuid.UUID | None]


@dataclass
class Principal:
    user: User
    platform_roles: set[str]
    scoped: set[tuple[str, str, uuid.UUID]]  # (role, scope_type, scope_id)

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def is_admin(self) -> bool:
        return "admin" in self.platform_roles

    @property
    def is_staff(self) -> bool:
        return bool(self.platform_roles & PLATFORM_ROLES)

    def can(self, perm: Perm, scopes: Iterable[Scope] = ()) -> bool:
        if any(perm in PLATFORM_GRANTS.get(r, set()) for r in self.platform_roles):
            return True
        wanted = {(t, i) for t, i in scopes if i is not None}
        for role, scope_type, scope_id in self.scoped:
            if (scope_type, scope_id) in wanted and perm in SCOPED_GRANTS.get(role, set()):
                return True
        return False

    def scope_ids(self, role: str, scope_type: str) -> set[uuid.UUID]:
        return {sid for r, t, sid in self.scoped if r == role and t == scope_type}

    def roles_summary(self) -> dict:
        return {
            "platform": sorted(self.platform_roles),
            "scoped": [{"role": r, "scope_type": t, "scope_id": str(i)} for r, t, i in sorted(
                self.scoped, key=lambda x: (x[0], x[1], str(x[2]))
            )],
        }


def build_principal(user: User, token_roles: Iterable[str] = ()) -> Principal:
    platform = {r for r in token_roles if r in PLATFORM_ROLES}
    scoped: set[tuple[str, str, uuid.UUID]] = set()
    for ra in user.roles:
        if ra.scope_type == "platform":
            if ra.role in PLATFORM_ROLES:
                platform.add(ra.role)
        elif ra.scope_id is not None:
            scoped.add((ra.role, ra.scope_type, ra.scope_id))
    return Principal(user=user, platform_roles=platform, scoped=scoped)
