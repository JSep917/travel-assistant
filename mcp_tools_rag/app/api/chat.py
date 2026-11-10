import json
import logging

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    # 修改 Example Value
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "thread_id": "test-user:05b30689",
                "message": "北京有什么好吃的？"
            }
        }
    )

    thread_id: str | None = Field(
        default=None,
        description="会话 ID，不传则新建会话",
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="用户消息",
    )

class ChatResponse(BaseModel):
    thread_id: str = Field(description="会话 ID")
    answer: str = Field(description="助手回答")

def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="发送消息",
    description="执行一轮对话，返回助手回答和 thread_id。",
)
async def chat(
    body: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:

    # TODO: 从认证信息获取
    user_id = "test-user"

    try:
        result = await service.chat(
            user_id=user_id,
            thread_id=body.thread_id,
            question=body.message,
        )
    except Exception:
        logger.exception("chat request failed")
        raise HTTPException(
            status_code=503,
            detail="模型服务暂时不可用，请稍后重试",
        )

    return ChatResponse(
        thread_id=result.thread_id,
        answer=result.answer,
    )

@router.post(
    "/chat/stream",
    summary="流式发送消息",
    description="通过 SSE 逐 token 返回助手回答。",
)
async def chat_stream(
    body: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    # TODO: 从认证信息获取
    user_id = "test-user"

    async def event_generator():
        try:
            async for event in service.stream_chat(
                user_id=user_id,
                thread_id=body.thread_id,
                question=body.message,
            ):
                payload = json.dumps(
                    event,
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
        except Exception:
            logger.exception("chat stream request failed")
            payload = json.dumps(
                {
                    "type": "error",
                    "detail": "模型服务暂时不可用，请稍后重试",
                },
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
