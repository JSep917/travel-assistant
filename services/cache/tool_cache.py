import hashlib
import json
import logging

import redis.asyncio as redis
from functools import cache

from config import settings

logger = logging.getLogger(__name__)


class ToolCache:
    def __init__(self, client):
        self.client = client

    @staticmethod
    def make_key(
        server_name: str,
        tool_name: str,
        args: dict,
        user_id: str = "",
    ) -> str:
        """生成key"""
        raw = json.dumps(
            args,
            ensure_ascii=False,
            sort_keys=True,
        )
        # 同输入同key - 确定性哈希
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        user_id = user_id or "public"
        return f"tool_cache:{server_name}:{tool_name}:{user_id}:{digest}"

    async def get(self, key: str) -> str | None:
        try:
            return await self.client.get(key)
        except Exception:
            logger.warning("tool cache get failed", exc_info=True)
            return None

    async def set(
        self,
        key: str,
        content: str,
        ttl: int = 600,
    ) -> None:
        """写入缓存按key区分"""
        try:
            await self.client.set(key, content, ex=ttl)
        except Exception:
            logger.warning("tool cache set failed", exc_info=True)

    async def close(self) -> None:
        await self.client.aclose()



@cache
def get_tool_cache() -> ToolCache:
    """全程复用一个 cache"""
    client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
    )
    return ToolCache(client)

async def close_tool_cache() -> None:
    """关闭缓存连接并清楚工厂缓存"""
    if get_tool_cache.cache_info().currsize:
        cache_obj = get_tool_cache()
        await cache_obj.close()

    get_tool_cache.cache_clear()