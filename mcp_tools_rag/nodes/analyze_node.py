import logging

from langgraph.types import Command
from mcp_tools_rag.common.state import AgentState
from mcp_tools_rag.common.prompt import ANALYZE_PROMPT
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from mcp_tools_rag.common.thread_utils import message_text
from mcp_tools_rag.common.message_manager import prepare_visible_history
from mcp_tools_rag.common.retry import call_with_retry
from mcp_tools_rag.common.turn import end_turn

logger = logging.getLogger(__name__)

def history_text(history: list) -> str:
    lines = []

    for message in history:
        text = message_text(message).strip()
        if not text:
            continue

        lines.append(
            f"{message.type}: {text[:500]}"
        )

    return "\n".join(lines)

class AnalyzeResult(BaseModel):
    need_tools: bool = Field(description="是否需要检索工具")
    need_memory: bool = Field(description="是否需要检索记忆")
    reason: str = Field(
        description="决策理由，说明为什么需要检索工具 / 记忆",
        max_length=50
    )
    rewrite_query: str = Field(
        description="查询补全 / 改写",
        max_length=70
    )

async def analyze_node(state: AgentState, llm) -> Command:
    """查询理解节点：判断动作、检索需求和改写 query。"""
    question = message_text(state['messages'][-1]).strip()

    history = prepare_visible_history(state["messages"][:-1])

    messages = [SystemMessage(content=ANALYZE_PROMPT.format(
        history=history_text(history),
        question=question,
    ))]

    llm_with_schema = llm.with_structured_output(
        AnalyzeResult,
        method="function_calling",
    )

    try:
        resp = await call_with_retry(
            lambda: llm_with_schema.ainvoke(messages),
            attempts=3,
        )
    except Exception:
        logger.exception("analyze llm call failed")
        return end_turn(
            content="网络失败，请稍后重试。",
            skip_memory=True
        )

    logger.info(
        "analyze need_tools=%s need_memory=%s",
        resp.need_tools,
        resp.need_memory,
    )

    if resp.need_tools or resp.need_memory:
        goto = "retrieve"
    else:
        goto = "agent"

    update = {
        "rewrite_query": resp.rewrite_query,
        "need_tools": resp.need_tools,
        "need_memory": resp.need_memory,
    }

    # 不检索工具时，清掉上一轮的工具候选，避免 agent 继续绑定旧工具
    if not resp.need_tools:
        update["to_candidates"] = None
        update["tool_map"] = None

    if not resp.need_memory:
        update["memories"] = None

    return Command(update=update, goto=goto)