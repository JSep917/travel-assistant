import asyncio
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient
from config import settings

logger = logging.getLogger(__name__)

# 缓存
_tuniu_cache: dict | None = None

async def get_tuniu_tools() -> dict:
    """获取 途牛 MCP 服务提供的工具"""
    global _tuniu_cache
    if _tuniu_cache is None:
        client = MultiServerMCPClient({
            "tuniu-ticket": { # 票价
                "transport": "streamable_http",
                "url": "https://openapi.tuniu.cn/mcp/ticket", # 途牛票价查询
                "headers": {
                    "apiKey": settings.TUNIU_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
            },
            "tuniu-hotel": { # 酒店
                "transport": "streamable_http",
                "url": "https://openapi.tuniu.cn/mcp/hotel",
                "headers": {
                    "apiKey": settings.TUNIU_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream"
                }
            },
        })
        tools = await client.get_tools()
        _tuniu_cache = {t.name: t for t in tools}
    return _tuniu_cache

async def main():
    tools = await get_tuniu_tools()
    tool = tools["query_cheapest_tickets"]
    resp = await tool.ainvoke({
        "scenic_name": "上海四行仓库抗战纪念馆"
    })

    import json
    _data = json.loads(resp[0]['text'])

    cleaned_ticket_price = []
    for d in _data['tickets']:
        if d and d['personTypeName'] == "成人票":
            cleaned_ticket_price.append({
                "ticket_price": float(d["startPrice"]),
            })
    logger.debug("ticket prices=%s", cleaned_ticket_price)
    logger.debug(
        "sorted ticket prices=%s",
        sorted(
            cleaned_ticket_price,
            key=lambda item: item["ticket_price"],
        ),
    )

if __name__ == "__main__":
    asyncio.run(get_tuniu_tools())