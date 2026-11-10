from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from config import settings
from mcp_tools_rag.app.api.chat import router as chat_router
from mcp_tools_rag.app.api.delete import router as delete_router
from mcp_tools_rag.app.api.rename import router as rename_router
from mcp_tools_rag.app.api.profile import router as profile_router
from mcp_tools_rag.app.api.threads import router as threads_router
from mcp_tools_rag.common.logging_config import setup_logging
from mcp_tools_rag.graph.graph import build_graph
from services.cache.tool_cache import close_tool_cache
from services.chat.chat_service import ChatService
from services.threads.thread_lifecycle_service import ThreadLifecycleService
from services.ingestion.user_profile_service import UserProfileService
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动资源，关闭时统一释放。"""
    setup_logging()

    pool = AsyncConnectionPool(
        conninfo=settings.POSTGRE_URI,
        min_size=1,
        max_size=10,
        open=False,
    )

    try:
        await pool.open()

        async with AsyncPostgresSaver.from_conn_string(
            settings.POSTGRE_URI
        ) as checkpointer:
            manager = CheckpointManager(checkpointer)
            await manager.setup()

            graph = await build_graph(checkpointer)

            thread_repo = ThreadRepository(pool)
            profile_repo = UserProfileRepository(pool)
            memory_service = ConversationMemoryService(
                get_conversation_store()
            )

            app.state.pool = pool
            app.state.graph = graph
            app.state.thread_repo = thread_repo
            app.state.profile_repo = profile_repo

            app.state.chat_service = ChatService(
                repo=thread_repo,
                profile_repo=profile_repo,
                graph=graph,
                memory_service=memory_service,
            )

            app.state.thread_service = ThreadLifecycleService(
                repo=thread_repo,
                checkpoints=manager,
                memory_service=memory_service,
            )

            app.state.profile_service = UserProfileService(
                repo=profile_repo,
            )

            yield

    finally:
        # 关闭连接、清除缓存
        close_tool_store()
        close_conversation_store()
        await close_tool_cache()
        await pool.close()


app = FastAPI(title="智能出行助手", lifespan=lifespan)

app.include_router(chat_router)
app.include_router(delete_router)
app.include_router(rename_router)
app.include_router(profile_router)
app.include_router(threads_router)


@app.get("/")
async def root():
    # 重定向
    return RedirectResponse(url="/docs")
