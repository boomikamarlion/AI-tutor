"""Live run state over Redis.

The worker appends streamed text to per-case keys and publishes events on `run:<id>`.
The SSE endpoint subscribes first, then sends a snapshot from the keys, then forwards events.
Delta events carry the offset they start at, so a client that got the snapshot can apply
any overlapping delta idempotently: text = text[:offset] + delta.
"""

import json
import uuid
from typing import Any

from redis.asyncio import Redis

TTL_SECONDS = 3600


def channel_name(run_id: uuid.UUID | str) -> str:
    return f"run:{run_id}"


def _case_key(run_id, case_id: str) -> str:
    return f"run:{run_id}:case:{case_id}"


def _state_key(run_id) -> str:
    return f"run:{run_id}:state"


class RunChannel:
    def __init__(self, redis: Redis, run_id: uuid.UUID):
        self.redis = redis
        self.run_id = run_id
        self.name = channel_name(run_id)

    async def _publish(self, event: dict[str, Any]) -> None:
        await self.redis.publish(self.name, json.dumps(event, default=str))

    async def status(self, status: str, **extra: Any) -> None:
        await self.redis.hset(_state_key(self.run_id), mapping={"status": status})
        await self.redis.expire(_state_key(self.run_id), TTL_SECONDS)
        await self._publish({"type": "status", "status": status, **extra})

    async def append(self, case_id: str, text: str) -> None:
        key = _case_key(self.run_id, case_id)
        new_len = await self.redis.append(key, text)
        await self.redis.expire(key, TTL_SECONDS)
        await self._publish({"type": "delta", "case_id": case_id, "offset": new_len - len(text), "text": text})

    async def case_done(self, case_id: str, **meta: Any) -> None:
        await self.redis.hset(_state_key(self.run_id), mapping={f"case:{case_id}": json.dumps(meta)})
        await self._publish({"type": "case_done", "case_id": case_id, **meta})

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        await self._publish({"type": event_type, **payload})


async def snapshot(redis: Redis, run_id: uuid.UUID, case_ids: list[str]) -> dict[str, Any]:
    state = await redis.hgetall(_state_key(run_id))
    texts = {}
    for cid in case_ids:
        raw = await redis.get(_case_key(run_id, cid))
        texts[cid] = raw.decode() if isinstance(raw, bytes) else (raw or "")
    decoded = {(k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
               for k, v in state.items()}
    return {
        "status": decoded.get("status"),
        "cases": {
            cid: {"text": texts[cid], **json.loads(decoded.get(f"case:{cid}", "{}"))} for cid in case_ids
        },
    }
