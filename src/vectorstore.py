"""Chroma 向量数据库：初始化、写入、检索及文档级管理。"""
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

import chromadb
from chromadb.config import Settings

from src.config import CHROMA_DIR, COLLECTION_NAME


_client = None
_collection = None


def get_chroma_client():
    """获取全局 Chroma 持久化客户端。"""
    global _client

    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

    return _client


def get_collection():
    """获取或创建当前知识库集合。"""
    global _collection

    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "DocuMind RAG collection"},
        )

    return _collection


def add_chunks(chunks: List[Dict[str, Any]]) -> int:
    """将文本块写入知识库，返回写入数量。"""
    if not chunks:
        return 0

    collection = get_collection()
    collection.add(
        ids=[item["id"] for item in chunks],
        documents=[item["text"] for item in chunks],
        metadatas=[item["metadata"] for item in chunks],
    )
    return len(chunks)


def query_chunks(
    question: str,
    top_k: int = 5,
    where: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """相似度查询；where 可用于 filename 等 metadata 过滤。"""
    collection = get_collection()
    total = collection.count()

    if total == 0:
        return []

    query_kwargs: Dict[str, Any] = {
        "query_texts": [question],
        "n_results": min(max(1, top_k), total),
    }
    if where:
        query_kwargs["where"] = where

    result = collection.query(**query_kwargs)
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    ids = result.get("ids", [[]])[0]

    retrieved = []
    for item_id, doc, meta, distance in zip(ids, docs, metas, distances):
        retrieved.append(
            {
                "id": item_id,
                "text": doc,
                "metadata": meta or {},
                "distance": float(distance),
            }
        )
    return retrieved


def get_document_chunks(
    filename: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """读取某个文件的原始 chunks，并按页码、chunk_index 排序。"""
    collection = get_collection()
    if collection.count() == 0:
        return []

    result = collection.get(
        where={"filename": filename},
        include=["documents", "metadatas"],
    )
    ids = result.get("ids") or []
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    items = []
    for item_id, text, metadata in zip(ids, documents, metadatas):
        items.append(
            {
                "id": item_id,
                "text": text,
                "metadata": metadata or {},
                # 全文读取不是相似度查询，因此没有真实 distance。
                "distance": None,
            }
        )

    def sort_key(item: Dict[str, Any]):
        metadata = item.get("metadata", {})
        page = metadata.get("page", 0)
        chunk_index = metadata.get("chunk_index", 0)
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 0
        try:
            chunk_index = int(chunk_index)
        except (TypeError, ValueError):
            chunk_index = 0
        return page, chunk_index

    items.sort(key=sort_key)
    if limit is not None:
        return items[: max(0, limit)]
    return items


def list_knowledge_base_documents() -> List[Dict[str, Any]]:
    """汇总知识库文件名、chunk 数与页数。"""
    collection = get_collection()
    if collection.count() == 0:
        return []

    result = collection.get(include=["metadatas"])
    metadatas = result.get("metadatas") or []
    stats = defaultdict(lambda: {"chunk_count": 0, "pages": set()})

    for metadata in metadatas:
        metadata = metadata or {}
        filename = str(metadata.get("filename") or "未知文件")
        stats[filename]["chunk_count"] += 1
        page = metadata.get("page")
        if page is not None:
            stats[filename]["pages"].add(str(page))

    documents = [
        {
            "filename": filename,
            "chunk_count": item["chunk_count"],
            "page_count": len(item["pages"]),
        }
        for filename, item in stats.items()
    ]
    return sorted(documents, key=lambda item: item["filename"].lower())


def get_document_info(filename: str) -> Optional[Dict[str, Any]]:
    """返回单个文件的统计信息，不存在时返回 None。"""
    for item in list_knowledge_base_documents():
        if item["filename"] == filename:
            return item
    return None


def delete_document_by_filename(filename: str) -> int:
    """按 metadata.filename 删除一个文件的全部 chunks。"""
    collection = get_collection()
    result = collection.get(
        where={"filename": filename},
        include=["metadatas"],
    )
    ids = result.get("ids") or []
    if not ids:
        return 0

    collection.delete(ids=ids)
    return len(ids)


def delete_documents_by_filename(filenames: Iterable[str]) -> int:
    """批量删除文件，返回删除的 chunk 总数。"""
    return sum(
        delete_document_by_filename(str(filename))
        for filename in dict.fromkeys(filenames)
    )


def replace_document_chunks(
    filename: str,
    new_chunks: List[Dict[str, Any]],
) -> Dict[str, int]:
    """
    原子化程度更高的文件重建：先备份旧 chunks，再删除并写入新 chunks。

    新数据写入失败时会尝试恢复旧数据，避免文件直接从知识库消失。
    """
    if not new_chunks:
        raise ValueError(f"文档 {filename} 没有可写入的文本块。")

    collection = get_collection()
    backup = collection.get(
        where={"filename": filename},
        include=["documents", "metadatas"],
    )
    old_ids = backup.get("ids") or []
    old_documents = backup.get("documents") or []
    old_metadatas = backup.get("metadatas") or []
    new_ids = [item["id"] for item in new_chunks]

    try:
        if old_ids:
            collection.delete(ids=old_ids)

        collection.add(
            ids=new_ids,
            documents=[item["text"] for item in new_chunks],
            metadatas=[item["metadata"] for item in new_chunks],
        )
    except Exception:
        # 清理可能已部分写入的新 IDs。
        try:
            collection.delete(ids=new_ids)
        except Exception:
            pass

        # 尽最大可能恢复旧版本。
        if old_ids:
            collection.add(
                ids=old_ids,
                documents=old_documents,
                metadatas=old_metadatas,
            )
        raise

    return {
        "removed_chunks": len(old_ids),
        "added_chunks": len(new_chunks),
    }


def clear_knowledge_base() -> int:
    """删除整个 collection；下次访问时自动创建空 collection。"""
    global _collection

    client = get_chroma_client()
    deleted_count = get_collection().count()
    client.delete_collection(name=COLLECTION_NAME)
    _collection = None
    return deleted_count
