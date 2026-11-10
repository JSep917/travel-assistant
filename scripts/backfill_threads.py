from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from mcp_tools_rag.graph.graph import build_graph
from mcp_tools_rag.common.thread_utils import build_title, build_preview
from config import settings
import psycopg
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )

async def main():
    """回填业务表"""
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

                title = build_title(messages)
                preview = build_preview(messages)
                user_id = thread_id.split(":", 1)[0]

                async with conn.transaction():
                    await conn.execute(
                        """
                        insert into threads (
                            thread_id, user_id, title,
                            last_message_preview
                        )
                        values (%s, %s, %s, %s)
                        on conflict (thread_id) do update
                        set
                            title = case
                                when threads.title_source = 'user'
                                then threads.title
                                else excluded.title
                            end,
                            last_message_preview = excluded.last_message_preview,
                            updated_at = now()
                        """,
                        (thread_id, user_id, title, preview),
                    )

if __name__ == "__main__":
    asyncio.run(main())