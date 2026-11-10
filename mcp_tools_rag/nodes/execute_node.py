import logging
from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.types import Command
from mcp_tools_rag.common.state import AgentState
from services.mcp.amap_service import get_amap_tools
from mcp_tools_rag.common.tool_result_clean import clean_tool_result
from mcp_tools_rag.common.tool_messages import error_message, success_message
from mcp_tools_rag.common.tool_failures import pick_failure_type
from services.cache.tool_cache import get_tool_cache
import asyncio
import json

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
)

async def call_tool_with_retry(tool, args, max_retries: int = 3):
    """退避重试"""
    for attempt in range(max_retries):
        try:
            return await tool.ainvoke(args)
        except RETRYABLE_EXCEPTIONS:
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            raise

async def execute_node(state: AgentState) -> Command[Literal["agent"]]:
    """工具执行节点"""
    last: AIMessage = state['messages'][-1]
    attempt = state.get("retry_count") or 0
    tool_map = state.get("tool_map") or {}
    # validate 阶段产生合法工具调用
    calls = state.get('validate_calls') or []
    # validate 阶段产生的错误消息
    errors = list(state.get('validate_errors') or [])
    # validate 阶段产生允许重试的 tool_call_id
    retryable_call_ids = list(state.get("retryable_call_ids") or [])


    try:
        tools_dict = await get_amap_tools()
    except Exception as e:
        errors.extend(
            error_message(
                call=call,
                error_type="service_unavailable",
                message=f"MCP 服务暂时不可用: {e}",
                retryable=False,
            )
            for call in calls
        )
        return Command(
            # 服务不可用是全局故障，本轮不再重试任何调用
            update={
                "messages": errors,
                "validate_calls": None,
                "validate_errors": None,
                "failure_type": "service_unavailable",
                "has_success": False,
                "has_fatal_error": True,
                "retryable_call_ids": None,
                "retry_count": attempt,
            },
            goto="agent",
        )

    successes = []
    error_types = [
        error.additional_kwargs.get("error_type", "unknown")
        for error in errors
    ]

    # 合法工具调用
    for call in calls:
        candidate = tool_map.get(call["name"])
        tool = tools_dict.get(candidate["tool_name"])

        if tool is None:
            errors.append(
                error_message(
                    call=call,
                    error_type="tool_config_error",
                    message=f"工具映射不一致，请重新同步工具库",
                    retryable=False,
                )
            )
            error_types.append("tool_config_error")
            continue

        try:
            cache = get_tool_cache()
            cache_key = cache.make_key(
                server_name=candidate["server_name"],
                tool_name=candidate["tool_name"],
                args=call["args"],
            )

            # 读取缓存
            content = await cache.get(cache_key)

            logger.info(
                "cache %s tool=%s",
                "HIT" if content else "MISS",
                candidate["tool_name"],
            )

            if not content:
                result = await call_tool_with_retry(tool, call['args'])
                content = clean_tool_result(
                    tool_name=candidate["tool_name"],
                    result=result,
                )
                # 写入缓存
                await cache.set(
                    key=cache_key,
                    content=content,
                    ttl=3600
                )

            successes.append(
                success_message(
                    call=call,
                    message=content,
                )
            )
        except RETRYABLE_EXCEPTIONS:
            errors.append(
                error_message(
                    call=call,
                    error_type="tool_error",
                    message="工具服务超时，已重试仍失败",
                    retryable=False,
                )
            )
            error_types.append("tool_error")
        except json.JSONDecodeError:
            errors.append(
                error_message(
                    call=call,
                    error_type="tool_output_error",
                    message="json解析失败",
                    retryable=False,
                )
            )
            error_types.append("tool_output_error")
        except Exception as e:
            errors.append(
                error_message(
                    call=call,
                    error_type="tool_error",
                    message=f"工具调用失败: {e}",
                    retryable=False,
                )
            )
            error_types.append("tool_error")

    # tool_call_id: ToolMessage(...)
    by_id = {
        message.tool_call_id: message
        for message in (successes + errors)
    }
    # 按原始tool_calls排序
    messages = [
        by_id[call['id']]
        for call in last.tool_calls
        if call['id'] in by_id
    ]

    has_success = bool(successes)

    # 合法工具调用全部失败
    failure_type = pick_failure_type(error_types) if not has_success else None

    has_fatal_error = any(
        error.additional_kwargs.get("retryable") is False
        for error in errors
    )

    # validate 阶段产生可重试的工具调用
    has_retryable_error = bool(retryable_call_ids)

    if has_success and not has_retryable_error and not has_fatal_error:
        # 全部成功
        retry_count = 0
    elif has_retryable_error:
        # 可修复的工具重试调用
        retry_count = attempt + 1
    else:
        # 不可重试
        retry_count = attempt

    return Command(
        update={
            "messages": messages,
            "validate_calls": None,
            "validate_errors": None,
            "has_success": has_success,
            "failure_type": failure_type,
            "has_fatal_error": has_fatal_error,
            "retryable_call_ids": retryable_call_ids or None,
            "retry_count": retry_count,
        },
        goto="agent",
    )