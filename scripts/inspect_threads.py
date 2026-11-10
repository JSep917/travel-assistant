import asyncio
import logging
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from mcp_tools_rag.common.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def main():
    """业务表全量查询"""
    with psycopg.connect(settings.POSTGRE_URI) as conn:
        rows = conn.execute(
            """
            select
                thread_id, user_id, title,
                last_message_preview, updated_at
            from threads
            order by updated_at desc
            """
        ).fetchall()

        for row in rows:
            logger.info("thread=%s", row)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())