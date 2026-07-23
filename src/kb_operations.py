"""知识库写操作：上传、构建、删除、清空和确认后的重建。"""
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.config import UPLOAD_DIR
from src.document_loader import load_document
from src.splitter import build_chunks
from src.vectorstore import (
    add_chunks,
    clear_knowledge_base,
    delete_document_by_filename,
    delete_documents_by_filename,
    replace_document_chunks,
)


def safe_filename(filename: str) -> str:
    """提取基本文件名并防御路径穿越（如 "../etc/passwd"）。"""
    name = Path(filename).name
    # 去掉任何残留的路径分隔符与上级引用，仅保留最后一段基本名。
    for sep in ("/", "\\"):
        name = name.replace(sep, "")
    name = name.replace("..", "")
    if not name:
        raise ValueError(f"非法文件名：{filename}")
    return name


def save_uploaded_file(uploaded_file) -> Path:
    filename = safe_filename(uploaded_file.name)
    file_path = UPLOAD_DIR / filename
    with open(file_path, "wb") as file:
        file.write(uploaded_file.getbuffer())
    return file_path


def delete_uploaded_files(filenames: Iterable[str]) -> int:
    deleted_count = 0
    for filename in dict.fromkeys(filenames):
        path = UPLOAD_DIR / safe_filename(str(filename))
        try:
            if path.is_file():
                path.unlink()
                deleted_count += 1
        except OSError:
            continue
    return deleted_count


def clear_upload_directory() -> int:
    deleted_count = 0
    for path in UPLOAD_DIR.iterdir():
        try:
            if path.is_file():
                path.unlink()
                deleted_count += 1
        except OSError:
            continue
    return deleted_count


def build_knowledge_base(
    uploaded_files,
    chunk_size: int,
    chunk_overlap: int,
    replace_same_name: bool = True,
) -> Dict[str, Any]:
    total_chunks = 0
    replaced_chunks = 0
    processed_files: List[str] = []

    for uploaded_file in uploaded_files:
        filename = safe_filename(uploaded_file.name)
        file_path = save_uploaded_file(uploaded_file)
        pages = load_document(file_path)
        chunks = build_chunks(
            pages=pages,
            filename=filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not chunks:
            raise ValueError(f"文档 {filename} 未解析出可写入内容。")

        if replace_same_name:
            result = replace_document_chunks(filename, chunks)
            replaced_chunks += result["removed_chunks"]
            total_chunks += result["added_chunks"]
        else:
            total_chunks += add_chunks(chunks)
        processed_files.append(filename)

    return {
        "total_chunks": total_chunks,
        "replaced_chunks": replaced_chunks,
        "processed_files": processed_files,
    }


def rebuild_documents(
    filenames: Iterable[str],
    chunk_size: int,
    chunk_overlap: int,
) -> Dict[str, Any]:
    """使用 data/uploads 中保存的原文件重新解析、切块并替换向量。"""
    results = []
    for raw_name in dict.fromkeys(filenames):
        filename = safe_filename(str(raw_name))
        file_path = UPLOAD_DIR / filename
        if not file_path.is_file():
            raise FileNotFoundError(
                f"找不到原文件 {filename}。请重新上传后再执行重建。"
            )

        # 先完成解析和切块，成功后才替换旧向量。
        pages = load_document(file_path)
        chunks = build_chunks(
            pages=pages,
            filename=filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not chunks:
            raise ValueError(f"文档 {filename} 未解析出可写入内容。")

        replace_result = replace_document_chunks(filename, chunks)
        results.append({"filename": filename, **replace_result})

    return {
        "documents": results,
        "document_count": len(results),
        "removed_chunks": sum(item["removed_chunks"] for item in results),
        "added_chunks": sum(item["added_chunks"] for item in results),
    }


def execute_confirmed_operation(
    pending_operation: Dict[str, Any],
    chunk_size: int,
    chunk_overlap: int,
) -> Dict[str, Any]:
    """仅供 UI 在二次确认完成后调用。"""
    operation_type = pending_operation.get("type")
    filenames = pending_operation.get("filenames") or []

    if operation_type == "delete":
        deleted_chunks = delete_documents_by_filename(filenames)
        deleted_files = delete_uploaded_files(filenames)
        return {
            "type": "delete",
            "filenames": filenames,
            "deleted_chunks": deleted_chunks,
            "deleted_files": deleted_files,
        }

    if operation_type == "rebuild":
        return {
            "type": "rebuild",
            **rebuild_documents(
                filenames=filenames,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
        }

    raise ValueError(f"不支持的待确认操作：{operation_type}")


__all__ = [
    "build_knowledge_base",
    "clear_knowledge_base",
    "clear_upload_directory",
    "delete_documents_by_filename",
    "delete_uploaded_files",
    "execute_confirmed_operation",
    "rebuild_documents",
    "safe_filename",
]
