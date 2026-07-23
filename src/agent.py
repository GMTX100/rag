"""基于 LangChain 的多步 RAG Agent。

用 LangChain 的 AgentExecutor + create_tool_calling_agent 取代原先手写的
Planner 循环，保留原有 5 个工具、二次确认安全机制、fallback 回退与完整 trace。

对外仍暴露 agent_answer(question, history, max_steps) 接口，供 app.py 调用。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from src.llm import get_langchain_chat_model
from src.memory import prepare_history
from src.rag_chain import generate_answer_from_documents
from src.tools import (
    document_info_tool,
    list_documents_tool,
    request_delete_documents_tool,
    request_rebuild_documents_tool,
    retrieve_tool,
)
from src.vectorstore import list_knowledge_base_documents


# ---------------------------------------------------------------------------
# 跨工具调用的共享上下文（通过 RunnableConfig 注入，避免全局可变状态）
# ---------------------------------------------------------------------------
@dataclass
class ToolContext:
    retrieved_docs: List[Dict[str, Any]] = field(default_factory=list)
    pending_operation: Optional[Dict[str, Any]] = None
    observations: List[Dict[str, Any]] = field(default_factory=list)


def _get_context(config: RunnableConfig) -> ToolContext:
    return config["metadata"]["tool_context"]


# ---------------------------------------------------------------------------
# 工具（LangChain @tool，返回文本 Observation 并记录到 ToolContext）
# ---------------------------------------------------------------------------
@tool
def retrieve_documents(
    query: str,
    filenames: Optional[List[str]] = None,
    mode: str = "semantic",
    top_k: int = 5,
    max_chunks_per_file: int = 40,
    use_rewrite: bool = True,
    config: RunnableConfig = None,
) -> str:
    """检索知识库，返回与问题相关的文本块摘要。

    query: 检索问题。
    filenames: 限定检索的文件名列表；为空则在全库检索。
    mode: semantic（语义检索，适合局部问题/概念）或 full_document（整篇读取，适合总结/对比，必须给定 filenames）。
    top_k: 每个文件或全库返回的块数量上限。
    max_chunks_per_file: full_document 模式下每个文件最多读取的块数量。
    use_rewrite: 是否先使用 LLM 将问题改写为更适合检索的查询。
    """
    ctx = _get_context(config)
    result = retrieve_tool(
        query=query,
        filenames=filenames or [],
        mode=mode,
        top_k=top_k,
        max_chunks_per_file=max_chunks_per_file,
        use_rewrite=use_rewrite,
    )
    documents = result.get("documents") or []
    ctx.retrieved_docs.extend(documents)
    ctx.observations.append(
        {
            "action": "retrieve_documents",
            "input": {
                "query": query,
                "filenames": filenames,
                "mode": mode,
                "top_k": top_k,
            },
            "output": {
                k: v for k, v in result.items() if k != "documents"
            } | {
                "documents_preview": [
                    {
                        "metadata": d.get("metadata", {}),
                        "text": str(d.get("text", ""))[:260],
                        "distance": d.get("distance"),
                    }
                    for d in documents[:3]
                ],
                "documents_total": len(documents),
            },
        }
    )
    if not result.get("ok"):
        return (
            f"检索失败：{result.get('error')}。"
            f"可用文件：{result.get('available_documents')}"
        )
    return (
        f"检索成功：模式 {result['mode']}，文件 {result.get('filenames') or '全库'}，"
        f"取得 {result['document_count']} 个 chunks。请基于证据继续，必要时可再次检索。"
    )


@tool
def list_documents(config: RunnableConfig = None) -> str:
    """列出知识库当前所有文档及其页数、块数。文件名称不清楚时优先调用本工具。"""
    ctx = _get_context(config)
    result = list_documents_tool()
    ctx.observations.append(
        {
            "action": "list_documents",
            "input": {},
            "output": {
                "document_count": result.get("document_count"),
                "chunk_count": result.get("chunk_count"),
            },
        }
    )
    documents = result.get("documents") or []
    if not documents:
        return "知识库为空。"
    lines = [
        f"- {item['filename']}（{item['page_count']} 页，{item['chunk_count']} chunks）"
        for item in documents
    ]
    return "知识库文档：\n" + "\n".join(lines)


@tool
def document_info(filenames: List[str], config: RunnableConfig = None) -> str:
    """查询指定文档的详细信息（页数、块数等）。filenames 为文件名称列表。"""
    ctx = _get_context(config)
    result = document_info_tool(filenames)
    ctx.observations.append(
        {
            "action": "document_info",
            "input": {"filenames": filenames},
            "output": {k: v for k, v in result.items() if k != "documents"},
        }
    )
    if not result.get("ok"):
        return (
            f"查询失败：无法唯一匹配 {result.get('unresolved')}。"
            f"可用文件：{result.get('available_documents')}"
        )
    return f"文档信息：{result.get('documents')}"


@tool
def request_delete_documents(filenames: List[str], config: RunnableConfig = None) -> str:
    """请求删除指定文档。只有用户明确要求删除时才使用。本工具只生成待确认操作，不会真正删除。"""
    ctx = _get_context(config)
    result = request_delete_documents_tool(filenames)
    ctx.observations.append(
        {
            "action": "request_delete_documents",
            "input": {"filenames": filenames},
            "output": {k: v for k, v in result.items() if k != "pending_operation"},
        }
    )
    pending = result.get("pending_operation")
    if pending:
        ctx.pending_operation = pending
        return (
            f"已生成删除待确认操作，目标文件：{pending['filenames']}。"
            "请告知用户在界面完成二次确认，不要声称已经删除。"
        )
    return (
        f"无法生成删除操作：{result.get('error')}。"
        f"可用文件：{result.get('available_documents')}"
    )


@tool
def request_rebuild_documents(filenames: List[str], config: RunnableConfig = None) -> str:
    """请求重建指定文档（按当前 Chunk 参数重新切块）。只有用户明确要求重建时才使用。本工具只生成待确认操作。"""
    ctx = _get_context(config)
    result = request_rebuild_documents_tool(filenames)
    ctx.observations.append(
        {
            "action": "request_rebuild_documents",
            "input": {"filenames": filenames},
            "output": {k: v for k, v in result.items() if k != "pending_operation"},
        }
    )
    pending = result.get("pending_operation")
    if pending:
        ctx.pending_operation = pending
        return (
            f"已生成重建待确认操作，目标文件：{pending['filenames']}。"
            "请告知用户在界面完成二次确认，不要声称已经重建。"
        )
    return (
        f"无法生成重建操作：{result.get('error')}。"
        f"可用文件：{result.get('available_documents')}"
    )


AGENT_TOOLS = [
    retrieve_documents,
    list_documents,
    document_info,
    request_delete_documents,
    request_rebuild_documents,
]


AGENT_SYSTEM_PROMPT = """你是 DocuMind 的多步 RAG Agent Planner。

