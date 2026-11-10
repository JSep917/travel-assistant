import asyncio
import logging

logger = logging.getLogger(__name__)


async def call_with_retry(
    fn,
    attempts: int = 2,
    base_delay: float = 0.5,
):
    """重试异步 LLM 调用，耗尽后抛出最后一次异常。"""
    last_error = None

    for attempt in range(attempts):
        try:
            return await fn()
        except Exception as exc:
            last_error = exc
            logger.warning(
                "llm call failed attempt=%s/%s",
                attempt + 1,
                attempts,
                exc_info=True,
            )

            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (attempt + 1))

    raise last_error
