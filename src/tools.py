"""Agent 工具：返回结构化 Observation，不在检索工具中直接生成答案。"""
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from src.rag_chain import rag_answer
from src.retriever import read_documents, retrieve
from src.vectorstore import get_document_info, list_knowledge_base_documents


def _available_names() -> List[str]:
    return [item["filename"] for item in list_knowledge_base_documents()]


def resolve_filenames(requested: Optional[Iterable[str]]) -> Dict[str, Any]:
    """将模型给出的名称解析为知识库中的精确文件名。"""
    available = _available_names()
    requested_names = [str(item).strip() for item in (requested or []) if str(item).strip()]

    if not requested_names:
        return {"resolved": [], "unresolved": [], "available": available}

    resolved: List[str] = []
    unresolved: List[str] = []

    for name in requested_names:
        if name in available:
            resolved.append(name)
            continue

        case_matches = [item for item in available if item.lower() == name.lower()]
        if len(case_matches) == 1:
            resolved.append(case_matches[0])
            continue

        partial_matches = [
            item for item in available
            if name.lower() in item.lower() or item.lower() in name.lower()
        ]
        if len(partial_matches) == 1:
            resolved.append(partial_matches[0])
        else:
            unresolved.append(name)

    return {
        "resolved": list(dict.fromkeys(resolved)),
        "unresolved": unresolved,
        "available": available,
    }


def retrieve_tool(
    query: str,
    filenames: Optional[Iterable[str]] = None,
    mode: str = "semantic",
    top_k: int = 5,
    max_chunks_per_file: int = 40,
    use_rewrite: bool = True,
) -> Dict[str, Any]:
    """
    原始检索工具。

    只返回 chunks、metadata 和距离，不调用最终回答模型。
    """
    resolution = resolve_filenames(filenames)
    if resolution["unresolved"]:
        return {
            "ok": False,
            "tool": "retrieve_documents",
            "error": f"无法唯一匹配文件：{resolution['unresolved']}",
            "available_documents": resolution["available"],
            "documents": [],
        }

    resolved = resolution["resolved"]
    if mode == "full_document":
        if not resolved:
            return {
                "ok": False,
                "tool": "retrieve_documents",
                "error": "full_document 模式必须指定至少一个文件名。",
                "available_documents": resolution["available"],
                "documents": [],
            }
        documents = read_documents(
            filenames=resolved,
            max_chunks_per_file=max(1, min(int(max_chunks_per_file), 100)),
        )
    else:
        documents = retrieve(
            question=query,
            top_k=max(1, min(int(top_k), 20)),
            use_rewrite=bool(use_rewrite),
            filenames=resolved or None,
        )

    return {
        "ok": True,
        "tool": "retrieve_documents",
        "query": query,
        "mode": mode,
        "filenames": resolved,
        "document_count": len(documents),
        "documents": documents,
    }


def list_documents_tool() -> Dict[str, Any]:
    documents = list_knowledge_base_documents()
    return {
        "ok": True,
        "tool": "list_documents",
        "documents": documents,
        "document_count": len(documents),
        "chunk_count": sum(item["chunk_count"] for item in documents),
    }


def document_info_tool(filenames: Iterable[str]) -> Dict[str, Any]:
    resolution = resolve_filenames(filenames)
    infos = [
        get_document_info(filename)
        for filename in resolution["resolved"]
    ]
    return {
        "ok": not resolution["unresolved"],
        "tool": "document_info",
        "documents": [item for item in infos if item],
        "unresolved": resolution["unresolved"],
        "available_documents": resolution["available"],
    }


def _build_pending_operation(operation_type: str, filenames: Iterable[str]) -> Dict[str, Any]:
    resolution = resolve_filenames(filenames)
    if resolution["unresolved"] or not resolution["resolved"]:
        return {
            "ok": False,
            "tool": f"request_{operation_type}_documents",
            "error": "文件名不存在或无法唯一匹配。",
            "unresolved": resolution["unresolved"],
            "available_documents": resolution["available"],
        }

    action_name = "删除" if operation_type == "delete" else "重建"
    operation_id = uuid4().hex
    return {
        "ok": True,
        "tool": f"request_{operation_type}_documents",
        "pending_operation": {
            "operation_id": operation_id,
            "type": operation_type,
            "filenames": resolution["resolved"],
            "confirmation_phrase": f"确认{action_name}",
        },
        "message": (
            f"已准备{action_name}操作，但尚未执行。"
            "请在界面中完成二次确认。"
        ),
    }


def request_delete_documents_tool(filenames: Iterable[str]) -> Dict[str, Any]:
    """只生成待确认删除操作，不直接修改数据库。"""
    return _build_pending_operation("delete", filenames)


def request_rebuild_documents_tool(filenames: Iterable[str]) -> Dict[str, Any]:
    """只生成待确认重建操作，不直接修改数据库。"""
    return _build_pending_operation("rebuild", filenames)


# 以下接口保留给旧代码使用。
def rag_qa_tool(question: str, filename: Optional[str] = None) -> str:
    where = {"filename": filename} if filename else None
    return rag_answer(question=question, top_k=5, use_rewrite=True, where=where)


def summary_tool(question: str, filename: Optional[str] = None) -> str:
    where = {"filename": filename} if filename else None
    return rag_answer(question=question, top_k=8, use_rewrite=True, where=where)


def compare_tool(question: str) -> str:
    return rag_answer(question=question, top_k=10, use_rewrite=True)


def interview_tool(question: str, filename: Optional[str] = None) -> str:
    where = {"filename": filename} if filename else None
    return rag_answer(question=question, top_k=8, use_rewrite=True, where=where)
