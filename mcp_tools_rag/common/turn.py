from langgraph.types import Command
from langchain_core.messages import AIMessage

def end_turn(content: str, skip_memory: bool = False) -> Command:
    """一轮结束"""

    additional_kwargs = {'skip_memory': True if skip_memory else False}

    return Command(
        # 清空本轮临时状态
        update={
            "messages": [AIMessage(
                content=content,
                additional_kwargs=additional_kwargs
            )],
            "rewrite_query": None,
            "to_candidates": None,
            "tool_map": None,
            "validate_calls": None,
            "validate_errors": None,
            "failure_type": None,
            "has_success": False,
            "has_fatal_error": False,
            "retryable_call_ids": None,
            "memories": None,
            "retry_count": 0,
        },
        goto="__end__",
    )