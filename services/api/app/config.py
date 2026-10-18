from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://ecosys:ecosys@localhost:5432/ecosys"
    # When set, Postgres auth uses an Entra token for this managed identity instead of a password.
    database_entra_user: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    content_dir: Path = REPO_ROOT / "content"
    models_config: Path = REPO_ROOT / "config" / "models.yaml"

    # "fake" runs everything locally with a deterministic provider; "foundry" calls Azure AI Foundry.
    model_provider: Literal["fake", "foundry"] = "fake"
    foundry_project_endpoint: str | None = None
    # Client id of the user-assigned managed identity in Azure; empty locally (uses az login).
    azure_client_id: str | None = None

    # Auth. "dev" accepts HS256 tokens minted by the web app's dev login; "entra" validates
    # Microsoft Entra External ID access tokens.
    auth_mode: Literal["dev", "entra"] = "dev"
    dev_jwt_secret: str = "dev-only-secret-change-me-dev-only-secret"
    entra_tenant_id: str | None = None
    entra_tenant_subdomain: str | None = None  # <subdomain>.ciamlogin.com
    entra_api_client_id: str | None = None  # audience of access tokens

    # Comma separated emails that always get the platform admin role (bootstrap).
    bootstrap_admins: str = ""

    cors_origins: str = "http://localhost:3000"
    applicationinsights_connection_string: str | None = None

    @property
    def entra_issuer(self) -> str:
        return f"https://{self.entra_tenant_id}.ciamlogin.com/{self.entra_tenant_id}/v2.0"

    @property
    def entra_jwks_url(self) -> str:
        sub = self.entra_tenant_subdomain or self.entra_tenant_id
        return f"https://{sub}.ciamlogin.com/{self.entra_tenant_id}/discovery/v2.0/keys"


@lru_cache
def get_settings() -> Settings:
    return Settings()
