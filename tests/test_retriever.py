"""混合检索 + Reranker 单元测试（mock 向量库，不触发真实 Chroma）。"""
import src.retriever as retriever
import src.config as cfg
from unittest.mock import patch


def _fake_collection(count=4):
    class C:
        def count(self):
            return count

    return C()


def _fake_query_chunks(question, top_k=5, where=None):
    # 两个文件各返回 top_k 个候选
    docs = []
    for i in range(top_k):
        docs.append(
            {
                "id": f"v{i}",
                "text": f"RAG 向量候选 {i} {question}",
                "metadata": {"filename": "a.pdf", "page": 1, "chunk_index": i},
                "distance": float(i) / top_k,
            }
        )
    return docs


def _fake_get_all_chunks(filenames=None):
    return [
        {"id": f"v{i}", "text": f"RAG 向量候选 {i} 检索", "metadata": {}}
        for i in range(4)
    ]


def test_retrieve_hybrid_returns_docs(monkeypatch):
    monkeypatch.setattr(cfg, "HYBRID_SEARCH", True)
    monkeypatch.setattr(cfg, "HYBRID_ALPHA", 0.5)
    monkeypatch.setattr(cfg, "RERANK_ENABLED", False)
    with patch.object(retriever, "query_chunks", _fake_query_chunks), patch.object(
        retriever, "get_all_chunks", _fake_get_all_chunks
    ), patch.object(retriever, "get_collection", lambda: _fake_collection(4)):
        docs = retriever.retrieve("RAG 检索", top_k=3)
    assert len(docs) == 3
    assert all("id" in d for d in docs)


def test_retrieve_rerank_path(monkeypatch):
    monkeypatch.setattr(cfg, "HYBRID_SEARCH", False)
    monkeypatch.setattr(cfg, "RERANK_ENABLED", True)
    monkeypatch.setattr(cfg, "RERANK_TYPE", "lexical")
    monkeypatch.setattr(cfg, "RERANK_TOP_N", 4)
    # 候选中让“RAG 模型 检索”相关且更聚焦的排序靠前
    candidate = [
        {"id": "x1", "text": "无关美食内容", "metadata": {"filename": "a.pdf", "page": 1, "chunk_index": 0}},
        {"id": "x2", "text": "RAG 模型 检索 架构", "metadata": {"filename": "a.pdf", "page": 1, "chunk_index": 1}},
        {"id": "x3", "text": "RAG 模型 检索", "metadata": {"filename": "a.pdf", "page": 1, "chunk_index": 2}},
    ]

    def fake_query(question, top_k=5, where=None):
        return candidate

    with patch.object(retriever, "query_chunks", fake_query):
        docs = retriever.retrieve("RAG 模型 检索", top_k=2)
    assert docs[0]["id"] == "x3"


def test_retrieve_pure_vector_when_disabled(monkeypatch):
    monkeypatch.setattr(cfg, "HYBRID_SEARCH", False)
    monkeypatch.setattr(cfg, "RERANK_ENABLED", False)
    with patch.object(retriever, "query_chunks", _fake_query_chunks):
        docs = retriever.retrieve("RAG 检索", top_k=2)
    assert len(docs) == 2
    assert all(d["id"].startswith("v") for d in docs)
