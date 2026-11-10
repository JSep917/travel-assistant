import logging
from http import HTTPStatus
import dashscope
from config import settings

logger = logging.getLogger(__name__)


def rerank_tools(
    query: str,
    candidates: list[dict],
    top_n: int = 5,
) -> list[dict]:
    """对 RRF 召回的候选工具做精排。"""
    if not candidates:
        return []

    documents = [
        candidate.get("search_text")
        for candidate in candidates
    ]

    try:
        resp = dashscope.TextReRank.call(
            model=settings.RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
            return_documents=False,
            api_key=settings.DASHSCOPE_API_KEY,
        )
    except Exception:
        logger.exception("rerank request failed, fallback to RRF order")
        return candidates[:top_n]

    if resp.status_code != HTTPStatus.OK:
        logger.error(
            "rerank failed status=%s message=%s",
            resp.status_code,
            getattr(resp, "message", ""),
        )
        return candidates[:top_n]

    results = resp.output.results

    return [
        {
            **candidates[item.index],
            "rerank_score": float(item.relevance_score),
        }
        for item in results
    ]


def rerank_memories(
    query: str,
    memories: list[dict],
    top_n: int = 5,
) -> list[dict]:
    if not memories:
        return []

    documents = [
        memory.get("search_text")[:1000]
        for memory in memories
    ]

    resp = dashscope.TextReRank.call(
        model=settings.RERANK_MODEL,
        query=query,
        documents=documents,
        top_n=min(top_n, len(documents)),
        return_documents=False,
        api_key=settings.DASHSCOPE_API_KEY,
    )

    return [
        {
            **memories[item.index],
            "rerank_score": float(item.relevance_score),
        }
        for item in resp.output.results
    ]

def filter_by_relative_score(
    items: list[dict],
    ratio: float,
    min_score: float,
    limit: int,
    key: str = "rerank_score",
) -> list[dict]:
    """相对阈值过滤"""
    if not items:
        return []

    best = max(item.get(key, 0) for item in items)
    threshold = max(best * ratio, min_score)

    filtered = [
        item
        for item in items
        if item.get(key, 0) >= threshold
    ]

    filtered.sort(
        key=lambda item: item.get(key, 0),
        reverse=True,
    )

    return filtered[:limit]