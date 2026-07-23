"""LLM 接入层：封装 OpenAI-compatible API。

同时提供：
- chat_completion：RAG / 合成 / Query Rewrite 复用的同步与流式调用。
- get_langchain_chat_model：返回 LangChain 的 ChatOpenAI 实例，供升级后的 Agent 使用。
"""
from typing import Iterator, Optional

from openai import OpenAI

from src.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

# 中期增强：LLM 调用统一超时与重试，避免单点故障导致界面卡死。
LLM_TIMEOUT = 60.0
LLM_MAX_RETRIES = 2


def get_llm_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("请先在 .env 文件中配置 OPENAI_API_KEY")

    return OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        timeout=LLM_TIMEOUT,
        max_retries=LLM_MAX_RETRIES,
    )


def chat_completion(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    stream: bool = False,
) -> str | Iterator[str]:
    """同步或流式调用对话模型。

    stream=True 时返回生成器，逐块产出文本；否则返回完整文本。
    """
    client = get_llm_client()
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]

    if not stream:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    def _stream() -> Iterator[str]:
        chunks = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in chunks:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    return _stream()


def get_langchain_chat_model(
    temperature: float = 0.0,
    streaming: bool = False,
):
    """返回 LangChain 的 ChatOpenAI 实例，兼容 OpenAI 网关。

    升级后的 Agent 使用此实例作为规划器（Planner）。
    """
    from langchain_openai import ChatOpenAI

    if not OPENAI_API_KEY:
        raise RuntimeError("请先在 .env 文件中配置 OPENAI_API_KEY")

    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        temperature=temperature,
        streaming=streaming,
        timeout=LLM_TIMEOUT,
        max_retries=LLM_MAX_RETRIES,
    )
