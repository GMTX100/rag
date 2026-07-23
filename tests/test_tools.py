"""工具层测试：文件名解析与 retrieve_tool 行为（mock 掉 Chroma / LLM）。"""
import src.tools as tools_mod
from unittest.mock import patch

from src.tools import resolve_filenames, retrieve_tool

AVAILABLE = [
    {"filename": "rag基础.pdf", "page_count": 10, "chunk_count": 100},
    {"filename": "深度学习报告.pdf", "page_count": 5, "chunk_count": 50},
]


def test_resolve_exact(monkeypatch):
    monkeypatch.setattr(tools_mod, "list_knowledge_base_documents", lambda: AVAILABLE)
    res = resolve_filenames(["rag基础.pdf"])
    assert res["resolved"] == ["rag基础.pdf"]
    assert res["unresolved"] == []


def test_resolve_case_insensitive(monkeypatch):
    monkeypatch.setattr(tools_mod, "list_knowledge_base_documents", lambda: AVAILABLE)
    res = resolve_filenames(["RAG基础.PDF"])
    assert res["resolved"] == ["rag基础.pdf"]


def test_resolve_partial_single(monkeypatch):
    monkeypatch.setattr(tools_mod, "list_knowledge_base_documents", lambda: AVAILABLE)
    res = resolve_filenames(["深度学习"])
    assert res["resolved"] == ["深度学习报告.pdf"]


def test_resolve_partial_ambiguous_is_unresolved(monkeypatch):
    # “pdf”同时命中两个文件 → 不唯一 → 进入 unresolved
    monkeypatch.setattr(tools_mod, "list_knowledge_base_documents", lambda: AVAILABLE)
    res = resolve_filenames(["pdf"])
    assert res["resolved"] == []
    assert res["unresolved"] == ["pdf"]


def test_resolve_empty(monkeypatch):
    monkeypatch.setattr(tools_mod, "list_knowledge_base_documents", lambda: AVAILABLE)
    res = resolve_filenames([])
    assert res["resolved"] == []


def test_retrieve_tool_semantic_ok(monkeypatch):
    monkeypatch.setattr(tools_mod, "list_knowledge_base_documents", lambda: AVAILABLE)
    monkeypatch.setattr(tools_mod, "retrieve", lambda **kw: [{"text": "sem", "metadata": {}}])
    monkeypatch.setattr(tools_mod, "read_documents", lambda **kw: [{"text": "full", "metadata": {}}])
    out = retrieve_tool(query="什么是 RAG", mode="semantic", top_k=5)
    assert out["ok"] is True
    assert out["document_count"] == 1
    assert out["mode"] == "semantic"


def test_retrieve_tool_unresolved_returns_error(monkeypatch):
    monkeypatch.setattr(tools_mod, "list_knowledge_base_documents", lambda: AVAILABLE)
    monkeypatch.setattr(tools_mod, "retrieve", lambda **kw: [])
    out = retrieve_tool(query="x", filenames=["不存在.pdf"])
    assert out["ok"] is False
    assert "无法唯一匹配" in out["error"]
