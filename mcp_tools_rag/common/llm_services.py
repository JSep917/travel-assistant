from functools import cache
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from config import settings

@cache
def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.2
    )

@cache
def get_analyze_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0
    )


@cache
def get_memory_llm() -> ChatOpenAI:
    """记忆卡片抽取轻量模型。"""
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0
    )


@cache
def get_profile_llm() -> ChatOpenAI:
    """用户画像抽取使用轻量模型。"""
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0
    )
