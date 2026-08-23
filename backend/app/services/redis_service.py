import json
import logging
from typing import Any, AsyncIterator, Optional, Tuple

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis = Redis.from_url(redis_url, decode_responses=True)

    def task_key(self, task_id: str) -> str:
        return f"task:{task_id}"

    def module_queue_key(self, module_name: str) -> str:
        return f"module:{module_name}:queue"

    def chain_key(self, chain_task_id: str) -> str:
        return f"chain:{chain_task_id}"

    def result_key(self, module_name: str, file_hash: str) -> str:
        return f"result:{module_name}:{file_hash}"

    def chain_completed_channel(self, chain_task_id: str) -> str:
        return f"chain:module:completed:{chain_task_id}"

    def chain_module_lock_key(self, chain_task_id: str, module_index: int) -> str:
        return f"lock:chain:{chain_task_id}:module:{module_index}"

    CHAIN_COMPLETED_PATTERN = "chain:module:completed:*"
    RESULT_PATTERN = "result:*:*"
    TASK_PATTERN = "task:*"
    CHAIN_PATTERN = "chain:*"

    def parse_result_key(self, result_key: str) -> Optional[Tuple[str, str]]:
        parts = result_key.split(":")
        if len(parts) < 3:
            return None
        return parts[1], parts[2]

    def chain_task_id_from_key(self, chain_key: str) -> str:
        return chain_key.split(":")[-1]

    async def get_json(self, key: str) -> Optional[dict]:
        raw = await self.redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.error("Corrupted JSON payload at key %s", key)
            return None

    async def set_json(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        await self.redis.set(key, json.dumps(data), ex=ttl)

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return await self.redis.delete(*keys)

    async def scan_iter(self, match: str) -> AsyncIterator[str]:
        async for key in self.redis.scan_iter(match=match):
            yield key

    async def delete_matching(self, pattern: str) -> int:
        deleted = 0
        async for key in self.redis.scan_iter(match=pattern):
            deleted += await self.redis.delete(key)
        return deleted

    async def acquire_lock(self, key: str, ttl: int = 3600) -> bool:

        return bool(await self.redis.set(key, "locked", nx=True, ex=ttl))

    async def acquire_chain_module_lock(
        self, chain_task_id: str, module_index: int, ttl: int = 3600
    ) -> bool:
        return await self.acquire_lock(
            self.chain_module_lock_key(chain_task_id, module_index), ttl=ttl
        )

    async def set_task(self, task_id: str, data: dict, ttl: int = 3600) -> None:
        await self.set_json(self.task_key(task_id), data, ttl=ttl)

    async def get_task(self, task_id: str) -> Optional[dict]:
        return await self.get_json(self.task_key(task_id))

    async def enqueue_task(self, module_name: str, task_id: str) -> None:
        await self.redis.rpush(self.module_queue_key(module_name), task_id)

    async def delete_task(self, task_id: str) -> None:
        await self.redis.delete(self.task_key(task_id))

    async def delete_tasks_for(
        self,
        file_hash: str,
        module_name: Optional[str] = None,
        case_insensitive: bool = False,
    ) -> int:
        deleted = 0
        async for task_key in self.redis.scan_iter(match=self.TASK_PATTERN):
            task_data = await self.get_json(task_key)
            if not task_data:
                continue

            if task_data.get("file_hash") != file_hash:
                continue

            if module_name is not None:
                candidate = task_data.get("module_name", "") or ""
                if case_insensitive:
                    if candidate.lower() != module_name.lower():
                        continue
                elif candidate != module_name:
                    continue

            deleted += await self.redis.delete(task_key)
        return deleted

    async def get_result(self, module_name: str, file_hash: str) -> Optional[dict]:
        return await self.get_json(self.result_key(module_name, file_hash))

    async def delete_result(self, module_name: str, file_hash: str) -> None:
        await self.redis.delete(self.result_key(module_name, file_hash))

    async def iter_result_keys(self) -> AsyncIterator[str]:
        async for key in self.redis.scan_iter(match=self.RESULT_PATTERN, count=100):
            yield key

    async def set_chain_state(
        self, chain_task_id: str, data: dict, ttl: int = 86400
    ) -> None:
        await self.set_json(self.chain_key(chain_task_id), data, ttl=ttl)

    async def get_chain_state(self, chain_task_id: str) -> Optional[dict]:
        return await self.get_json(self.chain_key(chain_task_id))

    async def iter_chain_states(self) -> AsyncIterator[Tuple[str, dict]]:
        async for chain_key in self.redis.scan_iter(match=self.CHAIN_PATTERN):
            if chain_key.startswith("chain:module:completed:"):
                continue
            chain_state = await self.get_json(chain_key)
            if chain_state is None:
                continue
            yield self.chain_task_id_from_key(chain_key), chain_state

    async def delete_chain_completed_key(self, chain_task_id: str) -> None:
        await self.redis.delete(self.chain_completed_channel(chain_task_id))

    async def delete_chain_keys(self, chain_task_id: str) -> int:
        return await self.delete_matching(f"*{chain_task_id}*")

    async def publish_chain_event(self, chain_task_id: str, payload: dict) -> None:
        await self.redis.publish(
            self.chain_completed_channel(chain_task_id), json.dumps(payload)
        )

    async def listen_chain_events(self) -> AsyncIterator[dict]:

        pubsub = self.redis.pubsub()
        await pubsub.psubscribe(self.CHAIN_COMPLETED_PATTERN)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    logger.error(
                        "Invalid JSON in chain event payload: %r", message.get("data")
                    )
        finally:
            try:
                await pubsub.punsubscribe(self.CHAIN_COMPLETED_PATTERN)
            except Exception as exc:
                logger.debug("Error unsubscribing from chain events: %s", exc)
            try:
                await pubsub.aclose()
            except Exception as exc:
                logger.debug("Error closing chain event pubsub: %s", exc)

    async def listen_result_keys(self) -> AsyncIterator[str]:
        channel_pattern = "__keyevent@*__:set"
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe(channel_pattern)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                key = message.get("data")
                if isinstance(key, str) and key.startswith("result:"):
                    yield key
        finally:
            try:
                await pubsub.punsubscribe(channel_pattern)
            except Exception as exc:
                logger.debug("Error unsubscribing from result keyevents: %s", exc)
            try:
                await pubsub.aclose()
            except Exception as exc:
                logger.debug("Error closing result keyevent pubsub: %s", exc)

    async def close(self) -> None:
        await self.redis.aclose()
