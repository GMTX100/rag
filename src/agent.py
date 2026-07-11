"""多步 RAG Agent：Planner → Tool → Observation → Final Answer。"""
import json
import re
from typing import Any, Dict, List, Optional

from src.llm import chat_completion
from src.prompts import AGENT_PLANNER_PROMPT
from src.rag_chain import generate_answer_from_documents
from src.tools import (
    document_info_tool,
    list_documents_tool,
    request_delete_documents_tool,
    request_rebuild_documents_tool,
    retrieve_tool,
)
from src.vectorstore import list_knowledge_base_documents


ALLOWED_ACTIONS = {
    "retrieve_documents",
    "list_documents",
    "document_info",
    "request_delete_documents",
    "request_rebuild_documents",
    "finish",
}


def extract_json_object(text: str) -> Dict[str, Any]:
    """兼容纯 JSON、代码块 JSON 以及前后含少量说明的返回。"""
    if not text or not text.strip():
        raise ValueError("Planner 未返回内容。")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError(f"Planner 返回内容中没有 JSON：{text}")
        value = json.loads(match.group())

    if not isinstance(value, dict):
        raise ValueError("Planner JSON 顶层必须是对象。")
    return value


def format_history(
    history: Optional[List[Dict[str, str]]],
    max_messages: int = 8,
) -> str:
    if not history:
        return "无历史对话。"

    lines = []
    for message in history[-max_messages:]:
        role = "用户" if message.get("role") == "user" else "助手"
        content = str(message.get("content", ""))[:1800]
        lines.append(f"{role}：{content}")
    return "\n".join(lines)


def format_available_documents() -> str:
    documents = list_knowledge_base_documents()
    if not documents:
        return "知识库为空。"
    return "\n".join(
        f"- {item['filename']}（{item['page_count']} 页，{item['chunk_count']} chunks）"
        for item in documents
    )


def summarize_observation_for_planner(observation: Dict[str, Any]) -> str:
    output = observation.get("output", {})
    tool = observation.get("action", "unknown")
    lines = [f"步骤 {observation.get('step')}，工具：{tool}"]

    if not output.get("ok", False):
        lines.append(f"失败：{output.get('error', '未知错误')}")
        available = output.get("available_documents") or []
        if available:
            lines.append(f"可用文件：{available}")
        return "\n".join(lines)

    if tool == "retrieve_documents":
        lines.append(
            f"模式：{output.get('mode')}；文件：{output.get('filenames') or '全库'}；"
            f"取得 {output.get('document_count', 0)} 个 chunks。"
        )
        for item in (output.get("documents") or [])[:4]:
            metadata = item.get("metadata", {})
            preview = str(item.get("text", "")).replace("\n", " ")[:260]
            lines.append(
                f"  - {metadata.get('filename')} 第{metadata.get('page')}页：{preview}"
            )
    elif tool in {"list_documents", "document_info"}:
        lines.append(f"文档信息：{output.get('documents', [])}")
    elif output.get("pending_operation"):
        lines.append(f"待确认操作：{output['pending_operation']}")
    else:
        lines.append(str(output)[:1200])

    return "\n".join(lines)


def format_observations(observations: List[Dict[str, Any]]) -> str:
    if not observations:
        return "尚无 Observation。"
    return "\n\n".join(
        summarize_observation_for_planner(item)
        for item in observations
    )


