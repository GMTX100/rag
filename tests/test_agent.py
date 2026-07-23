"""Agent（LangChain 版）测试：工具上下文注入、提示词、合成/回退分支。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from src.agent import (
    ToolContext,
    agent_answer,
    build_agent_prompt,
    operation_response,
    retrieve_documents,
)
from src.llm import get_langchain_chat_model as llm_factory


def test_langchain_chat_model_builds_without_network():
    model = llm_factory()
    assert model is not None
    # ChatOpenAI 实例应带有项目配置的模型名与 base_url
    assert getattr(model, "model_name", None) or getattr(model, "model", None)
    assert "apihub.agnes-ai.com" in str(getattr(model, "openai_api_base", "") or "")


def test_build_agent_prompt_has_placeholders():
    prompt = build_agent_prompt()
    assert prompt is not None
    assert "DocuMind" in prompt.content
    assert "request_delete_documents" in prompt.content


def test_tool_context_injection_records_docs():
    """验证 LangChain 通过 RunnableConfig 把共享上下文注入工具。"""
    ctx = ToolContext()
    fake_config = {"metadata": {"tool_context": ctx}}
    fake_docs = [
        {
            "text": "RAG 定义",
            "metadata": {"filename": "rag.pdf", "page": 1, "chunk_index": 0},
            "distance": 0.2,
        }
    ]
    with patch("src.agent.retrieve_tool", return_value={"ok": True, "mode": "semantic", "filenames": None, "document_count": 1, "documents": fake_docs}):
        observation = retrieve_documents.invoke(
            {"query": "什么是 RAG"}, config=fake_config
        )
    assert "检索成功" in observation
    assert ctx.retrieved_docs == fake_docs
    assert ctx.observations[0]["action"] == "retrieve_documents"


def test_operation_response_format():
    pending = {
        "operation_id": "abc",
        "type": "delete",
        "filenames": ["old.pdf"],
        "confirmation_phrase": "确认删除",
    }
    text = operation_response(pending)
    assert "old.pdf" in text
    assert "确认删除" in text


def test_agent_answer_pending_operation_short_circuits():
    """出现待确认删除时，直接返回操作提示，不进入合成。"""
    pending = {
        "operation_id": "x",
        "type": "delete",
        "filenames": ["old.pdf"],
        "confirmation_phrase": "确认删除",
    }
    fake_executor = MagicMock()
    fake_executor.invoke.return_value = {
        "output": "",
        "intermediate_steps": [],
    }
    with patch("src.agent.build_agent_executor", return_value=fake_executor), patch(
        "src.agent.generate_answer_from_documents", return_value="不应出现"
    ):
        # 通过 ToolContext 注入 pending_operation
        ctx = ToolContext(pending_operation=pending)
        with patch("src.agent.ToolContext", return_value=ctx):
            result = agent_answer("删除 old.pdf", max_steps=3)
    assert result["pending_operation"] == pending
    assert "old.pdf" in result["answer"]


def test_agent_answer_synthesizes_when_evidence_present():
    """有检索证据时，用专用合成器生成答案。"""
    ctx = ToolContext(
        retrieved_docs=[{"text": "证据", "metadata": {"filename": "a.pdf"}}]
    )
    fake_executor = MagicMock()
    fake_executor.invoke.return_value = {"output": "", "intermediate_steps": []}
    with patch("src.agent.build_agent_executor", return_value=fake_executor), patch(
        "src.agent.generate_answer_from_documents", return_value="合成答案"
    ), patch("src.agent.ToolContext", return_value=ctx):
        result = agent_answer("rag 是什么", max_steps=3)
    assert result["answer"] == "合成答案"
    assert result["pending_operation"] is None


def test_agent_answer_uses_llm_output_when_no_evidence():
    """无检索（闲聊）时，直接采用 Agent 的自然语言回答。"""
    ctx = ToolContext()
    fake_executor = MagicMock()
    fake_executor.invoke.return_value = {
        "messages": [AIMessage(content="你好，我是 DocuMind。")],
    }
    with patch("src.agent.build_agent_executor", return_value=fake_executor), patch(
        "src.agent.generate_answer_from_documents", return_value="不应出现"
    ), patch("src.agent.ToolContext", return_value=ctx):
        result = agent_answer("你好", max_steps=3)
    assert result["answer"] == "你好，我是 DocuMind。"


def test_agent_answer_empty_question():
    result = agent_answer("   ")
    assert result["answer"] == "请输入有效问题。"
    assert result["trace"] == []
