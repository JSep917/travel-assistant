from langchain_core.messages import HumanMessage, AIMessage
import re

GREETINGS = {
    "你好", "您好", "hi", "hello", "在吗",
    "谢谢", "好的", "嗯", "知道了",
}

def message_text(message) -> str:
    """单条消息转纯文本带清洗"""
    content = message.content

    if isinstance(content, str):
        text = content
    # 多模态
    elif isinstance(content, list):
        text = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict)
        )
    else:
        text = str(content or "")

    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def is_meaningful(text: str) -> bool:
    text = text.strip()

    if len(text) < 6:
        return False

    if text in GREETINGS:
        return False

    return True

def build_title(messages: list) -> str:
    """构建 threads 会话 title"""
    human_texts = [
        text
        for m in messages
        if isinstance(m, HumanMessage)
        if (text := message_text(m))
    ]

    if not human_texts:
        return "新会话"

    meaningful = [t for t in human_texts if is_meaningful(t)]

    if not meaningful:
        return "新会话"

    title = meaningful[0]

    # 去掉开头问候
    title = re.sub(
        r"^(你好|您好|嗨|hi|hello)[，,。.!！\s]*",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    return title[:30] or "新会话"

def build_preview(messages: list) -> str:
    """构建 threads 会话 last_message_preview"""
    for message in reversed(messages):
        if (
            isinstance(message, AIMessage)
            and not getattr(message, "tool_calls", None)
        ):
            text = message_text(message)
            if text:
                return text[:100]
    # 兜底最后一条用户消息
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = message_text(message)
            if text:
                return text[:100]

    return ""