你的职责：根据用户任务、可用文件和已取得的检索证据，决定调用哪个工具，最终综合出答案。
你可以连续调用多个工具（例如对不同文件分别检索后再对比），但每轮只调用一个工具。

可用工具：
- retrieve_documents：检索知识库文本块，适合回答内容相关问题。
- list_documents：列出知识库所有文件，名称不清楚时先调用。
- document_info：查询指定文件的页数/块数等信息。
- request_delete_documents：仅当用户明确要求删除时使用，只生成待确认操作，不会真正执行。
- request_rebuild_documents：仅当用户明确要求重建时使用，只生成待确认操作。

决策规则：
- 涉及知识库内容的问题，在没有取得检索证据前不要直接给最终答案。
- 指定某个文件时，filenames 必须使用“可用知识库文件”中的精确名称；不清楚时先 list_documents。
- 比较两个文件时，确保两个文件都取得证据，可分别多次检索。
- 用户说“总结整篇文档”时优先 full_document 模式（必须给定 filenames）。
- 不要臆造文件名。
- 当已有证据足够回答时，停止调用工具并直接给出最终答案。

安全约束：request_delete_documents / request_rebuild_documents 只生成待确认操作，
你绝不能声称已经执行了删除或重建，必须提示用户在界面完成二次确认。
"""


def build_agent_prompt():
    """返回 Agent 的系统提示（SystemMessage），供 create_react_agent 使用。"""
    return SystemMessage(content=AGENT_SYSTEM_PROMPT)


def build_agent_executor(max_steps: int):
    """构建基于 LangGraph 的 ReAct Agent（编译后的状态图）。"""
    llm = get_langchain_chat_model(temperature=0.0)
    return create_react_agent(
        llm,
        AGENT_TOOLS,
        prompt=build_agent_prompt(),
        version="v2",
    )


# ---------------------------------------------------------------------------
# 辅助函数（格式化 / trace / 回退），保持与 UI 兼容
# ---------------------------------------------------------------------------
def format_history(
    history: Optional[List[Dict[str, str]]],
    max_messages: int = 8,
) -> str:
    """兼容旧调用：直接取最近 N 条。新的记忆管理走 prepare_history。"""
    if not history:
        return "无历史对话。"
    lines = []
    for message in history[-max_messages:]:
        role = "用户" if message.get("role") == "user" else "助手"
        content = str(message.get("content", ""))[:1800]
        lines.append(f"{role}：{content}")
    return "\n".join(lines)


def _summarize_with_llm(prompt: str) -> str:
    """供记忆模块使用的 LLM 摘要回调（同步调用）。"""
    from src.config import MEMORY_MAX_TOKENS, MEMORY_USE_SUMMARY
    from src.llm import chat_completion
    from src.prompts import MEMORY_SUMMARY_PROMPT

    return chat_completion(
        system_prompt=MEMORY_SUMMARY_PROMPT,
        user_prompt=prompt,
        temperature=0.0,
    )


def build_history_block(history: Optional[List[Dict[str, str]]]) -> str:
    """中期增强：基于 token 预算的记忆管理，超出预算时对较早消息做 LLM 摘要。"""
    from src.config import MEMORY_MAX_TOKENS, MEMORY_USE_SUMMARY

    return prepare_history(
        history,
        max_tokens=MEMORY_MAX_TOKENS,
        use_summary=MEMORY_USE_SUMMARY,
        llm_fn=_summarize_with_llm if MEMORY_USE_SUMMARY else None,
    )


def format_available_documents() -> str:
    documents = list_knowledge_base_documents()
    if not documents:
        return "知识库为空。"
    return "\n".join(
        f"- {item['filename']}（{item['page_count']} 页，{item['chunk_count']} chunks）"
        for item in documents
    )


def build_trace(messages, ctx: ToolContext) -> List[Dict[str, Any]]:
    """从 LangGraph 的消息序列与共享上下文还原 Agent 执行轨迹。"""
    # 把同一 action 的富 Observation 排队，按出现顺序与 tool_call 配对。
    obs_queue: Dict[str, List[Dict[str, Any]]] = {}
    for observation in ctx.observations:
        obs_queue.setdefault(observation.get("action"), []).append(observation)

    trace: List[Dict[str, Any]] = []
    step = 0
    for message in messages or []:
        if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
            for call in message.tool_calls:
                step += 1
                action = call["name"]
                queue = obs_queue.get(action, [])
                output = queue.pop(0).get("output", {}) if queue else {}
                trace.append(
                    {
                        "step": step,
                        "action": action,
                        "reason": message.content or "",
                        "input": call.get("args", {}),
                        "output": output,
                    }
                )
    return trace


def build_tool_state(ctx: ToolContext) -> str:
    states = []
    for observation in ctx.observations:
        if observation.get("action") == "retrieve_documents":
            continue
        output = observation.get("output", {})
        states.append(f"- {observation.get('action')}：{output}")
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
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Agent 执行异常后的安全回退：一次普通全库检索 + 直接综合。"""
    output = retrieve_tool(
        query=question,
        mode="semantic",
        top_k=5,
        use_rewrite=True,
    )
    observation = {
        "step": len(observations) + 1,
        "action": "retrieve_documents",
        "reason": "Agent 异常后的安全回退",
        "input": {"query": question},
        "output": {k: v for k, v in output.items() if k != "documents"},
    }
    observations.append(observation)
    answer = generate_answer_from_documents(
        question=question,
        retrieved_docs=output.get("documents") or [],
        response_mode="qa",
        answer_instruction="直接回答问题，并明确指出证据不足之处。",
    )
    return {
        "answer": answer,
        "pending_operation": None,
        "trace": observations,
    }


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def _extract_final_content(messages) -> str:
    """取最后一条不含工具调用的 AI 消息作为最终自然语言回答。"""
    for message in reversed(messages or []):
        if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            return message.content or ""
    return ""


