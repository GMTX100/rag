"""对话记忆管理单元测试（无需网络）。"""
from src.memory import estimate_tokens, prepare_history


def _make_history(n, size_each=50):
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"消息内容编号{i}：" + "字" * size_each})
    return msgs


def test_estimate_tokens_counts_chinese_chars():
    # 10 个中文字 + 1 个英文词
    assert estimate_tokens("字" * 10 + " rag") == 11


def test_prepare_history_within_budget_returns_all():
    history = _make_history(4, size_each=10)
    out = prepare_history(history, max_tokens=10000, use_summary=False)
    assert "消息内容编号0" in out
    assert "消息内容编号3" in out
    assert "历史对话摘要" not in out


def test_prepare_history_over_budget_triggers_summary():
    history = _make_history(20, size_each=50)  # 每条约 52 token，远超预算
    calls = []

    def fake_llm(prompt):
        calls.append(prompt)
        return "这是一段历史摘要。"

    out = prepare_history(
        history,
        max_tokens=200,
        use_summary=True,
        llm_fn=fake_llm,
    )
    assert "【历史对话摘要】" in out
    assert "这是一段历史摘要。" in out
    assert calls  # LLM 摘要被调用


def test_prepare_history_over_budget_no_summary_truncates():
    history = _make_history(20, size_each=50)
    out = prepare_history(history, max_tokens=200, use_summary=False)
    assert "较早对话已截断" in out
    # 最近的消息仍在
    assert "消息内容编号19" in out


def test_prepare_history_empty():
    assert prepare_history(None) == "无历史对话。"
