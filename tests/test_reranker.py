"""Reranker 单元测试（零依赖词法重排 + 工厂回退，无需网络）。"""
from src.reranker import LexicalReranker, get_reranker, tokenize


def test_tokenize_mixed_chinese_english():
    toks = tokenize("RAG 模型 performance")
    assert "rag" in toks
    assert "performance" in toks
    # 中文按单字切分
    assert "模" in toks and "型" in toks


def test_lexical_reranker_orders_by_overlap():
    reranker = LexicalReranker()
    docs = [
        {"id": "a", "text": "完全无关的内容关于美食"},
        {"id": "b", "text": "RAG 检索增强生成 模型 架构"},
        {"id": "c", "text": "RAG 模型 检索"},
    ]
    ranked = reranker.rerank("RAG 模型 检索", docs)
    assert ranked[0]["id"] == "c"  # 完全命中
    assert ranked[-1]["id"] == "a"  # 无重叠


def test_lexical_reranker_respects_top_n():
    reranker = LexicalReranker()
    docs = [{"id": str(i), "text": f"RAG 模型 关键词{i}"} for i in range(10)]
    ranked = reranker.rerank("RAG 模型", docs, top_n=3)
    assert len(ranked) == 3


def test_get_reranker_auto_falls_back_without_sentence_transformers(monkeypatch):
    # 确保 sentence_transformers 不可见 → auto 回退到 LexicalReranker
    import sys

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    reranker = get_reranker("auto")
    assert isinstance(reranker, LexicalReranker)


def test_get_reranker_lexical_is_lexical():
    assert isinstance(get_reranker("lexical"), LexicalReranker)
