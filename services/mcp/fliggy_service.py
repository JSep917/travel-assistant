from langchain_mcp_adapters.client import MultiServerMCPClient
from config import settings  # 假设你的配置文件中已定义 FLYAI_API_KEY
import asyncio

# 缓存复用，避免重复加载
_fliggy_cache: dict | None = None

async def get_fliggy_tools() -> dict:
    """获取飞猪 MCP Server 提供的工具"""
    global _fliggy_cache
    if _fliggy_cache is None:
        client = MultiServerMCPClient({
            "fliggy": {
                "command": "uvx",
                "args": [
                    "--from",
                    "mcp-fliggy-travel==0.5.1",
                    "mcp-fliggy-travel"
                ],
                "transport": "stdio",
                "env": {
                    "FLYAI_API_KEY": settings.FLYAI_API_KEY,
                }
            }
        })
        tool = await client.get_tools()
        _fliggy_cache = {t.name: t for t in tool}
    return _fliggy_cache
