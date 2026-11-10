import logging
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from mcp_tools_rag.common.state import AgentState
from services.retrieval.conversation_store import get_conversation_store
from services.retrieval.embedding import get_embeddings
from services.retrieval.rerank_dashscope import (
    rerank_tools,
    rerank_memories,
    filter_by_relative_score,
)
from services.retrieval.tool_store import get_tool_store
import asyncio
import hashlib
import re


logger = logging.getLogger(__name__)


def make_llm_tool_name(server_name: str, name: str) -> str:
    """安全工具名 加前缀避免多 MCP 工具名冲突"""
    raw = f"{server_name}_{name}"

    safe = re.sub(r"[^A-Za-z0-9_-]", "_", raw)

    if not safe or not safe[0].isalpha():
        safe = f"tool_{safe}"

    if len(safe) > 64:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
        safe = f"{safe[:57]}_{digest}"
    return safe


async def retrieve_node(
    state: AgentState,
    config: RunnableConfig,
) -> Command[Literal['agent']]:
    """只负责检索工具候选和旧对话记忆。"""
    query = (state.get("rewrite_query") or "").strip()

    thread_id = (
        (config or {})
        .get("configurable", {})
        .get("thread_id", "")
    )
    user_id = thread_id.split(":")[0]

    need_tools = state.get("need_tools", True)
    need_memory = state.get("need_memory", True)

    query_vector = await get_embeddings().aembed_query(query)
    tool_store = get_tool_store()
    memory_store = get_conversation_store()

    tool_task = asyncio.to_thread(
        tool_store.search_tools,
        query=query,
        query_vector=query_vector,
        top_k=20,
    ) if need_tools else asyncio.sleep(0, result=[])

    memory_task = asyncio.to_thread(
        memory_store.search_memorise,
        query=query,
        query_vector=query_vector,
        user_id=user_id,
        thread_id=thread_id,
        top_k=20,
    ) if need_memory else asyncio.sleep(0, result=[])

    # 工具检索和记忆召回并行；记忆失败不影响工具检索
    rrf_candidates, rrf_memories = await asyncio.gather(
        tool_task,
        memory_task,
        return_exceptions=True,
    )

    if isinstance(rrf_candidates, Exception):
        # 工具检索失败 抛出异常
        raise rrf_candidates

    if isinstance(rrf_memories, Exception):
        # 记忆检索失败 不影响回答
        rrf_memories = []

    tool_task = asyncio.to_thread(
        rerank_tools,
        query=query,
        candidates=rrf_candidates,
        top_n=10,
    ) if need_tools and rrf_candidates else asyncio.sleep(0, result=[])

    memory_task = asyncio.to_thread(
        rerank_memories,
        query=query,
        memories=rrf_memories,
        top_n=10,
    ) if need_memory and rrf_memories else asyncio.sleep(0, result=[])

    # 工具、记忆精排并行执行
    candidates, memories = await asyncio.gather(
        tool_task,
        memory_task,
        return_exceptions=True,
    )
    if isinstance(candidates, Exception):
        # 工具精排失败，退回 RRF Top5
        candidates = rrf_candidates[:5]

    if isinstance(memories, Exception):
        # 记忆精排失败，退回 RRF Top5
        memories = rrf_memories[:5]

    # 候选工具集阈值过滤
    candidates = filter_by_relative_score(
        items=candidates,
        ratio=0.5,
        min_score=0.1,
        limit=5
    )
    # 记忆召回阈值过滤
    memories = filter_by_relative_score(
        items=memories,
        ratio=0.6,
        min_score=0.2,
        limit=5
    )

    # 组装工具名映射
    tool_map = {}
    for candidate in candidates:
        llm_name = make_llm_tool_name(
            candidate["server_name"],
            candidate["tool_name"],
        )
        candidate["llm_name"] = llm_name
        tool_map[llm_name] = candidate

    logger.info(
        "retrieve tools=%s memories=%s",
        len(candidates),
        len(memories),
    )

    return Command(
        update={
            "to_candidates": candidates,
            "tool_map": tool_map,
            "memories": memories,
        },
        goto="agent",
    )
