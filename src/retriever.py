"""检索层：Query Rewrite、文件过滤、全文读取和结果去重。"""
from typing import Any, Dict, Iterable, List, Optional

from src.llm import chat_completion
from src.prompts import QUERY_REWRITE_PROMPT
from src.vectorstore import get_document_chunks, query_chunks


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


def deduplicate_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据 filename + page + chunk_index 去重。"""
    seen = set()
    unique_docs = []

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


def retrieve(
    question: str,
    top_k: int = 5,
    use_rewrite: bool = True,
    filenames: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """
    语义检索。

    filenames 为空：在全知识库检索 top_k 个。
    filenames 非空：每个指定文件分别检索 top_k 个，确保对比任务中各文件都有证据。
    """
    search_query = rewrite_query(question) if use_rewrite else question
    normalized = [str(name) for name in dict.fromkeys(filenames or []) if name]

    if not normalized:
        return deduplicate_docs(
            query_chunks(question=search_query, top_k=top_k)
        )

    all_docs: List[Dict[str, Any]] = []
    for filename in normalized:
        all_docs.extend(
            query_chunks(
                question=search_query,
                top_k=top_k,
                where={"filename": filename},
            )
        )

    return deduplicate_docs(all_docs)


def read_documents(
    filenames: Iterable[str],
    max_chunks_per_file: int = 40,
) -> List[Dict[str, Any]]:
    """按文件读取原始 chunks，适合整篇总结或整体对比。"""
    all_docs: List[Dict[str, Any]] = []
    for filename in dict.fromkeys(filenames):
        all_docs.extend(
            get_document_chunks(
                filename=str(filename),
                limit=max_chunks_per_file,
            )
        )
    return deduplicate_docs(all_docs)
