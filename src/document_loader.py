"负责解析 PDF/TXT/Markdown 文档，并将不同格式文档统一转换为按页组织的文本结构。"
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader


def read_pdf(file_path: Path) -> List[Dict[str, Any]]:
    pages = []
    reader = PdfReader(str(file_path))

    for page_index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()

        if text:
            pages.append({
                "text": text,
                "page": page_index + 1
            })

    return pages


def read_text_file(file_path: Path) -> List[Dict[str, Any]]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return [{"text": text, "page": 1}]


def load_document(file_path: Path) -> List[Dict[str, Any]]:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        return read_pdf(file_path)

    if suffix in [".txt", ".md"]:
        return read_text_file(file_path)

    raise ValueError(f"暂不支持该文件类型：{suffix}")