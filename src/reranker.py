"""检索结果重排序（Reranker），提升 top-k 精度（中期增强）。

提供两种实现：
- LexicalReranker（默认，零依赖）：基于查询与文档的词重叠重排序，对中文做单字切分。
- CrossEncoderReranker（可选）：sentence-transformers + BGE Reranker 等 Cross-Encoder
  模型，质量更高；未安装依赖或模型时自动回退到 LexicalReranker。

通过 get_reranker(kind) 获取实例，调用 rerank(query, docs, top_n) 返回重排后的文档列表。
"""
import re
from typing import Any, Dict, List, Optional


def tokenize(text: str) -> List[str]:
    """中英文混合分词：英文/数字按词切分，中文按单字切分。"""
    text = (text or "").lower()
    tokens: List[str] = []
    for match in re.findall(r"[a-z0-9]+|[一-鿿]", text):
        if re.match(r"[a-z0-9]+", match):
            tokens.append(match)
        else:
            tokens.extend(list(match))
    return tokens


class LexicalReranker:
    """零依赖的词重叠重排序器。"""

    def score(self, query: str, doc: str) -> float:
        q_tokens = tokenize(query)
        d_tokens = tokenize(doc)
        if not q_tokens or not d_tokens:
            return 0.0
        q_set = set(q_tokens)
        d_set = set(d_tokens)
        overlap = len(q_set & d_set)
        if overlap == 0:
            return 0.0
        # 召回（命中查询词数）× 精确率（命中所占文档词比），
        # 既奖励命中的查询词，也偏好更简洁、更聚焦的文档。
        return overlap * (overlap / len(d_set))

    def rerank(
        self,
        query: str,
        docs: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        scored = [(self.score(query, d.get("text", "")), d) for d in docs]
        scored.sort(key=lambda x: x[0], reverse=True)
        if top_n is not None:
            scored = scored[:top_n]
        return [d for _, d in scored]


class CrossEncoderReranker:
    """基于 sentence-transformers CrossEncoder 的重排序器。"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # 缺少重依赖时优雅回退
            raise RuntimeError(
                "未安装 sentence-transformers，无法使用 CrossEncoderReranker。"
                "请 pip install sentence-transformers，或改用 lexical 类型。"
            ) from exc
        self.model = CrossEncoder(model_name)
        self._lexical = LexicalReranker()

    def rerank(
        self,
        query: str,
        docs: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not docs:
            return []
        pairs = [(query, d.get("text", "")) for d in docs]
        scores = self.model.predict(pairs)
        scored = list(zip(scores, docs))
        scored.sort(key=lambda x: float(x[0]), reverse=True)
        if top_n is not None:
            scored = scored[:top_n]
        return [d for _, d in scored]


def get_reranker(kind: str = "auto") -> LexicalReranker:
    """返回 Reranker 实例。

    kind:
    - "auto"：优先 CrossEncoder（若可用），否则 Lexical。
    - "lexical"：始终使用词法重排序（零依赖）。
    - "cross_encoder"：强制使用 CrossEncoder，不可用时抛错。
    """
    if kind == "lexical":
        return LexicalReranker()

    if kind == "cross_encoder":
        return CrossEncoderReranker()

    # auto
    try:
        return CrossEncoderReranker()
    except RuntimeError:
        return LexicalReranker()
