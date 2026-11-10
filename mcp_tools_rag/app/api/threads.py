from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from services.database.repositories import ThreadRepository

router = APIRouter(prefix="/api", tags=["threads"])


class ThreadItem(BaseModel):
    thread_id: str
    title: str
    last_message_preview: str
    updated_at: datetime | None = None


class MessageItem(BaseModel):
    role: str
    content: str


def get_current_user_id() -> str:
    # TODO: 替换为 token/session 认证
    return "test-user"


def get_thread_repo(request: Request) -> ThreadRepository:
    return request.app.state.thread_repo


def raw_message_text(message) -> str:
    content = message.content

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict)
        ).strip()

    return str(content or "").strip()


@router.get(
    "/threads",
    response_model=list[ThreadItem],
    summary="会话列表",
)
async def list_threads(
    user_id: str = Depends(get_current_user_id),
    repo: ThreadRepository = Depends(get_thread_repo),
):
    rows = await repo.list_by_user(user_id)

    return [
        ThreadItem(
            thread_id=row["thread_id"],
            title=row["title"] or "新会话",
            last_message_preview=row["last_message_preview"] or "",
            updated_at=row.get("updated_at"),
        )
        for row in rows
    ]


@router.get(
    "/threads/{thread_id}/messages",
    response_model=list[MessageItem],
    summary="会话历史",
)
async def get_thread_messages(
    thread_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    repo: ThreadRepository = Depends(get_thread_repo),
):
    thread = await repo.get(thread_id, user_id)

    if thread is None:
        raise HTTPException(404, "会话不存在")

    state = await request.app.state.graph.aget_state({
        "configurable": {
            "thread_id": thread_id,
        }
    })

    messages = state.values.get("messages", [])
    result = []

    for message in messages:
        text = raw_message_text(message)

        if not text:
            continue

        if message.type == "human":
            result.append(MessageItem(role="user", content=text))
        elif message.type == "ai" and not getattr(
            message,
            "tool_calls",
            None,
        ):
            result.append(
                MessageItem(role="assistant", content=text)
            )

    return result
