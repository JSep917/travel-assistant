import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_tools_rag.common.logging_config import setup_logging
from services.ingestion.tool_sync_service import ToolSyncService
from services.retrieval.tool_store import (
    close_tool_store,
    get_tool_store,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """连接 Milvus，建立工具 collection 并回填。"""
    store = get_tool_store()

    try:
        store.ensure_collection()
        logger.info("collection connected name=%s", store.collection_name)

        service = ToolSyncService(store)
        count = await service.sync_amap(flush=True)

        logger.info("tool sync completed count=%s", count)

        stats = store.client.get_collection_stats(
            store.collection_name
        )
        logger.info("collection stats=%s", stats)

    finally:
        close_tool_store()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
