import hashlib
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage
from mcp_tools_rag.common.thread_utils import message_text
from services.ingestion.memory_card import (
    MemoryCard,
    extract_memory_card,
)
from services.retrieval.conversation_store import ConversationStore
from services.retrieval.embedding import get_embeddings

logger = logging.getLogger(__name__)


class ConversationMemoryService:
    """会话记忆业务层。"""

    def __init__(self, store: ConversationStore):
        self.store = store

    async def delete_by_thread(self, thread_id: str) -> None:
        """删除某个会话的全部记忆。"""
        if not thread_id:
            return None

        memory_ids = self.store.list_memory_ids(
            thread_id=thread_id,
        )

        logger.info(
            "memory delete start thread=%s count=%s",
            thread_id,
            len(memory_ids),
        )

        self.store.delete_by_thread(thread_id)

    async def delete_by_user(self, user_id: str) -> None:
        """删除某个用户的全部记忆。"""
        if not user_id:
            return None

        memory_ids = self.store.list_memory_ids(
            user_id=user_id,
        )

        logger.info(
            "memory delete user=%s count=%s",
            user_id,
            len(memory_ids),
        )

        self.store.delete_by_user(user_id)

    async def add_turn(
        self,
        thread_id: str,
        user_id: str,
        human_text: str,
        ai_text: str,
        tenant_id: str = "",
    ) -> int:
        """写入一轮完整对话。"""
        return await self.add_turns(
            thread_id=thread_id,
            user_id=user_id,
            turns=[(human_text, ai_text)],
            tenant_id=tenant_id,
        )

    async def add_turns(
        self,
        thread_id: str,
        user_id: str,
        turns: list[tuple[str, str]],
        tenant_id: str = "",
    ) -> int:
        """批量写入多轮完整对话，用于回填。"""
        if not turns:
            return 0

        existing_ids = set(
            self.store.list_memory_ids(thread_id=thread_id)
        )

        logger.debug(
            "memory existing thread=%s count=%s",
            thread_id,
            len(existing_ids),
        )

        candidates = []
        seen_ids = set()

        for human_text, ai_text in turns:
            human_text = human_text.strip()
            ai_text = ai_text.strip()

            if not human_text or not ai_text:
                continue

            content = (
                f"用户：{human_text}\n"
                f"助手：{ai_text}"
            )

            memory_id = self._build_memory_id(
                thread_id=thread_id,
                human_text=human_text,
            )

            # 同一批内去重 + 已入库去重
            if memory_id in seen_ids or memory_id in existing_ids:
                continue

            seen_ids.add(memory_id)
            candidates.append((
                memory_id,
                human_text,
                ai_text,
                content,
            ))

        if not candidates:
            logger.debug("memory no new turns thread=%s", thread_id)
            return 0

        logger.debug(
            "memory new turns thread=%s count=%s",
            thread_id,
            len(candidates),
        )

        records = []

        for candidate in candidates:
            _, human_text, ai_text, content = candidate

            try:
                card = await extract_memory_card(
                    human_text=human_text,
                    ai_text=ai_text,
                )
            except Exception:
                logger.warning(
                    "memory card extraction failed thread=%s",
                    thread_id,
                    exc_info=True,
                )
                card = None

            # 拦截 None
            if not isinstance(card, MemoryCard):
                logger.warning(
                    "memory card is empty thread=%s type=%s",
                    thread_id,
                    type(card).__name__,
                )
                card = MemoryCard.empty()

            if card.skip_memory:
                continue

            search_text = card.to_context()
            records.append((candidate, search_text))

        if not records:
            logger.info(
                "memory skipped thread=%s reason=not_worth_remembering",
                thread_id,
            )
            return 0

        vectors = await get_embeddings().aembed_documents(
            [search_text for _, search_text in records]
        )

        now = int(time.time() * 1000)
        rows = []

        for (candidate, search_text), vector in zip(
            records,
            vectors,
        ):
            memory_id, _, _, content = candidate

            rows.append({
                "memory_id": memory_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "tenant_id": tenant_id or "",
                "content": content,
                "created_at": now,
                "dense": vector,
                "search_text": search_text,
            })

        for index in range(0, len(rows), 100):
            self.store.upsert(rows[index:index + 100])

        logger.info(
            "memory written thread=%s count=%s",
            thread_id,
            len(rows),
        )

        return len(rows)

    @staticmethod
    def split_turns(messages: list) -> list[tuple[str, str]]:
        """按 Human + 最终 AI 切分完整轮次。"""
        turns = []
        human_text = ""

        for message in messages:
            if isinstance(message, HumanMessage):
                human_text = message_text(message).strip()
                continue

            if (
                isinstance(message, AIMessage)
                and not message.tool_calls
                and message.content
            ):
                ai_text = message_text(message).strip()

                if human_text and ai_text:
                    turns.append((human_text, ai_text))

                human_text = ""

        return turns

    @staticmethod
    def _build_memory_id(
        thread_id: str,
        human_text: str,
    ) -> str:
        """thread_id + 整轮内容确定性哈希，用于幂等写入。"""
        digest = hashlib.sha256(
            f"memory:v2\x00{human_text}".encode("utf-8")
        ).hexdigest()[:32]

        return f"{thread_id}:{digest}"
