from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Annotated

from arq import ArqRedis
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.rbac import Perm, Principal, Scope, build_principal
from app.auth.tokens import TokenError, verify_token
from app.config import get_settings
from app.db import get_session
from app.models import RoleAssignment, User

Session = Annotated[AsyncSession, Depends(get_session)]


async def current_principal(
    session: Session, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    try:
        identity = verify_token(authorization.split(" ", 1)[1])
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    user = (await session.execute(
        select(User).options(selectinload(User.roles)).where(User.external_id == identity.external_id)
    )).scalar_one_or_none()
    if user is None:
        user = User(external_id=identity.external_id, email=identity.email, display_name=identity.name,
                    interests=[])
        session.add(user)
        await session.flush()
        bootstrap = {e.strip().lower() for e in get_settings().bootstrap_admins.split(",") if e.strip()}
        if identity.email and identity.email.lower() in bootstrap:
            session.add(RoleAssignment(user_id=user.id, role="admin", scope_type="platform"))
        await session.commit()
        user = (await session.execute(
            select(User).options(selectinload(User.roles)).where(User.id == user.id)
        )).scalar_one()
    user.last_seen_at = datetime.now(UTC)
    if identity.email and not user.email:
        user.email = identity.email
    await session.commit()
    return build_principal(user, identity.token_roles)


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require(principal: Principal, perm: Perm, scopes: Iterable[Scope] = ()) -> None:
    if not principal.can(perm, scopes):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {perm.value}")


def require_platform(perm: Perm):
    async def dep(principal: CurrentPrincipal) -> Principal:
        require(principal, perm)
        return principal

    return Depends(dep)


def get_arq(request: Request) -> ArqRedis:
    return request.app.state.arq


Arq = Annotated[ArqRedis, Depends(get_arq)]
