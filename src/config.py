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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-XwPBm3pp3Ci3OCM3rlIh6xiwME9ZSBt5HaszKZHyOMOF1H6h")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://apihub.agnes-ai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "agnes-2.0-flash")

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "documind_collection")
