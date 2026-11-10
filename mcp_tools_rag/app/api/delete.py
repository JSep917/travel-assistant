import logging

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Depends,
    Response,
    Path,
    status
)

from services.threads.thread_lifecycle_service import ThreadLifecycleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["delete"])

def get_thread_service(request: Request) -> ThreadLifecycleService:
    return request.app.state.thread_service

@router.delete(
    "/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除会话",
    description="删除指定会话及其 checkpoint、记忆和业务记录。",
)
async def delete_thread(
    thread_id: str = Path(description="会话ID"),
    service: ThreadLifecycleService = Depends(get_thread_service),
):
    # TODO: 从认证信息获取
    user_id = "test-user"

    ok = await service.delete_thread(
        thread_id=thread_id,
        user_id=user_id,
    )

    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"Thread {thread_id} not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
