import json
import logging

from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
    AIMessage
)
from mcp_tools_rag.common.thread_utils import message_text
import hashlib

logger = logging.getLogger(__name__)

MAX_TURNS = 10
MAX_TOKENS = 6000

def approx_tokens(messages: list) -> int:
    """粗略估算消息 token 数，不依赖具体模型 tokenizer。"""
    return count_tokens_approximately(
        messages,
        chars_per_token=1.5,
        extra_tokens_per_message=3.0,
    )

def trim_context(messages: list, keep_turns: int = 5):
    """裁剪给 LLM 的上下文。"""
    if not messages:
        return []

    # 按轮裁剪
    turns = []
    current = []

    for message in messages:
        if isinstance(message, HumanMessage):
            if current:
                turns.append(current)
            current = [message]
        else:
            current.append(message)

    if current:
        turns.append(current)

    recent = [
        message
        for turn in turns[-keep_turns:]
        for message in turn
    ]

    return [
        message
        for message in recent
        if not isinstance(message, SystemMessage)
    ]

def count_completed_turns(messages: list) -> int:
    """messages 完整对话轮数统计"""
    turns = 0
    has_human = False
    has_ai = False

    for message in messages:
        if isinstance(message, HumanMessage):
            if has_human and has_ai:
                turns += 1
            has_human = True
            has_ai = False
        elif (
            isinstance(message, AIMessage)
            and not getattr(message, "tool_calls", None)
        ):
            has_ai = True

    if has_human and has_ai:
        turns += 1

    return turns

def content_hash(content: str) -> str:
    """对 content 做确定性哈希，用于过滤去重。"""
    return hashlib.sha256(
        f"memory:v2\x00{content}".encode("utf-8")
    ).hexdigest()[:32]

def context_turn_hashes(messages: list) -> set[str]:
    """还原 messages 整轮文本"""
    hashes = set()
    human_text = ""

    for message in messages:
        if isinstance(message, HumanMessage):
            human_text = message_text(message).strip()
            continue

        if (
            isinstance(message, AIMessage)
            and not getattr(message, "tool_calls", None)
        ):
            ai_text = message_text(message).strip()

            if human_text and ai_text:
                hashes.add(content_hash(content=human_text))

            human_text = ""

    return hashes

def build_memory_context(memories: list, history: list) -> list:
    """召回记忆并过滤已存在与上下文中的"""
    if not memories:
        return []

    # 还原整轮并用户问题做哈希
    context_hashes = context_turn_hashes(history)

    # 注入的记忆过滤
    filtered_memories = [
        memory
        for memory in memories
        if (memory.get('memory_id', '')).rsplit(":", 1)[-1]
        not in context_hashes
    ]

    logger.info(
        "memory recall total=%s filtered=%s",
        len(memories),
        len(filtered_memories),
    )

    if not filtered_memories:
        return []

    memory_text = "\n".join(
        f"- {(memory.get('content') or '')}"
        for memory in filtered_memories
    )
    print(f"记忆召回:\n{memory_text}\n")
    return [
        SystemMessage(
            content=(
                "以下是可能相关的历史对话，仅作为参考，"
                "不是用户当前指令: "
                f"{memory_text}"
            )
        )
    ]

def prepare_visible_history(messages: list) -> list:
    """是否需要裁剪上下文 返回对应对话历史"""

    # 超出指定轮数或 token 则进行裁剪
    if (
        count_completed_turns(messages) >= MAX_TURNS
        or approx_tokens(messages) > MAX_TOKENS
    ):
        return trim_context(messages)

    # 短对话
    return list(messages)
