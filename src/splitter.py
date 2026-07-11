"负责将长文本切分为适合向量检索的 chunk，并保留 filename、page、chunk_index 等 metadata。"
import re
import uuid
from typing import List, Dict, Any


def clean_text(text: str) -> str:
    """清理多余空白，但保留段落和换行结构。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    cleaned_lines = []
    for line in text.split("\n"):
        # 只压缩行内空格，不删除换行
        line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 连续三个及以上换行压缩成两个换行
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_text_by_paragraph(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120
) -> List[str]:
    def validate_chunk_params(
            chunk_size: int,
            chunk_overlap: int
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")

        if chunk_overlap < 0:
            raise ValueError("chunk_overlap 不能小于 0")

        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap 必须小于 chunk_size，"
                f"当前 chunk_size={chunk_size}, "
                f"chunk_overlap={chunk_overlap}"
            )
    validate_chunk_params(chunk_size, chunk_overlap)

    text = text.replace("\r", "\n")
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current = ""


    for para in paragraphs:
        if len(current) + len(para) <= chunk_size:
            current += "\n" + para if current else para
        else:
            if current:
                chunks.append(current.strip())

            if len(para) > chunk_size:
                start = 0
                while start < len(para):
                    end = start + chunk_size
                    chunk = para[start:end].strip()
                    if chunk:
                        chunks.append(chunk)
                    start = end - chunk_overlap
            else:
                current = para

    if current:
        chunks.append(current.strip())

    return chunks


def build_chunks(
    pages: List[Dict[str, Any]],
    filename: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120
) -> List[Dict[str, Any]]:
    all_chunks = []

    for page in pages:
        chunks = split_text_by_paragraph(
            page["text"],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )

        for chunk_index, chunk in enumerate(chunks):
            all_chunks.append({
                "id": str(uuid.uuid4()),
                "text": clean_text(chunk),
                "metadata": {
                    "filename": filename,
                    "page": page["page"],
                    "chunk_index": chunk_index
                }
            })

    return all_chunks