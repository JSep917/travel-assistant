import asyncio
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# 缓存 复用代码只加载一次
_12306_cache: dict | None = None

async def get_12306_tools() -> dict:
    """获取12306 MCP Server提供的工具"""
    global _12306_cache
    if _12306_cache is None:
        client = MultiServerMCPClient({
            "12306": {
                "command": "uvx",
                "args": ["mcp-server-12306"],
                "transport": "stdio",
            }
        })
        tool = await client.get_tools()
        _12306_cache = {t.name: t for t in tool}
    return _12306_cache

async def main():
    tools = await get_12306_tools()
    tool = tools['query-ticket-price']
    resp = await tool.ainvoke({
        "from_station": "湘潭",
        "to_station": "上海",
        "train_date": "2026-10-02"
    })
    logger.debug("ticket response=%s", resp)


if __name__ == "__main__":
    asyncio.run(main())

