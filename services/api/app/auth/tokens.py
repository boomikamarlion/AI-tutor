"""Bearer-token verification.

Production: Microsoft Entra External ID issues access tokens for our API app registration
(audience = ENTRA_API_CLIENT_ID). Platform roles (admin, author) come from Entra app roles in
the `roles` claim. Scoped roles (mentor, judge, org_admin) live in our database.

Development: the web app's dev login mints HS256 tokens with the same claim names.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.config import Settings, get_settings


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class Identity:
    external_id: str
    email: str | None
    name: str
    token_roles: frozenset[str] = field(default_factory=frozenset)


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def _verify_entra(token: str, settings: Settings) -> Identity:
    if not (settings.entra_tenant_id and settings.entra_api_client_id):
        raise TokenError("Entra auth is not configured")
    try:
        key = _jwks_client(settings.entra_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=[settings.entra_api_client_id, f"api://{settings.entra_api_client_id}"],
            issuer=settings.entra_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    oid = claims.get("oid") or claims["sub"]
    email = claims.get("email") or claims.get("preferred_username")
    if not email and isinstance(claims.get("emails"), list) and claims["emails"]:
        email = claims["emails"][0]
    return Identity(
        external_id=f"{claims.get('tid', settings.entra_tenant_id)}:{oid}",
        email=email,
        name=claims.get("name") or (email.split("@")[0] if email else "Learner"),
        token_roles=frozenset(claims.get("roles", [])),
    )


def mint_dev_token(email: str, name: str, roles: list[str] | None = None, secret: str | None = None) -> str:
    """Used by tests and the local seed script. The web app mints the same shape."""
    import time

    now = int(time.time())
    payload = {"sub": email, "email": email, "name": name, "roles": roles or [], "iat": now, "exp": now + 86400}
    return jwt.encode(payload, secret or get_settings().dev_jwt_secret, algorithm="HS256")


def _verify_dev(token: str, settings: Settings) -> Identity:
    try:
        claims = jwt.decode(token, settings.dev_jwt_secret, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    return Identity(
        external_id=f"dev:{claims['sub']}",
        email=claims.get("email"),
        name=claims.get("name") or claims["sub"],
        token_roles=frozenset(claims.get("roles", [])),
    )


def verify_token(token: str, settings: Settings | None = None) -> Identity:
    settings = settings or get_settings()
    if settings.auth_mode == "entra":
        return _verify_entra(token, settings)
    if settings.env == "prod":
        raise TokenError("dev auth is disabled in prod")
    return _verify_dev(token, settings)
