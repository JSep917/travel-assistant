from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage
from mcp_tools_rag.common.llm_services import get_memory_llm
from mcp_tools_rag.common.prompt import MEMORY_CARD_PROMPT
from mcp_tools_rag.common.retry import call_with_retry


class MemoryCard(BaseModel):
    """一轮对话的结构化记忆卡片。"""
    topic: str = Field(default="", description="本轮主题")
    intent: str = Field(default="", description="用户本轮意图")
    summary: str = Field(
        default="",
        description="本轮摘要",
        max_length=100,
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="用于检索的关键词",
        max_length=5,
    )
    skip_memory: bool = Field(
        default=False,
        description="是否跳过长期记忆写入",
    )

    @classmethod
    def empty(cls) -> "MemoryCard":
        return cls(skip_memory=True)

    def to_context(self) -> str:
        """拼接用于 BM25/Dense 的增强检索文本。"""
        parts = [
            f"主题：{self.topic}",
            f"意图：{self.intent}",
            f"摘要：{self.summary}",
            f"关键词：{'、'.join(self.keywords)}",
        ]

        return "\n".join(
            part
            for part in parts
            if part.split("：", 1)[-1].strip()
        )

async def extract_memory_card(human_text: str, ai_text: str):
    """调用轻量模型抽取记忆卡片。"""
    prompt = MEMORY_CARD_PROMPT.format(
        human_text=human_text[:200],
        ai_text=ai_text[:400],
    )

    llm = get_memory_llm().with_structured_output(
        MemoryCard,
        method="json_mode",
    )

    return await call_with_retry(
        lambda: llm.ainvoke([
            SystemMessage(content=prompt)
        ]),
        attempts=2,
    )