def agent_answer(
    question: str,
    history: Optional[List[Dict[str, str]]] = None,
    max_steps: int = 4,
    stream: bool = False,
) -> Dict[str, Any]:
    """
    多步 Agent 入口（基于 LangGraph 的 ReAct Agent）。

    达到 finish / 出现待确认操作 / 超过 max_steps 时停止，返回
    {"answer", "pending_operation", "trace"}，与 app.py 完全兼容。
    stream=True 时，answer 为文本块生成器（逐字流式输出），否则为完整字符串。
    """
    if not question or not question.strip():
        return {
            "answer": "请输入有效问题。",
            "pending_operation": None,
            "trace": [],
        }

    max_steps = max(1, min(int(max_steps), 8))
    ctx = ToolContext()
    graph = build_agent_executor(max_steps)

    human_content = (
        f"【可用知识库文件】\n{format_available_documents()}\n\n"
        f"【最近对话】\n{build_history_block(history)}\n\n"
        f"【用户当前任务】\n{question}"
    )

    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=human_content)]},
            config={
                "metadata": {"tool_context": ctx},
                # 多留 3 步余量，避免恰好在最终回答前触发递归上限。
                "recursion_limit": max_steps + 3,
            },
        )
    except Exception as exc:  # 模型/解析/递归超限异常 → 安全回退
        return fallback_answer(
            question,
            [{"step": 0, "action": "agent_error", "output": {"error": str(exc)}}],
        )

    messages = result.get("messages", [])

    # 1) 出现待确认操作：优先返回，未确认前绝不执行
    if ctx.pending_operation:
        return {
            "answer": operation_response(ctx.pending_operation),
            "pending_operation": ctx.pending_operation,
            "trace": build_trace(messages, ctx),
        }

    # 2) 已取得检索证据：用专用合成器生成高质量答案（支持流式）
    if ctx.retrieved_docs:
        answer = generate_answer_from_documents(
            question=question,
            retrieved_docs=ctx.retrieved_docs,
            response_mode="qa",
            answer_instruction="",
            tool_state=build_tool_state(ctx),
            stream=stream,
        )
        return {
            "answer": answer,
            "pending_operation": None,
            "trace": build_trace(messages, ctx),
        }

    # 3) 无任何检索（闲聊/纯管理问题）：使用 Agent 自身的自然语言回答
    final_text = _extract_final_content(messages).strip()
    if final_text:
        return {
            "answer": final_text,
            "pending_operation": None,
            "trace": build_trace(messages, ctx),
        }

    # 4) 兜底：主动检索一次再回答
    return fallback_answer(question, ctx.observations)
