"""项目公共工具函数。"""
from typing import Any, Dict, Iterable, List


def deduplicate_docs(docs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据 (filename, page, chunk_index) 对文档块去重。

    原本分别存在于 retriever.py 的 deduplicate_docs 与
    rag_chain.py 的 deduplicate_evidence，现已统一到此处作为唯一实现。
    """
    seen: set = set()
    unique_docs: List[Dict[str, Any]] = []

    for doc in docs:
        metadata = doc.get("metadata", {})
        key = (
            metadata.get("filename"),
            metadata.get("page"),
            metadata.get("chunk_index"),
        )
        if key not in seen:
            seen.add(key)
            unique_docs.append(doc)
    return unique_docs
