import asyncio
import logging
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from config import settings
from mcp_tools_rag.common.logging_config import setup_logging
from mcp_tools_rag.graph.graph import build_graph
from services.cache.tool_cache import close_tool_cache
from services.chat.chat_service import ChatService
from services.database.repositories import (
    CheckpointManager,
    ThreadRepository,
    UserProfileRepository,
)
from services.ingestion.conversation_memory_service import (
    ConversationMemoryService,
)
from services.retrieval.conversation_store import (
    close_conversation_store,
    get_conversation_store,
)
from services.retrieval.tool_store import close_tool_store


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

logger = logging.getLogger(__name__)


async def main() -> None:
    pool = AsyncConnectionPool(
        conninfo=settings.POSTGRE_URI,
        min_size=1,
        max_size=5,
        open=False,
    )
    await pool.open()

    memory_store = get_conversation_store()
    memory_service = ConversationMemoryService(memory_store)

    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.POSTGRE_URI
        ) as checkpointer:
            manager = CheckpointManager(checkpointer)
            await manager.setup()

            graph = await build_graph(checkpointer)

            chat_service = ChatService(
                repo=ThreadRepository(pool),
                profile_repo=UserProfileRepository(pool),
                graph=graph,
                memory_service=memory_service,
            )

            result = await chat_service.chat(
                user_id="test-user",
                thread_id="test-user:05b30689",
                question="我想去长沙，有什么值得去吃的？",
            )

            logger.info(
                "thread_id=%s answer=%s",
                result.thread_id,
                result.answer,
            )

    finally:
        close_tool_store()
        close_conversation_store()
        await close_tool_cache()
        await pool.close()


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
