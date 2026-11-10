from sentence_transformers import CrossEncoder

reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")


def rerank_tools(query, candidates, top_n=8):
    pairs = [
        (query, candidate.get("search_text"))
        for candidate in candidates
    ]
    scores = reranker.predict(pairs)

    ranked = sorted(
        zip(candidates, scores),
        key=lambda item: item[1],
        reverse=True,
    )[:top_n]

    return [
        {**candidate, "rerank_score": float(score)}
        for candidate, score in ranked
    ]