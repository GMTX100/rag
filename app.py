import inspect
import json
from typing import Any, Dict

import streamlit as st

import src.config as cfg
from src.agent import agent_answer
from src.document_loader import supported_extensions
from src.kb_operations import (
    build_knowledge_base,
    clear_knowledge_base,
    clear_upload_directory,
    delete_documents_by_filename,
    delete_uploaded_files,
    execute_confirmed_operation,
)
from src.vectorstore import list_knowledge_base_documents


def init_session_state():
    defaults = {
        "messages": [],
        "pending_operation": None,
        "flash_message": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def show_flash_message():
    flash = st.session_state.pop("flash_message", None)
    if not flash:
        return
    level = flash.get("level", "success")
    getattr(st, level, st.info)(flash.get("message", ""))


def render_sidebar() -> Dict[str, Any]:
    with st.sidebar:
        st.header("⚙️ 参数设置")

        chunk_size = st.slider(
            "Chunk Size",
            min_value=300,
            max_value=1500,
            value=800,
            step=100,
        )
        chunk_overlap = st.slider(
            "Chunk Overlap",
            min_value=0,
            max_value=300,
            value=120,
            step=20,
        )
        max_agent_steps = st.slider(
            "Agent 最大工具调用步数",
            min_value=1,
            max_value=8,
            value=4,
            help="防止 Planner 无限循环。一般问答 3～4 步即可。",
        )
        show_agent_trace = st.checkbox(
            "显示 Agent 执行轨迹",
            value=True,
            help="展示 Planner、工具参数和 Observation，便于调试。",
        )
        stream_output = st.checkbox(
            "流式输出答案",
            value=True,
            help="逐字流式生成最终答案（中期增强）。",
        )
        replace_same_name = st.checkbox(
            "同名文档自动覆盖",
            value=True,
        )

        st.divider()
        st.subheader("🔎 检索增强（中期增强）")
        use_rerank = st.checkbox(
            "启用 Reranker 重排序",
            value=cfg.RERANK_ENABLED,
            help="检索后对候选做重排序，提升 top-k 精度。默认零依赖词法重排。",
        )
        use_hybrid = st.checkbox(
            "启用混合检索 Hybrid Search",
            value=cfg.HYBRID_SEARCH,
            help="BM25 词法 + 向量语义融合（RRF），兼顾关键词与语义。",
        )
        hybrid_alpha = st.slider(
            "混合检索权重 α（BM25 占比）",
            min_value=0.0,
            max_value=1.0,
            value=cfg.HYBRID_ALPHA,
            step=0.1,
            help="0=纯向量，1=纯 BM25。",
            disabled=not use_hybrid,
        )
        memory_max_tokens = st.slider(
            "对话记忆预算（token 近似）",
            min_value=500,
            max_value=6000,
            value=cfg.MEMORY_MAX_TOKENS,
            step=500,
            help="超过预算时对较早对话做 LLM 摘要压缩。",
        )
        memory_use_summary = st.checkbox(
            "较早对话使用 LLM 摘要压缩",
            value=cfg.MEMORY_USE_SUMMARY,
            help="关闭则仅截断展示较早消息。",
        )

        # 把开关实时写入 config，供检索/记忆模块在调用时读取。
        cfg.RERANK_ENABLED = use_rerank
        cfg.HYBRID_SEARCH = use_hybrid
        cfg.HYBRID_ALPHA = hybrid_alpha
        cfg.MEMORY_MAX_TOKENS = memory_max_tokens
        cfg.MEMORY_USE_SUMMARY = memory_use_summary

        st.divider()
        st.subheader("📤 构建知识库")
        uploaded_files = st.file_uploader(
            "上传文档",
            type=supported_extensions(),
            accept_multiple_files=True,
            help="支持 PDF / TXT / MD / DOCX / PPTX / HTML / CSV",
        )
        build_button = st.button(
            "构建 / 更新知识库",
            type="primary",
            use_container_width=True,
        )

        st.divider()
        st.subheader("🗂️ 当前知识库")
        knowledge_documents = list_knowledge_base_documents()
        total_chunks = sum(item["chunk_count"] for item in knowledge_documents)
        col1, col2 = st.columns(2)
        col1.metric("文档数", len(knowledge_documents))
        col2.metric("文本块", total_chunks)

        document_names = [item["filename"] for item in knowledge_documents]
        stats = {item["filename"]: item for item in knowledge_documents}
        selected_documents = st.multiselect(
            "手动选择要删除的文档",
            options=document_names,
            format_func=lambda name: (
                f"{name}（{stats[name]['page_count']} 页，"
                f"{stats[name]['chunk_count']} chunks）"
            ),
        )
        manual_delete_confirm = st.checkbox(
            "我确认删除所选文档",
            key="manual_delete_confirm",
        )
        manual_delete_phrase = st.text_input(
            "输入“删除所选文档”完成二次确认",
            key="manual_delete_phrase",
        )
        manual_delete_button = st.button(
            "删除所选文档",
            disabled=(
                not selected_documents
                or not manual_delete_confirm
                or manual_delete_phrase.strip() != "删除所选文档"
            ),
            use_container_width=True,
        )

        clear_confirmation = st.text_input(
            "输入“清空知识库”以彻底清空",
            key="clear_kb_confirmation",
        )
        clear_kb_button = st.button(
            "彻底清空知识库",
            disabled=clear_confirmation.strip() != "清空知识库",
            use_container_width=True,
        )

        st.divider()
        clear_chat_button = st.button(
            "清空聊天记录",
            use_container_width=True,
        )

    return {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "max_agent_steps": max_agent_steps,
        "show_agent_trace": show_agent_trace,
        "stream_output": stream_output,
        "replace_same_name": replace_same_name,
        "use_rerank": use_rerank,
        "use_hybrid": use_hybrid,
        "hybrid_alpha": hybrid_alpha,
        "memory_max_tokens": memory_max_tokens,
        "memory_use_summary": memory_use_summary,
        "uploaded_files": uploaded_files,
        "build_button": build_button,
        "selected_documents": selected_documents,
        "manual_delete_button": manual_delete_button,
        "clear_kb_button": clear_kb_button,
        "clear_chat_button": clear_chat_button,
    }


def handle_build(sidebar_state: Dict[str, Any]):
    if not sidebar_state["build_button"]:
        return

    uploaded_files = sidebar_state["uploaded_files"]
    if not uploaded_files:
        st.warning("请先上传文档。")
        return

    with st.spinner("正在解析、切块并写入知识库..."):
        try:
            result = build_knowledge_base(
                uploaded_files=uploaded_files,
                chunk_size=sidebar_state["chunk_size"],
                chunk_overlap=sidebar_state["chunk_overlap"],
                replace_same_name=sidebar_state["replace_same_name"],
            )
            message = (
                f"已处理 {len(result['processed_files'])} 个文档，"
                f"写入 {result['total_chunks']} 个 chunks。"
            )
            if result["replaced_chunks"]:
                message += f" 替换旧 chunks {result['replaced_chunks']} 个。"
            st.session_state.flash_message = {
                "level": "success",
                "message": message,
            }
            st.rerun()
        except Exception as exc:
            st.error(f"知识库构建失败：{exc}")


def handle_manual_delete(sidebar_state: Dict[str, Any]):
    if not sidebar_state["manual_delete_button"]:
        return

    filenames = sidebar_state["selected_documents"]
    try:
        deleted_chunks = delete_documents_by_filename(filenames)
        deleted_files = delete_uploaded_files(filenames)
        st.session_state.messages = []
        st.session_state.pending_operation = None
        st.session_state.flash_message = {
            "level": "success",
            "message": (
                f"已删除 {len(filenames)} 个文档、{deleted_chunks} 个 chunks；"
                f"同步删除原文件 {deleted_files} 个。"
            ),
        }
        st.rerun()
    except Exception as exc:
        st.error(f"删除失败：{exc}")


def handle_clear_kb(sidebar_state: Dict[str, Any]):
    if not sidebar_state["clear_kb_button"]:
        return

    try:
        deleted_chunks = clear_knowledge_base()
        deleted_files = clear_upload_directory()
        st.session_state.messages = []
        st.session_state.pending_operation = None
        st.session_state.flash_message = {
            "level": "success",
            "message": (
                f"知识库已清空：删除 {deleted_chunks} 个 chunks，"
                f"清理原文件 {deleted_files} 个。"
            ),
        }
        st.rerun()
    except Exception as exc:
        st.error(f"清空知识库失败：{exc}")


def handle_clear_chat(sidebar_state: Dict[str, Any]):
    if sidebar_state["clear_chat_button"]:
        st.session_state.messages = []
        st.rerun()


def render_trace(trace):
    for item in trace or []:
        step = item.get("step", "?")
        action = item.get("action", "unknown")
        reason = item.get("reason", "")
        st.markdown(f"**步骤 {step}：`{action}`**")
        if reason:
            st.caption(reason)
        st.json(
            {
                "input": item.get("input", {}),
                "observation": _compact_observation(item.get("output", {})),
            },
            expanded=False,
        )


def _compact_observation(output: Dict[str, Any]) -> Dict[str, Any]:
    """避免在轨迹中把所有 chunk 全量展开。"""
    if not isinstance(output, dict):
        return {"value": str(output)}

    compact = {key: value for key, value in output.items() if key != "documents"}
    documents = output.get("documents")
    if isinstance(documents, list):
        compact["documents_preview"] = []
        for item in documents[:3]:
            if isinstance(item, dict) and "text" in item:
                compact["documents_preview"].append(
                    {
                        "metadata": item.get("metadata", {}),
                        "text": str(item.get("text", ""))[:300],
                        "distance": item.get("distance"),
                    }
                )
            else:
                compact["documents_preview"].append(item)
        compact["documents_total"] = len(documents)
    return compact


def render_chat_history(show_agent_trace: bool):
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if (
                show_agent_trace
                and message["role"] == "assistant"
                and message.get("trace")
            ):
                with st.expander("查看 Planner / Observation 执行轨迹"):
                    render_trace(message["trace"])


def render_pending_operation(sidebar_state: Dict[str, Any]):
    pending = st.session_state.pending_operation
    if not pending:
        return

    operation_id = pending["operation_id"]
    operation_type = pending["type"]
    action_name = "删除" if operation_type == "delete" else "重建"
    filenames = pending.get("filenames") or []
    phrase = pending["confirmation_phrase"]

    st.warning(
        f"Agent 请求{action_name}以下文档，但操作尚未执行："
        f"**{'、'.join(filenames)}**"
    )
    st.caption(
        "二次确认要求：先勾选确认框，再输入指定短语。"
        "删除会同时移除向量和 data/uploads 中的原文件；"
        "重建会使用当前侧栏的 Chunk 参数重新切块。"
    )

    confirmed = st.checkbox(
        f"我确认执行本次{action_name}操作",
        key=f"operation_checkbox_{operation_id}",
    )
    typed_phrase = st.text_input(
        f"请输入：{phrase}",
        key=f"operation_phrase_{operation_id}",
    )

    col1, col2 = st.columns(2)
    execute_button = col1.button(
        f"确认并执行{action_name}",
        type="primary" if operation_type == "rebuild" else "secondary",
        disabled=not confirmed or typed_phrase.strip() != phrase,
        key=f"execute_operation_{operation_id}",
        use_container_width=True,
    )
    cancel_button = col2.button(
        "取消操作",
        key=f"cancel_operation_{operation_id}",
        use_container_width=True,
    )

    if cancel_button:
        st.session_state.pending_operation = None
        st.session_state.flash_message = {
            "level": "info",
            "message": f"已取消{action_name}操作，知识库未发生变化。",
        }
        st.rerun()

    if execute_button:
        try:
            with st.spinner(f"正在执行{action_name}操作..."):
                result = execute_confirmed_operation(
                    pending_operation=pending,
                    chunk_size=sidebar_state["chunk_size"],
                    chunk_overlap=sidebar_state["chunk_overlap"],
                )

            if result["type"] == "delete":
                message = (
                    f"删除完成：{len(result['filenames'])} 个文档，"
                    f"{result['deleted_chunks']} 个 chunks，"
                    f"{result['deleted_files']} 个原文件。"
                )
            else:
                message = (
                    f"重建完成：{result['document_count']} 个文档，"
                    f"移除旧 chunks {result['removed_chunks']} 个，"
                    f"写入新 chunks {result['added_chunks']} 个。"
                )

            st.session_state.pending_operation = None
            st.session_state.messages = []
            st.session_state.flash_message = {
                "level": "success",
                "message": message,
            }
            st.rerun()
        except Exception as exc:
            st.error(f"{action_name}操作失败：{exc}")


def handle_user_question(sidebar_state: Dict[str, Any]):
    question = st.chat_input(
        "例如：只根据 rag基础知识.pdf 解释 RAG；比较 A.pdf 和 B.pdf；删除旧文档.pdf"
    )
    if not question:
        return

    history = list(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Agent 正在规划、调用工具并综合回答..."):
            try:
                result = agent_answer(
                    question=question,
                    history=history,
                    max_steps=sidebar_state["max_agent_steps"],
                    stream=sidebar_state["stream_output"],
                )
                answer = result["answer"]
                # 中期增强：流式输出（answer 为生成器时逐字渲染）
                if inspect.isgenerator(answer):
                    answer = st.write_stream(answer)
                else:
                    st.markdown(answer)
                if sidebar_state["show_agent_trace"] and result.get("trace"):
                    with st.expander("查看 Planner / Observation 执行轨迹"):
                        render_trace(result["trace"])
            except Exception as exc:
                result = {"trace": [], "pending_operation": None}
                answer = f"运行出错：{exc}"
                st.error(answer)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "trace": result.get("trace", []),
        }
    )

    if result.get("pending_operation"):
        st.session_state.pending_operation = result["pending_operation"]
        st.rerun()


def main():
    st.set_page_config(
        page_title="DocuMind Multi-step RAG Agent",
        page_icon="📚",
        layout="wide",
    )
    st.title("📚 DocuMind：多步 RAG-Agent")
    st.caption(
        "支持文件级过滤、原始检索工具、多步 Planner/Observation 循环，"
        "以及需二次确认的文档删除与重建。"
    )

    init_session_state()
    show_flash_message()
    sidebar_state = render_sidebar()

    handle_manual_delete(sidebar_state)
    handle_clear_kb(sidebar_state)
    handle_build(sidebar_state)
    handle_clear_chat(sidebar_state)

    render_chat_history(sidebar_state["show_agent_trace"])
    render_pending_operation(sidebar_state)
    handle_user_question(sidebar_state)


if __name__ == "__main__":
    main()
