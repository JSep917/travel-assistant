import asyncio
import json
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient
from config import settings

logger = logging.getLogger(__name__)

# 重复执行，结果一样
_amap_cache: dict | None = None
# 防止并发执行
_amap_lock = asyncio.Lock()

async def get_amap_tools() -> dict:
    """获取高德 MCP 服务提供的工具。"""
    global _amap_cache
    if _amap_cache is not None:
        return _amap_cache

    async with _amap_lock:
        # 双重检查
        if _amap_cache is not None:
            return _amap_cache

        try:
            client = MultiServerMCPClient({
                "amap_maps": {
                    "command": "npx",
                    "args": ["-y", "@amap/amap-maps-mcp-server"],
                    "transport": "stdio",
                    "env": {
                        "AMAP_MAPS_API_KEY": settings.AMAP_API_KEY,
                    },
                }
            })

            tools = await client.get_tools()
            _amap_cache = {tool.name: tool for tool in tools}

        except Exception:
            _amap_cache = None
            raise
    return _amap_cache

async def main1():
    tools = await get_amap_tools()
    tool = tools["maps_geo"]

    result = await tool.ainvoke({
        "address": "南锣鼓巷",
        "city": "北京",
    })

    logger.debug("result type=%s", type(result))
    logger.debug("result=%s", json.loads(result[0]["text"]))
    logger.debug("text type=%s", type(result[0]["text"]))


async def main2():
    tools = await get_amap_tools()
    tool = tools["maps_search_detail"]
    resp = await tool.ainvoke({
        "id": "B0LK9ZA8KY"
    })
    from mcp_tools_rag.common.tool_result_clean import clean_tool_result
    logger.debug(
        "clean result=%s",
        clean_tool_result(
            tool_name="maps_search_detail",
            result=resp,
        ),
    )


if __name__ == "__main__":
    asyncio.run(main2())