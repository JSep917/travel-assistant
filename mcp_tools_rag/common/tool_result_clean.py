import json
from typing import Any


PAYLOAD_KEYS = {
    "pois", "geocodes", "route",
    "lives", "results", "return",
}

KEEP_FIELDS = {
    "id", "poi_id", "name", "poi_name",
    "title", "address", "addr", "location",
    "lonlat", "origin", "destination", "distance",
    "duration", "city", "citycode", "district",
    "province", "adcode", "street", "typecode",
    "type", "level", "count", "status", "info",
    "cost", "rating", "opentime2", "open_time"
    "tel", "business_area"
}


def _empty_result(tool_name: str, message: str) -> dict:
    return {
        "tool": tool_name,
        "items": [],
        "count": 0,
        "message": message,
    }

def unwrap_mcp_result(value: Any, depth: int = 0) -> Any:
    """解包 MCP content blocks、JSON 字符串和常见包装层。"""
    if depth > 4:
        return value

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return value

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return value

        return unwrap_mcp_result(parsed, depth + 1)

    if isinstance(value, list):
        # MCP text content blocks
        if value and isinstance(value[0], dict) and "text" in value[0]:
            text = "\n".join(
                block.get("text", "")
                for block in value
                if isinstance(block, dict)
            )
            return unwrap_mcp_result(text, depth + 1)

        return value

    if isinstance(value, dict):
        # 当前层已经有 payload，不要再往下拆
        if any(key in value for key in PAYLOAD_KEYS):
            return value

        for key in ("content", "data", "result", "return"):
            if key in value:
                return unwrap_mcp_result(value[key], depth + 1)

    return value


def find_payload(data: Any) -> tuple[str | None, Any]:
    """递归查找 pois/geocodes/route/lives/results 等 payload。"""
    if isinstance(data, dict):
        for key in PAYLOAD_KEYS:
            if key in data:
                return key, data[key]

        for value in data.values():
            found_key, found_value = find_payload(value)
            if found_key is not None:
                return found_key, found_value

    elif isinstance(data, list):
        for item in data:
            found_key, found_value = find_payload(item)
            if found_key is not None:
                return found_key, found_value

    return None, None


def _clean_value(value: Any, depth: int = 0) -> Any:
    """通用投影：保留关键字段，限制深度、数组长度和字符串长度。"""
    if depth > 4:
        return None

    if isinstance(value, str):
        return value[:300]

    if isinstance(value, list):
        return [
            cleaned
            for item in value[:8]
            if (cleaned := _clean_value(item, depth + 1)) is not None
        ]

    if isinstance(value, dict):
        result = {}

        for key, val in value.items():
            if key in KEEP_FIELDS and val is not None:
                cleaned = _clean_value(val, depth + 1)
                if cleaned not in (None, "", [], {}):
                    result[key] = cleaned

        # 如果没有命中已知字段，保留少量短标量
        if not result:
            for key, val in list(value.items())[:5]:
                if isinstance(val, (str, int, float, bool)):
                    cleaned = _clean_value(val, depth + 1)
                    if cleaned not in (None, ""):
                        result[key] = cleaned

        return result or None

    return value


def clean_tool_result(tool_name: str, result: Any) -> str:
    """通用 MCP 工具结果清洗。

    返回 JSON 字符串；空结果返回结构化 no-result。
    """
    data = unwrap_mcp_result(result)

    if data is None or data == "" or data == [] or data == {}:
        return json.dumps(
            _empty_result(tool_name, "工具返回为空"),
            ensure_ascii=False,
        )

    payload_key, payload = find_payload(data)

    if payload_key is not None:
        # route 常把 distance/duration 放在 paths[0] 里
        if (
            payload_key == "route"
            and isinstance(payload, dict)
            and isinstance(payload.get("paths"), list)
            and payload["paths"]
        ):
            first_path = payload["paths"][0]
            if isinstance(first_path, dict):
                payload = {
                    **payload,
                    "distance": first_path.get("distance"),
                    "duration": first_path.get("duration"),
                }

        cleaned = _clean_value(payload)

        if cleaned in (None, "", [], {}):
            return json.dumps(
                _empty_result(tool_name, "未找到有效数据"),
                ensure_ascii=False,
            )

        count = len(payload) if isinstance(payload, list) else 1

        output = {
            "tool": tool_name,
            "payload_key": payload_key,
            "count": count,
        }

        if isinstance(cleaned, list):
            output["items"] = cleaned
        else:
            output["data"] = cleaned

        return json.dumps(output, ensure_ascii=False)

    # 没有已知 payload，整体投影
    cleaned = _clean_value(data)

    if cleaned in (None, "", [], {}):
        return json.dumps(
            _empty_result(tool_name, "未找到有效数据"),
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "tool": tool_name,
            "data": cleaned,
        },
        ensure_ascii=False,
    )

