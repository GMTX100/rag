"""去重工具测试（不依赖 API / Chroma）。"""
from src.utils import deduplicate_docs


def _doc(filename, page, chunk_index, text="x"):
    return {
        "text": text,
        "metadata": {"filename": filename, "page": page, "chunk_index": chunk_index},
    }


def test_deduplicate_removes_exact_triple():
    docs = [
        _doc("A.pdf", 1, 0),
        _doc("A.pdf", 1, 0),  # 重复
        _doc("A.pdf", 1, 1),
    ]
    result = deduplicate_docs(docs)
    assert len(result) == 2
    assert result[0]["metadata"]["chunk_index"] == 0
    assert result[1]["metadata"]["chunk_index"] == 1


def test_deduplicate_keeps_different_keys():
    docs = [
        _doc("A.pdf", 1, 0),
        _doc("B.pdf", 1, 0),
        _doc("A.pdf", 2, 0),
    ]
    result = deduplicate_docs(docs)
    assert len(result) == 3


def test_deduplicate_empty():
    assert deduplicate_docs([]) == []
