import logging
import sys
from pathlib import Path

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from mcp_tools_rag.common.logging_config import setup_logging
from mcp_tools_rag.graph.graph import build_graph
from services.ingestion.conversation_memory_service import (
    ConversationMemoryService,
)
from services.retrieval.conversation_store import (
    get_conversation_store,
)
import psycopg
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

logger = logging.getLogger(__name__)


async def main():
    """回填会话长期记忆。"""
    store = get_conversation_store()

    try:
        store.ensure_collection()
        service = ConversationMemoryService(store)

        async with AsyncPostgresSaver.from_conn_string(
            settings.POSTGRE_URI
        ) as checkpointer:
            graph = await build_graph(checkpointer=checkpointer)

            async with await psycopg.AsyncConnection.connect(
                settings.POSTGRE_URI
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "select distinct thread_id from checkpoints"
                    )
                    thread_ids = [
                        row[0] for row in await cur.fetchall()
                    ]

            total = 0

            for thread_id in thread_ids:
                config = {
                    "configurable": {
                        "thread_id": thread_id,
                    }
                }

                state = await graph.aget_state(config)
                messages = state.values.get("messages", [])

                if not messages:
                    continue

                user_id = thread_id.split(":", 1)[0]

                turns = service.split_turns(messages)

                count = await service.add_turns(
                    thread_id=thread_id,
                    user_id=user_id,
                    turns=turns,
                    tenant_id="",
                )
                total += count

                logger.info(
                    "memory backfill thread=%s count=%s",
                    thread_id,
                    count,
                )

            logger.info("memory backfill completed total=%s", total)

    finally:
        store.close()
        get_conversation_store.cache_clear()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
