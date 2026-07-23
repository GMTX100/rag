"""将检索与生成解耦，同时保留传统 rag_answer 兼容入口。"""
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.llm import chat_completion
from src.prompts import AGENT_FINAL_PROMPT, RAG_SYSTEM_PROMPT
from src.retriever import retrieve
from src.utils import deduplicate_docs


def format_context(
    retrieved_docs: List[Dict[str, Any]],
    max_total_chars: int = 50000,
    max_chunk_chars: int = 2400,
) -> Tuple[str, List[Dict[str, Any]]]:
    """构造带 [资料N] 编号的证据上下文，并限制总长度。"""
    parts = []
    used_docs: List[Dict[str, Any]] = []
    current_length = 0

    for item in deduplicate_docs(retrieved_docs):
        metadata = item.get("metadata", {})
        filename = metadata.get("filename", "unknown")
        page = metadata.get("page", "unknown")
        chunk_index = metadata.get("chunk_index", "unknown")
        text = str(item.get("text", ""))[:max_chunk_chars]
        block = (
            f"[资料{len(used_docs) + 1}] 文件：{filename}，"
            f"页码：{page}，chunk：{chunk_index}\n{text}"
        )

        if current_length + len(block) > max_total_chars:
            break

        parts.append(block)
        used_docs.append(item)
        current_length += len(block)

    return "\n\n".join(parts), used_docs


def build_sources(retrieved_docs: List[Dict[str, Any]]) -> str:
    lines = []
    for index, item in enumerate(retrieved_docs, start=1):
        metadata = item.get("metadata", {})
        filename = metadata.get("filename", "unknown")
        page = metadata.get("page", "unknown")
        chunk_index = metadata.get("chunk_index", "unknown")
        distance = item.get("distance")
        distance_text = (
            f"，距离：{float(distance):.4f}"
            if distance is not None
            else "，全文读取"
        )
        lines.append(
            f"- 资料{index}：{filename}，第 {page} 页，"
            f"chunk {chunk_index}{distance_text}"
        )
    return "\n".join(lines)


def generate_answer_from_documents(
    question: str,
    retrieved_docs: List[Dict[str, Any]],
    response_mode: str = "qa",
    answer_instruction: str = "",
    tool_state: str = "",
    stream: bool = False,
):
    """根据已有证据生成最终答案。

    stream=False 返回完整字符串；stream=True 返回文本块生成器（中期增强：流式输出）。
    """
    context, used_docs = format_context(retrieved_docs)

    if not context and not tool_state:
        return "知识库中没有找到相关内容，请检查文件名或先构建知识库。"

    user_prompt = f"""
【用户问题】
{question}

【回答模式】
{response_mode}

【回答组织要求】
{answer_instruction or '直接、清晰地回答用户问题。'}

【检索证据】
{context or '无文档证据。'}

【工具状态】
{tool_state or '无。'}

请生成最终答案。
"""
    answer = chat_completion(
        system_prompt=AGENT_FINAL_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
        stream=stream,
    )

    if stream:
        return _stream_with_sources(answer, used_docs)

    if used_docs:
        return f"{answer}\n\n---\n\n### 参考来源\n{build_sources(used_docs)}"
    return answer


def _stream_with_sources(answer_stream, used_docs):
    """流式答案：逐块产出正文，结束后追加参考来源。"""
    full = []
    for chunk in answer_stream:
        full.append(chunk)
        yield chunk
    if used_docs:
        tail = f"\n\n---\n\n### 参考来源\n{build_sources(used_docs)}"
        full.append(tail)
        yield tail


def rag_answer(
    question: str,
    top_k: int = 5,
    use_rewrite: bool = True,
    where: Optional[dict] = None,
) -> str:
    """旧接口兼容：检索后立即生成；新 Agent 主要使用 retrieve_tool。"""
    filenames = None
    if where and isinstance(where, dict) and where.get("filename"):
        filenames = [where["filename"]]

    retrieved_docs = retrieve(
        question=question,
        top_k=top_k,
        use_rewrite=use_rewrite,
        filenames=filenames,
    )
    if not retrieved_docs:
        return "知识库中没有找到相关内容，请先上传文档并构建知识库。"

    context, used_docs = format_context(retrieved_docs)
    user_prompt = f"""
【参考资料】
{context}

【用户问题】
{question}

请基于参考资料回答。
"""
    answer = chat_completion(
        system_prompt=RAG_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
    )
    return f"{answer}\n\n---\n\n### 参考来源\n{build_sources(used_docs)}"