def plan_next_action(
    question: str,
    history: Optional[List[Dict[str, str]]],
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    user_prompt = f"""
【可用知识库文件】
{format_available_documents()}

【最近对话】
{format_history(history)}

【用户当前任务】
{question}

【已有 Observation】
{format_observations(observations)}

请决定下一步 action，只输出 JSON。
"""
    response = chat_completion(
        system_prompt=AGENT_PLANNER_PROMPT,
        user_prompt=user_prompt,
        temperature=0.0,
    )
    decision = extract_json_object(response)
    action = str(decision.get("action", "")).strip()
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Planner 选择了未知 action：{action}")
    if not isinstance(decision.get("action_input", {}), dict):
        raise ValueError("action_input 必须是 JSON 对象。")
    return decision


def execute_action(action: str, action_input: Dict[str, Any]) -> Dict[str, Any]:
    if action == "retrieve_documents":
        return retrieve_tool(
            query=str(action_input.get("query", "")),
            filenames=action_input.get("filenames") or [],
            mode=str(action_input.get("mode", "semantic")),
            top_k=int(action_input.get("top_k", 5)),
            max_chunks_per_file=int(action_input.get("max_chunks_per_file", 40)),
            use_rewrite=bool(action_input.get("use_rewrite", True)),
        )
    if action == "list_documents":
        return list_documents_tool()
    if action == "document_info":
        return document_info_tool(action_input.get("filenames") or [])
    if action == "request_delete_documents":
        return request_delete_documents_tool(action_input.get("filenames") or [])
    if action == "request_rebuild_documents":
        return request_rebuild_documents_tool(action_input.get("filenames") or [])
    raise ValueError(f"action {action} 不是可执行工具。")


def collect_evidence(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    documents = []
    for observation in observations:
        output = observation.get("output", {})
        if observation.get("action") == "retrieve_documents" and output.get("ok"):
            documents.extend(output.get("documents") or [])
    return documents


def build_tool_state(observations: List[Dict[str, Any]]) -> str:
    states = []
    for observation in observations:
        if observation.get("action") == "retrieve_documents":
            continue
        states.append(summarize_observation_for_planner(observation))
    return "\n\n".join(states)


def operation_response(pending: Dict[str, Any]) -> str:
    action_name = "删除" if pending["type"] == "delete" else "重建"
    filenames = "、".join(pending["filenames"])
    return (
        f"已生成**{action_name}知识库文档**的待确认操作，但尚未执行。\n\n"
        f"目标文件：{filenames}\n\n"
        f"请在页面出现的确认区域中勾选确认，并输入："
        f"`{pending['confirmation_phrase']}`。只有完成二次确认后才会真正执行。"
    )


def fallback_answer(
    question: str,
    trace: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Planner 失败时退回一次普通全库检索，保证问答功能不中断。"""
    output = retrieve_tool(
        query=question,
        mode="semantic",
        top_k=5,
        use_rewrite=True,
    )
    observation = {
        "step": len(trace) + 1,
        "action": "retrieve_documents",
        "reason": "Planner 异常后的安全回退",
        "input": {"query": question},
        "output": output,
    }
    trace.append(observation)
    answer = generate_answer_from_documents(
        question=question,
        retrieved_docs=output.get("documents") or [],
        response_mode="qa",
        answer_instruction="直接回答问题，并明确指出证据不足之处。",
    )
    return {
        "answer": answer,
        "pending_operation": None,
        "trace": trace,
    }


def agent_answer(
    question: str,
    history: Optional[List[Dict[str, str]]] = None,
    max_steps: int = 4,
) -> Dict[str, Any]:
    """
    多步循环入口。

    每轮：Planner 决策 → 执行一个工具 → 记录 Observation。
    达到 finish、出现待确认操作或超过 max_steps 时停止。
    """
    if not question or not question.strip():
        return {
            "answer": "请输入有效问题。",
            "pending_operation": None,
            "trace": [],
        }

    max_steps = max(1, min(int(max_steps), 8))
    observations: List[Dict[str, Any]] = []

    for step in range(1, max_steps + 1):
        try:
            decision = plan_next_action(question, history, observations)
        except Exception as exc:
            observations.append(
                {
                    "step": step,
                    "action": "planner_error",
                    "reason": "Planner 返回无法解析",
                    "input": {},
                    "output": {"ok": False, "error": str(exc)},
                }
            )
            return fallback_answer(question, observations)

        action = decision["action"]
        action_input = decision.get("action_input", {})
        reason = str(decision.get("reason", ""))

        if action == "finish":
            answer = generate_answer_from_documents(
                question=question,
                retrieved_docs=collect_evidence(observations),
                response_mode=str(action_input.get("response_mode", "qa")),
                answer_instruction=str(action_input.get("answer_instruction", "")),
                tool_state=build_tool_state(observations),
            )
            return {
                "answer": answer,
                "pending_operation": None,
                "trace": observations,
            }

        try:
            output = execute_action(action, action_input)
        except Exception as exc:
            output = {"ok": False, "tool": action, "error": str(exc)}

        observation = {
            "step": step,
            "action": action,
            "reason": reason,
            "input": action_input,
            "output": output,
        }
        observations.append(observation)

        pending = output.get("pending_operation") if isinstance(output, dict) else None
        if pending:
            return {
                "answer": operation_response(pending),
                "pending_operation": pending,
                "trace": observations,
            }

    # 达到最大步数后，使用已有 Observation 强制综合，避免无限循环。
    answer = generate_answer_from_documents(
        question=question,
        retrieved_docs=collect_evidence(observations),
        response_mode="qa",
        answer_instruction=(
            "Agent 已达到最大工具调用步数。请基于现有证据尽可能回答，"
            "并明确说明尚未覆盖的部分。"
        ),
        tool_state=build_tool_state(observations),
    )
    return {
        "answer": answer,
        "pending_operation": None,
        "trace": observations,
    }
