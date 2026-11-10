from pydantic import BaseModel, Field, ConfigDict

from fastapi import (
    APIRouter,
    HTTPException,
    Depends,
    Request,
    Path
)

from services.threads.thread_lifecycle_service import ThreadLifecycleService

class RenameThreadRequest(BaseModel):
    # 修改 Example Value
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "新标题"
            }
        }
    )
    title: str = Field(
        min_length=1,
        max_length=50,
        description="新的会话标题",
    )

class RenameThreadResponse(BaseModel):
    thread_id: str = Field(description="会话ID")
    title: str = Field(
        min_length=1,
        max_length=50,
        description="新的会话标题",
    )

router = APIRouter(prefix="/api", tags=["rename"])

def get_thread_service(request: Request) -> ThreadLifecycleService:
    return request.app.state.thread_service

@router.patch(
    "/threads/{thread_id}",
    response_model=RenameThreadResponse,
    summary="修改会话标题",
)
async def rename_thread(
    body: RenameThreadRequest,
    thread_id: str = Path(description="会话ID"),
    service: ThreadLifecycleService = Depends(get_thread_service),
):
    # TODO: 从认证信息获取
    user_id = "test-user"

    title = body.title.strip()
    if not title:
        raise HTTPException(
            status_code=400,
            detail="标题不能为空",
        )

    ok = await service.rename_thread(
        thread_id=thread_id,
        user_id=user_id,
        title=title,
    )

    if not ok:
        raise HTTPException(404, "会话不存在")

    return RenameThreadResponse(
        thread_id=thread_id,
        title=title,
    )