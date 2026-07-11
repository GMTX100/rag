"负责封装 OpenAI-compatible API 调用，供 RAG、Agent 和 Query Rewrite 复用"
from openai import OpenAI
from src.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


def get_llm_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("请先在 .env 文件中配置 OPENAI_API_KEY")

    return OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL
    )


def chat_completion(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2
) -> str:
    client = get_llm_client()

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()}
        ],
        temperature=temperature
    )

    return response.choices[0].message.content