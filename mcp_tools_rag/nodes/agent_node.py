import logging

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from services.ingestion.user_profile_service import build_profile_context
from mcp_tools_rag.common.retry import call_with_retry
from mcp_tools_rag.common.state import AgentState
from mcp_tools_rag.common.prompt import AGENT_PROMPT
from mcp_tools_rag.common.turn import end_turn
from mcp_tools_rag.common.message_manager import (
    prepare_visible_history,
    build_memory_context
)
from datetime import datetime, timedelta, timezone
import json

logger = logging.getLogger(__name__)

NOW = datetime.now(timezone(timedelta(hours=8)))

MAX_ATTEMPT = 2

FALLBACK_MESSAGES = {
    "tool_not_found": (
        "我没能找到合适的工具来处理这个请求。"
        "可以换一种说法，或补充更多信息。"
    ),
    "service_unavailable": (
        "地图服务暂时不可用，请稍后再试。"
    ),
    "tool_config_error": (
        "工具配置异常，暂时无法完成查询。"
        "请稍后再试或联系管理员。"
    ),
    "tool_error": (
        "工具查询暂时失败，请稍后再试。"
    ),
    "validation_error": (
        "我没能正确理解请求参数。"
        "可以补充地点、时间等信息。"
    ),
    "no_result": (
        "没有查到相关结果，可以换个关键词试试。"
    ),
    "unknown": (
        "抱歉，这次没有得到可靠结果。"
    ),
    "tool_output_error": (
        "工具返回的数据格式异常，暂时无法解析。"
        "请稍后再试。"
    ),
}

def build_tool_defs(candidates: list[dict]) -> list[dict]:
    """构造 function schema"""
    tool_defs = []

    for candidate in candidates:

        logger.debug(
            "tool candidate name=%s score=%s",
            candidate["tool_name"],
            candidate.get("rerank_score"),
        )

        schema = candidate["schema"]

        if isinstance(schema, str):
            schema = json.loads(schema)

        tool_defs.append({
            "type": "function",
            "function": {
                "name": candidate["llm_name"],
                "description": candidate["description"],
                "parameters": schema or {
                    "type": "object",
                    "properties": {},
                },
            },
        })

    return tool_defs


def current_turn_messages(messages: list) -> list:
    """取最后一个 HumanMessage 之后的消息。"""
    last_human_index = -1

    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            last_human_index = index
            break

    if last_human_index == -1:
        return messages[-6:]

    return messages[last_human_index:]

def summarize_existing(state: AgentState, llm):
    """部分工具成功调用"""

    context = current_turn_messages(state["messages"])

    return llm.ainvoke([
        SystemMessage(
            content=(
                "只能基于已有工具结果回答。"
                "不要调用任何工具。"
                "如果有失败的部分，简要说明没有查到。"
            )
        ),
        *context,
    ])

async def agent_node(
    state: AgentState,
    llm,
    config: RunnableConfig | None = None,
) -> Command:
    """agent节点"""
    attempt = state.get("retry_count") or 0
    has_success = state.get("has_success", False)
    has_fatal_error = state.get("has_fatal_error", False)
    retryable_call_ids = state.get("retryable_call_ids") or []
    failure_type = state.get("failure_type") or "unknown"

    # 存在不可重试错误、无可修复调用
    if has_fatal_error and not retryable_call_ids:
        # 部分成功
        if has_success:
            resp = await summarize_existing(state, llm)
            return end_turn(content=resp.content)

        # 全部失败
        return end_turn(content=FALLBACK_MESSAGES[failure_type])

    # 重试最大限
    if attempt >= MAX_ATTEMPT:
        # 部分成功
        if has_success:
            resp = await summarize_existing(state, llm)
            return end_turn(content=resp.content)

        # 全部失败
        return end_turn(content=FALLBACK_MESSAGES[failure_type])

    history = prepare_visible_history(state["messages"])

    profile_data = (
        (config or {})
        .get("configurable", {})
        .get("user_profile")
    )

    messages = [
        # 系统提示词
        SystemMessage(content=AGENT_PROMPT.format(current_time=NOW)),
        # 用户画像
        *build_profile_context(profile_data),
        # 召回记忆
        *build_memory_context(
            memories=state.get("memories") or [],
            history=history,
        ),
        # 最近 N 轮对话
        *history,
    ]

    logger.info(
        "agent context state_messages=%s llm_messages=%s",
        len(state["messages"]),
        len(messages),
    )

    # 构造function schema
    tool_defs = build_tool_defs(state.get('to_candidates') or [])

    logger.debug("bound tool defs=%s", len(tool_defs))

    # 动态绑定工具
    llm_with_tools = llm.bind_tools(tool_defs) if tool_defs else llm

    try:
        resp = await call_with_retry(
            lambda: llm_with_tools.ainvoke(messages),
            attempts=3,
        )
    except Exception:
        logger.exception("agent llm call failed")
        return end_turn(
            content="网络失败，请稍后重试。",
            skip_memory=True,
        )

    return Command(
        update={"messages": [resp]},
        goto="validate",
    ) if resp.tool_calls else end_turn(content=resp.content)




