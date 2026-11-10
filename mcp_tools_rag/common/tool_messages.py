import json
from langchain_core.messages import ToolMessage


def error_message(
    call,
    error_type: str,
    message: str,
    retryable: bool,
) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(
            {
                "ok": False,
                "error_type": error_type,
                "retryable": retryable,
                "message": message,
            },
            ensure_ascii=False,
        ),
        tool_call_id=call["id"],
        name=call["name"],
        status="error",
        additional_kwargs={
            "error_type": error_type,
            "retryable": retryable,
        },
    )


def success_message(call, message: str) -> ToolMessage:
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        payload = {"message": message}

    if isinstance(payload, dict):
        payload = {"ok": True, **payload}
    else:
        payload = {"ok": True, "data": payload}

    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id=call["id"],
        name=call["name"],
        status="success",
    )