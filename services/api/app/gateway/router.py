"""Role → deployment routing, read from config/models.yaml."""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

from app.config import get_settings


@dataclass(frozen=True)
class RoleConfig:
    role: str
    deployment: str
    fallback: str | None
    reasoning_effort: str | None
    max_output_tokens: int
    seed: int | None

    def settings(self) -> dict[str, Any]:
        """The pinned settings recorded on every run for reproducibility."""
        return {
            "deployment": self.deployment,
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class Price:
    input_per_m: float
    output_per_m: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_m + output_tokens * self.output_per_m) / 1_000_000


@lru_cache
def _config() -> dict[str, Any]:
    with open(get_settings().models_config, encoding="utf-8") as f:
        return yaml.safe_load(f)


def role_config(role: str) -> RoleConfig:
    raw = _config()["roles"][role]
    deployment = os.environ.get(f"MODEL_{role.upper()}_DEPLOYMENT", raw["deployment"])
    return RoleConfig(
        role=role,
        deployment=deployment,
        fallback=raw.get("fallback"),
        reasoning_effort=raw.get("reasoning_effort"),
        max_output_tokens=int(raw.get("max_output_tokens", 1000)),
        seed=raw.get("seed"),
    )


def price(deployment: str) -> Price:
    raw = _config()["deployments"].get(deployment)
    if raw is None:  # unknown deployment: assume the most expensive tier so budgets stay safe
        raw = max(_config()["deployments"].values(), key=lambda d: d["output_per_m"])
    return Price(float(raw["input_per_m"]), float(raw["output_per_m"]))


def budget(tier: str) -> tuple[float, float]:
    raw = _config()["budgets"][tier]
    return float(raw["soft_usd"]), float(raw["hard_usd"])


def credit_pool_usd() -> float:
    return float(_config()["budgets"]["credit_pool_usd"])
