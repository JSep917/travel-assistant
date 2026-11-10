from services.database.repositories import CheckpointManager
from psycopg_pool import AsyncConnectionPool
from services.retrieval.conversation_store import (
    get_conversation_store,
    close_conversation_store
)
from config import settings

async def cleanup_expired_threads(
    pool,
    checkpoints,
    memory_store,
    days: int = 90,
    batch_size: int = 100,
):
    """TTL定时清理策略"""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select thread_id, user_id
                from threads
                where updated_at < now() - make_interval(days => %s)
                order by updated_at
                limit %s
                """,
                (days, batch_size),
            )
            rows = await cur.fetchall()

    for row in rows:
        thread_id = row["thread_id"]
        user_id = row["user_id"]

        # 删 checkpointer
        await checkpoints.delete_thread(thread_id)

        # 删业务记录
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    delete from threads
                    where thread_id = %s and user_id = %s
                    """,
                    (thread_id, user_id),
                )
        # 删向量记忆
        memory_store.delete_by_thread(thread_id)

async def main():
    # 创建连接池对象
    pool = AsyncConnectionPool(
        conninfo=settings.POSTGRE_URI,
        min_size=1,
        max_size=5,
        open=False,
    )
    # 启动连接池
    await pool.open()

    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.POSTGRE_URI
        ) as checkpointer:

            checkpoints = CheckpointManager(checkpointer)
            memory_store = get_conversation_store()
            await cleanup_expired_threads(pool, checkpoints, memory_store)

    finally:
        close_conversation_store()
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())