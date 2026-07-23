"""对话记忆管理（中期增强）：基于 token 预算的滑动窗口 + 可选 LLM 摘要压缩。

取代原先"最近 8 条"的硬编码切片：
- 预算内：直接保留全部历史。
- 超预算：保留最近的若干条直到预算耗尽；较早消息由 llm_fn 压缩为一段摘要，
  减少上下文占用同时保留长期信息。
"""
import re
from typing import Any, Callable, Dict, List, Optional

# 角色中文映射
_ROLE_MAP = {"user": "用户", "assistant": "助手", "system": "系统"}


def estimate_tokens(text: str) -> int:
    """近似 token 计数：中文按字计、英文/数字按词计。无需额外依赖。"""
    text = text or ""
    cjk = len(re.findall(r"[一-鿿]", text))
    others = len(re.findall(r"[a-zA-Z0-9]+", text))
    return cjk + others


def _format_messages(messages: List[Dict[str, str]]) -> str:
    if not messages:
        return "无历史对话。"
    lines = []
    for message in messages:
        role = _ROLE_MAP.get(message.get("role"), message.get("role", "?"))
        lines.append(f"{role}：{message.get('content', '')}")
    return "\n".join(lines)


def summarize_history(
    older_messages: List[Dict[str, str]],
    llm_fn: Callable[[str], str],
) -> str:
    """调用 LLM 将较早对话压缩为一段摘要。"""
    transcript = _format_messages(older_messages)
    prompt = (
        "请将以下历史对话压缩为简洁的要点摘要，保留关键事实、用户偏好与未决问题，"
        "不要遗漏与当前任务相关的信息：\n\n" + transcript
    )
    try:
        return llm_fn(prompt).strip()
    except Exception:
        # LLM 不可用时退化为截断展示。
        return _truncate_older(older_messages)


def _truncate_older(older_messages: List[Dict[str, str]]) -> str:
    parts = ["（较早对话已截断）"]
    for message in older_messages[-3:]:
        role = _ROLE_MAP.get(message.get("role"), message.get("role", "?"))
        parts.append(f"{role}：{str(message.get('content', ''))[:200]}")
    return "\n".join(parts)


def prepare_history(
    history: Optional[List[Dict[str, str]]],
    max_tokens: int = 2000,
    use_summary: bool = True,
    llm_fn: Optional[Callable[[str], str]] = None,
) -> str:
    """返回压缩后的历史对话文本，供注入 Agent 提示词。

    max_tokens: token 预算。
    use_summary: 超出预算时是否用 LLM 摘要（需提供 llm_fn）。
    llm_fn: 接受 prompt 字符串、返回摘要字符串的回调（通常为 chat_completion 包装）。
    """
    if not history:
        return "无历史对话。"

    total = sum(estimate_tokens(str(m.get("content", ""))) for m in history)
    if total <= max_tokens:
        return _format_messages(history)

    # 从最近往回累加，直到预算耗尽。
    kept: List[Dict[str, str]] = []
    used = 0
    for message in reversed(history):
        tokens = estimate_tokens(str(message.get("content", "")))
        if used + tokens > max_tokens and kept:
            break
        kept.insert(0, message)
        used += tokens

    older = history[: len(history) - len(kept)]

    parts: List[str] = []
    if older:
        if use_summary and llm_fn:
            summary = summarize_history(older, llm_fn)
            parts.append(f"【历史对话摘要】\n{summary}")
        else:
            parts.append(_truncate_older(older))
    parts.append(_format_messages(kept))
    return "\n".join(parts)
