import json
import logging

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    ValidationError,
)

from mcp_tools_rag.common.llm_services import get_profile_llm
from mcp_tools_rag.common.prompt import USER_PROFILE_PROMPT
from mcp_tools_rag.common.retry import call_with_retry
from langchain_core.messages import SystemMessage
from services.database.repositories import UserProfileRepository

logger = logging.getLogger(__name__)

class UserProfilePatch(BaseModel):
    """API 请求体模型"""
    city: str | None = None
    dining_preferences: list[str] | None = None
    transport_preferences: list[str] | None = None
    accommodation_preferences: list[str] | None = None
    activity_preferences: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "activity_preferences",
            "attraction_preferences",
        ),
    )

class UserProfile(BaseModel):
    """跨会话的长期用户画像。"""

    city: str = Field(
        default="",
        description="用户常住或默认出发城市",
        max_length=50,
    )
    dining_preferences: list[str] = Field(
        default_factory=list,
        description="餐饮偏好，如不吃辣、不甜、咸鲜、素食",
        max_length=10,
    )
    transport_preferences: list[str] = Field(
        default_factory=list,
        description="交通偏好，如步行优先、地铁优先、打车",
        max_length=10,
    )
    accommodation_preferences: list[str] = Field(
        default_factory=list,
        description="住宿偏好，如安静、近地铁、亲子",
        max_length=10,
    )
    activity_preferences: list[str] = Field(
        default_factory=list,
        description="游玩偏好，如历史、博物馆、自然风光、亲子",
        max_length=10,
        validation_alias=AliasChoices(
            "activity_preferences",
            "attraction_preferences",
        ),
    )

    def to_context(self) -> str:
        lines = [
            f"城市：{self.city}" if self.city else "",
            (
                f"餐饮偏好：{'、'.join(self.dining_preferences)}"
                if self.dining_preferences
                else ""
            ),
            (
                f"交通偏好：{'、'.join(self.transport_preferences)}"
                if self.transport_preferences
                else ""
            ),
            (
                f"住宿偏好：{'、'.join(self.accommodation_preferences)}"
                if self.accommodation_preferences
                else ""
            ),
            (
                f"游玩偏好：{'、'.join(self.activity_preferences)}"
                if self.activity_preferences
                else ""
            ),
        ]

        return "\n".join(line for line in lines if line)


class UserProfileService:
    """user_profiles 业务层"""
    def __init__(self, repo: UserProfileRepository):
        self.repo = repo

    async def get(self, user_id: str) -> UserProfile:
        """获取用户画像"""
        data = await self.repo.get(user_id)

        return normalize_user_profile(data)

    async def update_manual(
        self,
        user_id: str,
        patch: UserProfilePatch,
    ) -> UserProfile:
        """用户自行修改画像"""
        current = await self.get(user_id)

        data = current.model_dump()
        data.update(
            patch.model_dump(exclude_unset=True)
        )

        try:
            profile = UserProfile.model_validate(data)
        except ValidationError as exc:
            logger.warning(
                "invalid user profile user=%s errors=%s",
                user_id,
                exc.errors(),
            )
            raise ValueError("画像数据不合法") from exc

        await self.repo.upsert(
            user_id=user_id,
            profile=profile.model_dump(),
        )

        return profile


def normalize_user_profile(
    profile: dict | UserProfile | None,
) -> UserProfile:
    """把 dict / None / UserProfile 统一成 UserProfile。"""
    if isinstance(profile, UserProfile):
        return profile

    if not profile:
        return UserProfile()

    try:
        return UserProfile.model_validate(profile)
    except Exception:
        logger.warning(
            "invalid user profile, reset",
            exc_info=True,
        )
        return UserProfile()


def merge_user_profile(
    old: UserProfile,
    new: UserProfile,
) -> UserProfile:
    """新画像为空时保留旧值，列表去重。"""
    if not new.city:
        new.city = old.city

    new.dining_preferences = _dedupe(
        new.dining_preferences or old.dining_preferences
    )
    new.transport_preferences = _dedupe(
        new.transport_preferences or old.transport_preferences
    )
    new.accommodation_preferences = _dedupe(
        new.accommodation_preferences
        or old.accommodation_preferences
    )
    new.activity_preferences = _dedupe(
        new.activity_preferences
        or old.activity_preferences
    )
    return new


async def update_user_profile(
    old_profile: dict | UserProfile | None,
    human_text: str,
    ai_text: str,
    llm=None,
) -> UserProfile:
    """从一轮对话中抽取并合并用户画像。"""
    old = normalize_user_profile(old_profile)
    base_llm = llm or get_profile_llm()

    prompt = USER_PROFILE_PROMPT.format(
        old_profile=json.dumps(
            old.model_dump(),
            ensure_ascii=False,
        ),
        human_text=human_text[:200],
        ai_text=ai_text[:400],
    )

    structured_llm = base_llm.with_structured_output(
        UserProfile,
        method="json_mode",
    )

    try:
        result = await call_with_retry(
            lambda: structured_llm.ainvoke([
                SystemMessage(content=prompt)
            ]),
            attempts=2,
        )
    except Exception:
        logger.warning(
            "user profile generation failed",
            exc_info=True,
        )
        return old
    # 拦截 None
    if not isinstance(result, UserProfile):
        logger.warning(
            "user profile invalid type=%s",
            type(result).__name__,
        )
        return old

    return merge_user_profile(old, result)


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()

    for item in items:
        text = (item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)

    return result


def build_profile_context(
    profile: dict | UserProfile | None,
) -> list:
    """把用户画像转成注入 agent 的消息列表。"""
    if not profile:
        return []

    profile = normalize_user_profile(profile)
    profile_text = profile.to_context()

    if not profile_text:
        return []

    return [
        SystemMessage(
            content=(
                "用户长期画像，仅作参考：\n"
                f"{profile_text}\n"
                "如果与本轮用户明确表达冲突，以本轮表达为准。"
            )
        )
    ]