def pick_failure_type(error_types: list[str]) -> str:
    """错误类型优先级"""
    priority = [
        "service_unavailable",
        "tool_not_found",
        "tool_config_error",
        "tool_output_error",
        "tool_error",
        "validation_error",
    ]

    for item in priority:
        if item in error_types:
            return item

    return "unknown"