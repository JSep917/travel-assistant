import logging
from collections.abc import AsyncIterator
from uuid import uuid4

from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from pydantic import BaseModel

from mcp_tools_rag.common.thread_utils import (
    build_preview,
    build_title,
    message_text,
)
from services.database.repositories import (
    ThreadRepository,
    UserProfileRepository,
)
from services.ingestion.conversation_memory_service import (
    ConversationMemoryService,
)
from services.ingestion.user_profile_service import update_user_profile

logger = logging.getLogger(__name__)


class ChatResult(BaseModel):
    thread_id: str
    answer: str
    messages: list[BaseMessage]


class ChatService:
    """一次完整对话：校验会话、执行图、更新画像和记忆。"""

    def __init__(
        self,
        repo: ThreadRepository,
        profile_repo: UserProfileRepository,
        graph,
        memory_service: ConversationMemoryService,
    ):
        self.repo = repo
        self.profile_repo = profile_repo
        self.graph = graph
        self.memory_service = memory_service

    async def chat(
        self,
        user_id: str,
        question: str,
        thread_id: str | None = None,
    ) -> ChatResult:
        thread_id = thread_id or f"{user_id}:{uuid4().hex[:8]}"

        # 查询会话是否存在
        thread = await self.repo.get(thread_id, user_id)

        if thread is None:
            # 创建新会话
            thread = await self.repo.create(
                thread_id=thread_id,
                user_id=user_id,
                title="新会话",
            )

        if thread is None:
            raise RuntimeError("创建会话失败")

        human = HumanMessage(content=question)
        human_text = message_text(human)

        old_profile = await self.profile_repo.get(user_id)

        result = await self.graph.ainvoke(
            {"messages": [human]},
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "user_profile": old_profile or {},
                }
            },
        )

        final_ai = result["messages"][-1]
        ai_text = message_text(final_ai)
        # 增加更新用户画像
        await self._update_profile(
            user_id=user_id,
            old_profile=old_profile,
            human_text=human_text,
            ai_text=ai_text,
        )
        # 写入对话历史
        await self._write_memory(
            thread_id=thread_id,
            user_id=user_id,
            human_text=human_text,
            ai_text=ai_text,
        )
        # 更新 threads 元数据
        await self._update_thread_meta(
            thread=thread,
            thread_id=thread_id,
            user_id=user_id,
            messages=result["messages"],
        )

        return ChatResult(
            thread_id=thread_id,
            answer=final_ai.content,
            messages=result["messages"],
        )

    async def stream_chat(
        self,
        user_id: str,
        question: str,
        thread_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """流式执行一轮对话，按 token 产出 SSE 事件。"""
        thread_id = thread_id or f"{user_id}:{uuid4().hex[:8]}"

        thread = await self.repo.get(thread_id, user_id)

        if thread is None:
            thread = await self.repo.create(
                thread_id=thread_id,
                user_id=user_id,
                title="新会话",
            )

        if thread is None:
            raise RuntimeError("创建会话失败")

        human = HumanMessage(content=question)
        human_text = message_text(human)
        old_profile = await self.profile_repo.get(user_id)

        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_profile": old_profile or {},
            }
        }

        # 先告诉前端新会话的 thread_id
        yield {
            "type": "meta",
            "thread_id": thread_id,
        }

        parts: list[str] = []

        try:
            async for message, metadata in self.graph.astream(
                {"messages": [human]},
                config=config,
                stream_mode="messages",
            ):
                if metadata.get("langgraph_node") != "agent":
                    continue

                text = self._stream_text(message)

                if not text:
                    continue

                # 规避 token流后 额外输出一次完整回答
                if parts and text == "".join(parts):
                    continue

                parts.append(text)
                yield {
                    "type": "token",
                    "content": text,
                }
        except Exception:
            logger.exception(
                "chat stream failed thread=%s",
                thread_id,
            )
            yield {
                "type": "error",
                "detail": "生成回答失败，请稍后重试",
            }
            return

        ai_text = "".join(parts).strip()

        try:
            state = await self.graph.aget_state(config)
            final_messages = state.values.get("messages", [])

            if not ai_text:
                final_ai = final_messages[-1]
                ai_text = message_text(final_ai)
                yield {
                    "type": "token",
                    "content": ai_text,
                }
            # 增加更新用户画像
            await self._update_profile(
                user_id=user_id,
                old_profile=old_profile,
                human_text=human_text,
                ai_text=ai_text,
            )
            # 写入对话历史
            await self._write_memory(
                thread_id=thread_id,
                user_id=user_id,
                human_text=human_text,
                ai_text=ai_text,
            )
            # 更新 threads 元数据
            await self._update_thread_meta(
                thread=thread,
                thread_id=thread_id,
                user_id=user_id,
                messages=final_messages,
            )
        except Exception:
            logger.exception(
                "chat postprocess failed thread=%s",
                thread_id,
            )

        yield {
            "type": "done",
            "thread_id": thread_id,
            "answer": ai_text,
        }

    @staticmethod
    def _stream_text(message: BaseMessage) -> str:
        """只提取最终回答的 token，忽略完整消息和工具调用。"""
        if not isinstance(message, AIMessageChunk):
            return ""

        if (
            getattr(message, "tool_calls", None)
            or getattr(message, "tool_call_chunks", None)
        ):
            return ""

        content = message.content

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict)
            )

        return ""

    async def _update_profile(
        self,
        user_id: str,
        old_profile: dict | None,
        human_text: str,
        ai_text: str,
    ) -> None:
        try:
            new_profile = await update_user_profile(
                old_profile=old_profile,
                human_text=human_text,
                ai_text=ai_text,
            )

            if new_profile.model_dump() != (old_profile or {}):
                await self.profile_repo.upsert(
                    user_id=user_id,
                    profile=new_profile.model_dump(),
                )
        except Exception:
            logger.exception(
                "profile update failed user=%s",
                user_id,
            )

    async def _write_memory(
        self,
        thread_id: str,
        user_id: str,
        human_text: str,
        ai_text: str,
    ) -> None:
        try:
            await self.memory_service.add_turn(
                thread_id=thread_id,
                user_id=user_id,
                human_text=human_text,
                ai_text=ai_text,
            )
        except Exception:
            logger.exception(
                "memory write failed thread=%s",
                thread_id,
            )

    async def _update_thread_meta(
        self,
        thread: dict,
        thread_id: str,
        user_id: str,
        messages: list,
    ) -> None:
        """更新 threads 业务表元数据"""
        new_title = build_title(messages)

        if (
            thread.get("title_source") == "auto"
            and new_title != "新会话"
            and new_title != thread.get("title")
        ):
            await self.repo.update_title_auto(
                thread_id=thread_id,
                user_id=user_id,
                title=new_title,
            )

        preview = build_preview(messages)
        await self.repo.touch_thread(
            thread_id=thread_id,
            user_id=user_id,
            preview=str(preview),
        )
