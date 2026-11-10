import logging

from langchain_core.messages import AIMessage, ToolMessage
from mcp_tools_rag.common.tool_messages import error_message
from mcp_tools_rag.common.tool_failures import pick_failure_type
from langgraph.types import Command
from mcp_tools_rag.common.state import AgentState
from jsonschema import SchemaError
from typing import Literal
import jsonschema

logger = logging.getLogger(__name__)


async def validate_node(state: AgentState) -> Command[Literal['agent', 'tools']]:
    """工具校验前置节点"""
    last: AIMessage = state['messages'][-1]
    attempt = state.get('retry_count', 0)
    tool_map = state.get('tool_map') or {}

    errors: list[ToolMessage] = []
    valid_calls = []
    error_types = []
    # 参数错误允许重试的 tool_call_id
    retryable_call_ids: list[str] = []

    for call in last.tool_calls:
        candidate = tool_map.get(call['name'])
        # 工具不存在
        if candidate is None:
            errors.append(
                error_message(
                    call=call,
                    error_type="tool_not_found",
                    message=(
                        f"工具 {call['name']} 不在当前可用列表中，"
                        "只能从已绑定工具里选择，不要编造工具名。"
                    ),
                    retryable=True,
                )
            )
            error_types.append("tool_not_found")
            retryable_call_ids.append(call["id"])
            continue

        # 参数schema校验
        try:
            jsonschema.validate(call['args'], candidate['schema'])
        except jsonschema.ValidationError as e:
            errors.append(
                error_message(
                    call=call,
                    error_type="validation_error",
                    message=f"参数不合法: {e}",
                    retryable=True,
                )
            )
            error_types.append("validation_error")
            retryable_call_ids.append(call["id"])
            continue
        except SchemaError as e:
            errors.append(
                error_message(
                    call=call,
                    error_type="tool_config_error",
                    message=f"工具配置异常: {e}",
                    retryable=False,
                )
            )
            error_types.append("tool_config_error")
            continue
        # 合法工具
        valid_calls.append(call)

    # 全挂了
    if not valid_calls:
        # 错误优先级
        failure_type = pick_failure_type(error_types)

        return Command(
            update={
                "messages": errors,
                "validate_calls": None,
                "validate_errors": None,
                "failure_type": failure_type,
                "has_success": False,
                "has_fatal_error": any(
                    e.additional_kwargs.get("retryable") is False
                    for e in errors
                ),
                # 可修复的参数错误允许重试
                "retryable_call_ids": retryable_call_ids or None,
                "retry_count": attempt + 1 if retryable_call_ids else 0,
            },
            goto="agent",
        )

    logger.info(
        "validate valid=%s errors=%s retryable=%s",
        len(valid_calls),
        len(errors),
        len(retryable_call_ids),
    )

    # 合法调用
    return Command(
        update={
            "validate_calls": valid_calls,
            "validate_errors": errors,
            "retryable_call_ids": retryable_call_ids or None,
            "has_fatal_error": any(
                e.additional_kwargs.get("retryable") is False
                for e in errors
            ),
        },
        goto="tools"
    )

