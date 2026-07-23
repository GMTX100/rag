"""统一管理项目路径、模型参数、API Key 和向量数据库配置。"""
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# 不要把真实密钥直接写进源码，请在项目根目录的 .env 中配置。
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://apihub.agnes-ai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "agnes-2.0-flash")

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "documind_collection")

# ---- 中期增强（功能增强）运行开关 ----
# 是否启用混合检索（BM25 词法 + 向量语义融合）。
HYBRID_SEARCH = os.getenv("HYBRID_SEARCH", "false").lower() == "true"
# 混合检索中词法（BM25）权重，0=纯向量，1=纯 BM25。
HYBRID_ALPHA = float(os.getenv("HYBRID_ALPHA", "0.5"))
# 是否对检索候选做重排序（Reranker）。
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").lower() == "true"
# Reranker 候选池大小（先取较多候选再重排到 top_k）。
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "12"))
# Reranker 类型：auto（有 CrossEncoder 用 CrossEncoder，否则回退词法）/ lexical / cross_encoder。
RERANK_TYPE = os.getenv("RERANK_TYPE", "auto")
# 对话记忆预算（token 近似），超过则对较早消息做摘要压缩。
MEMORY_MAX_TOKENS = int(os.getenv("MEMORY_MAX_TOKENS", "2000"))
# 是否对超出预算的较早消息使用 LLM 摘要压缩。
MEMORY_USE_SUMMARY = os.getenv("MEMORY_USE_SUMMARY", "true").lower() == "true"

# ---- 启动时校验关键配置 ----
if not OPENAI_API_KEY or not OPENAI_API_KEY.strip():
    raise RuntimeError(
        "OPENAI_API_KEY 未配置！"
        "请复制 .env.example 为 .env 并填入真实 API Key。"
    )
