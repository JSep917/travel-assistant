from typing import NotRequired, TypedDict, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    rewrite_query: str | None
    need_tools: bool | None
    need_memory: bool | None

    to_candidates: list[dict] | None
    tool_map: dict[str, dict] | None
    # conversation_memory 召回的历史对话
    memories: list[dict] | None

    validate_errors: list | None
    validate_calls: list | None

    # 本轮允许重试的 tool_call_id（只包含参数错误等可修复调用）
    retryable_call_ids: list[str] | None

    retry_count: int | None
    # 全部失败 -> 错误优先级 -> 固定文案
    failure_type: str | None
    # 本轮是否有成功工具调用
    has_success: bool | None
    # 本轮是否存在不允许重试的工具错误
    has_fatal_error: bool | None

