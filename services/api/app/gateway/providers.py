"""Model providers.

`FoundryProvider` calls Azure AI Foundry deployments through Microsoft Agent Framework
(`FoundryChatClient`, Responses API) with Entra ID auth — no API keys.
`FakeProvider` is deterministic and offline; it powers local dev, tests and demos.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from app.config import get_settings
from app.gateway.router import RoleConfig

T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StreamResult:
    """Async-iterate for text chunks; `usage` is filled when iteration ends.

    `source` (the raw test-case input) is only used by the fake provider."""

    chunks: AsyncIterator[str]
    usage: Usage = field(default_factory=Usage)


class ModelProvider(Protocol):
    def stream_text(
        self, cfg: RoleConfig, prompt: str, *, instructions: str | None = None, source: str | None = None
    ) -> StreamResult: ...

    async def complete_json(
        self, cfg: RoleConfig, prompt: str, schema: type[T], *, instructions: str | None = None
    ) -> tuple[T, Usage]: ...


# ---------------------------------------------------------------- Azure AI Foundry


class FoundryProvider:
    def __init__(self) -> None:
        from azure.identity.aio import DefaultAzureCredential

        settings = get_settings()
        if not settings.foundry_project_endpoint:
            raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is required when MODEL_PROVIDER=foundry")
        self._endpoint = settings.foundry_project_endpoint
        self._credential = DefaultAzureCredential(managed_identity_client_id=settings.azure_client_id)
        self._clients: dict[str, Any] = {}

    def _client(self, deployment: str):
        from agent_framework.foundry import FoundryChatClient

        if deployment not in self._clients:
            self._clients[deployment] = FoundryChatClient(
                project_endpoint=self._endpoint, model=deployment, credential=self._credential
            )
        return self._clients[deployment]

    @staticmethod
    def _options(cfg: RoleConfig, instructions: str | None) -> dict[str, Any]:
        opts: dict[str, Any] = {"max_tokens": cfg.max_output_tokens, "store": False}
        if cfg.reasoning_effort:
            opts["reasoning"] = {"effort": cfg.reasoning_effort}
        if cfg.seed is not None:
            opts["seed"] = cfg.seed
        if instructions:
            opts["instructions"] = instructions
        return opts

    @staticmethod
    def _usage(details: Any) -> Usage:
        details = details or {}
        return Usage(
            input_tokens=int(details.get("input_token_count") or 0),
            output_tokens=int(details.get("output_token_count") or 0),
        )

    def stream_text(
        self, cfg: RoleConfig, prompt: str, *, instructions: str | None = None, source: str | None = None
    ) -> StreamResult:
        from agent_framework import Message

        result = StreamResult(chunks=None)  # type: ignore[arg-type]

        async def gen() -> AsyncIterator[str]:
            stream = self._client(cfg.deployment).get_response(
                [Message("user", [prompt])], stream=True, options=self._options(cfg, instructions)
            )
            async for update in stream:
                if update.text:
                    yield update.text
            final = await stream.get_final_response()
            result.usage = self._usage(final.usage_details)

        result.chunks = gen()
        return result

    async def complete_json(
        self, cfg: RoleConfig, prompt: str, schema: type[T], *, instructions: str | None = None
    ) -> tuple[T, Usage]:
        from agent_framework import Message

        opts = self._options(cfg, instructions)
        opts["response_format"] = schema
        response = await self._client(cfg.deployment).get_response([Message("user", [prompt])], options=opts)
        value = response.value if isinstance(response.value, schema) else schema.model_validate_json(response.text)
        return value, self._usage(response.usage_details)


# ---------------------------------------------------------------- offline fake


class FakeProvider:
    """Deterministic stand-in. Output quality tracks the prompt's structure, so a better
    prompt really does produce a better (fake) output and score — enough to exercise the loop."""

    # Registered by app.engine.critic so the fake critic can grade without a model.
    json_handlers: dict[type, Callable[[str], BaseModel]] = {}

    def __init__(self, delay: float = 0.01) -> None:
        self.delay = delay

    def stream_text(
        self, cfg: RoleConfig, prompt: str, *, instructions: str | None = None, source: str | None = None
    ) -> StreamResult:
        from app.engine.fake_output import fake_output

        text = fake_output(prompt, source)
        result = StreamResult(chunks=None)  # type: ignore[arg-type]

        async def gen() -> AsyncIterator[str]:
            words = text.split(" ")
            for i in range(0, len(words), 4):
                await asyncio.sleep(self.delay)
                yield " ".join(words[i : i + 4]) + (" " if i + 4 < len(words) else "")
            result.usage = Usage(input_tokens=len(prompt) // 4, output_tokens=len(text) // 4)

        result.chunks = gen()
        return result

    async def complete_json(
        self, cfg: RoleConfig, prompt: str, schema: type[T], *, instructions: str | None = None
    ) -> tuple[T, Usage]:
        handler = self.json_handlers.get(schema)
        if handler is None:
            raise NotImplementedError(f"FakeProvider has no handler for {schema.__name__}")
        await asyncio.sleep(self.delay)
        value = handler(prompt)
        return value, Usage(input_tokens=len(prompt) // 4, output_tokens=len(value.model_dump_json()) // 4)  # type: ignore[return-value]


_provider: ModelProvider | None = None


def get_provider() -> ModelProvider:
    global _provider
    if _provider is None:
        _provider = FoundryProvider() if get_settings().model_provider == "foundry" else FakeProvider()
    return _provider


def set_provider(provider: ModelProvider | None) -> None:
    global _provider
    _provider = provider
