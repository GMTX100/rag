"""检索层：Query Rewrite、文件过滤、混合检索、Reranker 与结果去重。

中期增强：
- 混合检索（Hybrid Search）：BM25 词法检索与向量语义检索，通过倒数排名融合
  （RRF）结合，兼顾关键词精确匹配与语义召回。
- Reranker：在取得候选后做重排序（默认零依赖词法重排，可选 Cross-Encoder）。
"""
from typing import Any, Dict, Iterable, List, Optional

import src.config as cfg
from src.llm import chat_completion
from src.prompts import QUERY_REWRITE_PROMPT
from src.reranker import get_reranker, tokenize
from src.utils import deduplicate_docs
from src.vectorstore import get_all_chunks, get_collection, get_document_chunks, query_chunks

# BM25 索引缓存：collection 数量变化即失效重建。
_bm25_cache: Dict[str, Any] = {"count": None, "index": None, "ids": None}


def _build_bm25(filenames: Optional[Iterable[str]] = None):
    """构建（或复用缓存的）BM25 索引；filenames 限定词表范围。"""
    from rank_bm25 import BM25Okapi

    collection = get_collection()
    current_count = collection.count()
    if (
        _bm25_cache["count"] == current_count
        and _bm25_cache["index"] is not None
        and filenames is None
    ):
        return _bm25_cache["index"], _bm25_cache["ids"]

    chunks = get_all_chunks(filenames=filenames)
    if not chunks:
        return None, None

    corpus = [tokenize(c["text"]) for c in chunks]
    index = BM25Okapi(corpus)
    if filenames is None:
        _bm25_cache.update(
            {"count": current_count, "index": index, "ids": [c["id"] for c in chunks]}
        )
    return index, [c["id"] for c in chunks]


def rewrite_query(question: str) -> str:
    """将用户问题改写为更适合向量检索的完整问题。"""
    user_prompt = f"""
用户原始问题：
{question}

请输出改写后的检索问题。
"""
    rewritten = chat_completion(
        system_prompt=QUERY_REWRITE_PROMPT,
        user_prompt=user_prompt,
        temperature=0.0,
    )
    return rewritten.strip()


def _vector_query(
    question: str,
    top_k: int,
    filenames: Optional[List[str]],
) -> List[Dict[str, Any]]:
    if not filenames:
        return deduplicate_docs(query_chunks(question=question, top_k=top_k))
    all_docs: List[Dict[str, Any]] = []
    for filename in filenames:
        all_docs.extend(
            query_chunks(question=question, top_k=top_k, where={"filename": filename})
        )
    return deduplicate_docs(all_docs)


def _bm25_top_ids(query: str, k: int, ids: List[str], index) -> Dict[str, int]:
    """对候选 ids 计算 BM25 得分并返回 {id: 排名}，排名越小越好。"""
    scores = index.get_scores(tokenize(query))
    id_to_score = {cid: float(s) for cid, s in zip(ids, scores)}
    ranked = sorted(id_to_score.items(), key=lambda x: x[1], reverse=True)
    return {cid: rank + 1 for rank, (cid, _) in enumerate(ranked[:k])}


def _rerank_fuse(
    question: str,
    vector_docs: List[Dict[str, Any]],
    filenames: Optional[List[str]],
    pool: int,
    alpha: float,
) -> List[Dict[str, Any]]:
    """用 RRF 融合向量排名与 BM25 排名，返回融合后的候选文档。"""
    # 候选并集：向量返回 pool 个 + BM25 返回 pool 个。
    vector_ids = {d["id"]: i + 1 for i, d in enumerate(vector_docs[:pool])}
    vector_map = {d["id"]: d for d in vector_docs}

    index, bm25_ids = _build_bm25(filenames=filenames)
    bm25_ranks: Dict[str, int] = {}
    if index is not None and bm25_ids:
        bm25_ranks = _bm25_top_ids(query=question, k=pool, ids=bm25_ids, index=index)

    candidate_ids = set(vector_ids) | set(bm25_ranks)
    rrf_k = 60

    fused: List[Dict[str, Any]] = []
    for cid in candidate_ids:
        score = 0.0
        if cid in vector_ids:
            score += (1 - alpha) * (1.0 / (rrf_k + vector_ids[cid]))
        if cid in bm25_ranks:
            score += alpha * (1.0 / (rrf_k + bm25_ranks[cid]))
        doc = vector_map.get(cid)
        if doc is not None:
            fused.append((score, doc))
    fused.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in fused]


def retrieve(
    question: str,
    top_k: int = 5,
    use_rewrite: bool = True,
    filenames: Optional[Iterable[str]] = None,
    use_hybrid: Optional[bool] = None,
    hybrid_alpha: Optional[float] = None,
    use_rerank: Optional[bool] = None,
    rerank_top_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """统一检索入口。

    use_hybrid / hybrid_alpha / use_rerank / rerank_top_n 为 None 时读取 config 全局开关。
    """
    use_hybrid = cfg.HYBRID_SEARCH if use_hybrid is None else use_hybrid
    hybrid_alpha = cfg.HYBRID_ALPHA if hybrid_alpha is None else hybrid_alpha
    use_rerank = cfg.RERANK_ENABLED if use_rerank is None else use_rerank
    rerank_top_n = cfg.RERANK_TOP_N if rerank_top_n is None else rerank_top_n

    search_query = rewrite_query(question) if use_rewrite else question
    normalized = [str(name) for name in dict.fromkeys(filenames or []) if name]

    # 候选池：重排序需要更大的候选集，否则取 top_k 即可。
    pool = max(top_k, rerank_top_n) if use_rerank else top_k

    if use_hybrid:
        vector_docs = _vector_query(search_query, pool, normalized or None)
        docs = _rerank_fuse(
            question=search_query,
            vector_docs=vector_docs,
            filenames=normalized or None,
            pool=pool,
            alpha=hybrid_alpha,
        )
    else:
        docs = _vector_query(search_query, pool, normalized or None)

    docs = deduplicate_docs(docs)

    if use_rerank:
        reranker = get_reranker(cfg.RERANK_TYPE)
        docs = reranker.rerank(search_query, docs, top_n=min(rerank_top_n, pool))

    return docs[:top_k]


def read_documents(
    filenames: Iterable[str],
    max_chunks_per_file: int = 40,
) -> List[Dict[str, Any]]:
    """按文件读取原始 chunks（按页码/chunk 排序），适合整篇总结或整体对比。"""
    all_docs: List[Dict[str, Any]] = []
    for filename in dict.fromkeys(filenames):
        all_docs.extend(
            get_document_chunks(
                filename=str(filename),
                limit=max(1, min(int(max_chunks_per_file), 100)),
            )
        )
    return deduplicate_docs(all_docs)
