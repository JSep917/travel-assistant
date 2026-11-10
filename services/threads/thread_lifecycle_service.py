import logging


logger = logging.getLogger(__name__)


class ThreadLifecycleService:
    """threads 业务表服务层"""
    def __init__(
        self,
        repo,
        checkpoints,
        memory_service,
    ):
        self.repo = repo
        self.checkpoints = checkpoints
        self.memory_service = memory_service

    async def rename_thread(
        self,
        thread_id: str,
        user_id: str,
        title: str,
    ) -> bool:
        """修改会话标题，并标记为用户自定义。"""
        title = (title or "").strip()[:50]

        if not title:
            return False

        thread = await self.repo.get(thread_id, user_id)
        # 会话不存在
        if thread is None:
            return False

        return await self.repo.rename(
            thread_id=thread_id,
            user_id=user_id,
            title=title,
        )

    async def delete_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> bool:
        """用户删除会话"""
        # 校验会话属于当前用户
        thread = await self.repo.get(thread_id, user_id)
        if thread is None:
            return False

        # 删 checkpoint
        await self.checkpoints.delete_thread(thread_id)

        # 删向量记忆
        await self.memory_service.delete_by_thread(thread_id)

        # 删业务记录
        await self.repo.delete(thread_id, user_id)

        return True

