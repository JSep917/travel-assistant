from fastapi import APIRouter, Depends, HTTPException, Request

from services.ingestion.user_profile_service import (
    UserProfile,
    UserProfileService,
)

from services.ingestion.user_profile_service import UserProfilePatch

router = APIRouter(prefix="/api", tags=["profile"])

def get_profile_service(request: Request) -> UserProfileService:
    return request.app.state.profile_service

@router.get(
    "/profile",
    response_model=UserProfile,
    summary="查看用户画像",
)
async def get_profile(
    service: UserProfileService = Depends(get_profile_service),
) -> UserProfile:
    # TODO: 从认证信息获取
    user_id = "test-user"

    return await service.get(user_id)

@router.patch(
    "/profile",
    response_model=UserProfile,
    summary="修改用户画像",
)
async def update_profile(
    body: UserProfilePatch,
    service: UserProfileService = Depends(get_profile_service),
):
    # TODO: 从认证信息获取
    user_id = "test-user"

    try:
        return await service.update_manual(
            user_id=user_id,
            patch=body,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )