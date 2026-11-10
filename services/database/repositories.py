from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

class ThreadRepository:
    """会话业务表 threads 的数据访问层"""

    def __init__(self, pool):
        self.pool = pool

    async def create(
        self,
        thread_id: str,
        user_id: str,
        title: str = "新会话",
        tenant_id: str | None = None,
    ) -> dict:
        """新建一条会话业务记录。"""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    insert into threads (
                        thread_id, tenant_id, user_id, title
                    )
                    values (%s, %s, %s, %s)
                    on conflict (thread_id) do update
                    set updated_at = now()
                    returning *
                    """,
                    (thread_id, tenant_id, user_id, title),
                )
                return await cur.fetchone()

    async def touch_thread(self, thread_id: str, user_id: str, preview: str = "") -> bool:
        """更新会话的最后消息预览和活跃时间。"""
        preview = (preview or "").strip()[:100]

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    update threads
                    set 
                        last_message_preview = %s,
                        updated_at = now()
                    where thread_id = %s and user_id = %s
                    """,
                    (preview, thread_id, user_id),
                )
                return cur.rowcount > 0

    async def list_by_user(self, user_id: str, limit: int = 50) -> list[dict]:
        """查用户会话列表"""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    select *
                    from threads
                    where user_id = %s
                      and archived_at is null
                    order by updated_at desc
                    limit %s
                    """,
                    (user_id, limit),
                )
                return await cur.fetchall()

    async def update_title_auto(self, thread_id: str, user_id: str, title: str,) -> bool:
        """只更新自动标题，不覆盖用户手动标题。"""
        title = title.strip()[:50]
        if not title:
            return False

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    update threads
                    set 
                        title = %s,
                        updated_at = now()
                    where thread_id = %s
                      and user_id = %s
                      and title_source = 'auto'
                    """,
                    (title, thread_id, user_id),
                )
                return cur.rowcount > 0

    async def rename(self, thread_id: str, user_id: str, title: str) -> bool:
        """更新用户修改标题"""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    update threads
                    set 
                        title = %s,
                        title_source = 'user',
                        updated_at = now()
                    where thread_id = %s and user_id = %s
                    """,
                    (title[:50], thread_id, user_id),
                )
                return cur.rowcount > 0

    async def archive(self, thread_id: str, user_id: str) -> bool:
        """归档会话"""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    update threads
                    set archived_at = now()
                    where thread_id = %s and user_id = %s
                    """,
                    (thread_id, user_id),
                )
                return cur.rowcount > 0

    async def get(self, thread_id: str, user_id: str) -> dict | None:
        """查询单个会话"""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    select *
                    from threads
                    where thread_id = %s
                      and user_id = %s
                    """,
                    (thread_id, user_id),
                )
                return await cur.fetchone()

    async def delete(self, thread_id: str, user_id: str) -> bool:
        """删除单个会话"""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    delete
                    from threads
                    where thread_id = %s
                      and user_id = %s
                    """,
                    (thread_id, user_id),
                )
                return cur.rowcount > 0


class UserProfileRepository:
    """用户长期画像数据访问层。"""

    def __init__(self, pool):
        self.pool = pool

    async def get(self, user_id: str) -> dict | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    select profile
                    from user_profiles
                    where user_id = %s
                    """,
                    (user_id,),
                )
                row = await cur.fetchone()
                return row["profile"] if row else None

    async def upsert(
        self,
        user_id: str,
        profile: dict,
        tenant_id: str | None = None,
    ) -> None:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    insert into user_profiles (
                        user_id, tenant_id, profile
                    )
                    values (%s, %s, %s)
                    on conflict (user_id) do update
                    set
                        profile = excluded.profile,
                        updated_at = now()
                    """,
                    (
                        user_id,
                        tenant_id,
                        Jsonb(profile),
                    ),
                )


class CheckpointManager:
    """LangGraph checkpointer 的生命周期与删除封装。"""
    def __init__(self, checkpointer):
        self.checkpointer = checkpointer

    async def setup(self):
        """初始化/迁移 checkpoint 相关表"""
        await self.checkpointer.setup()

    async def delete_thread(self, thread_id: str):
        """删除指定 thread 的全部 checkpoint 数据。"""
        await self.checkpointer.adelete_thread(thread_id)