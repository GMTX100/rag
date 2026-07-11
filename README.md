# DocuMind · 多步 RAG-Agent 本地知识库问答系统

> 基于 RAG 与多步 Agent 的本地知识库问答系统：支持 PDF / TXT / Markdown 文档上传、解析、切块、向量化存储与检索，并通过多步 Agent 自动完成文档问答、整篇总结、多文档比较、知识库查询与文档维护任务。

## ✨ 亮点特性

- **多格式文档接入**：PDF / TXT / Markdown 上传、解析、切块、向量化一站式完成。
- **带页码的来源溯源**：每个 chunk 记录 `filename / page / chunk_index` 元数据，回答可精确回溯到原文页码，并列出参考来源。
- **多步 Agent 架构**：`Planner → Tool → Observation → Final Answer` 循环，支持文件级过滤检索、多文档对比、整篇总结、知识库查询，以及删除 / 重建申请。
- **检索与生成解耦**：`retrieve_tool` 只返回原始 chunk 与元数据，不直接生成答案，证据更可靠、可审计。
- **文件级过滤**：按精确文件名限定检索范围，解决多文档内容互相干扰的问题。
- **知识库管理与二次确认**：支持同名文档覆盖、文档删除、整库清空、重建切块；删除 / 重建需页面二次确认（勾选 + 输入指定短语），并带旧向量备份与异常恢复，避免误删与知识库污染。
- **安全回退**：Planner 输出无法解析时自动回退到普通全库检索，保证问答功能不中断。
- **本地化 / 可替换大模型**：向量库 ChromaDB 持久化落盘，LLM 走 OpenAI-compatible 接口，可私有化替换为任意兼容服务。

## 🧰 技术栈

`Streamlit` · `ChromaDB`（持久化 + all-MiniLM-L6-v2 默认嵌入）· `PyPDF` · `OpenAI-compatible API` · `python-dotenv` · `NumPy / Pandas`

## 📁 项目结构

```text
rag_kb_delete_update/
├── app.py                 # Streamlit 入口：UI、参数、构建/删除/清空知识库、问答
├── requirements.txt       # 依赖清单
├── .env.example           # 环境变量模板
├── data/
│   ├── uploads/           # 用户上传的原始文档
│   └── chroma_db/         # ChromaDB 持久化向量库（自动生成）
└── src/
    ├── config.py          # 路径、模型、API、向量库配置
    ├── llm.py             # OpenAI-compatible 调用封装（chat_completion）
    ├── document_loader.py # PDF / TXT / MD 解析
    ├── splitter.py        # 文本切块（chunk_size / overlap 可调）
    ├── retriever.py       # 语义检索 + Query Rewrite（查询改写）
    ├── vectorstore.py     # Chroma 初始化、写入、检索、文档级管理
    ├── rag_chain.py       # 检索与生成解耦，证据格式化与来源输出
    ├── prompts.py         # Planner / Final / RAG 提示词
    ├── agent.py           # 多步 Agent：Planner → Tool → Observation → Final Answer
    ├── tools.py           # Agent 工具集（retrieve / list / info / delete / rebuild）
    └── kb_operations.py   # 知识库构建 / 删除 / 清空 / 重建（含备份与异常恢复）
```

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的密钥与模型（可替换为任意 OpenAI-compatible 服务）：
#   OPENAI_API_KEY=sk-xxx
#   OPENAI_BASE_URL=https://your-endpoint/v1
#   OPENAI_MODEL=你的模型名
#   COLLECTION_NAME=documind_collection

# 3. 启动应用
streamlit run app.py
# 浏览器打开 http://localhost:8501
```

## 💡 使用示例

在侧边栏上传文档后，可直接用自然语言提问：

- **文件过滤检索**：`只根据 rag基础知识.pdf 解释 RAG 的定义和基本流程。`
- **多文档比较**：`比较 A.pdf 和 B.pdf 中对 RAG 与 Agent 的定位差异。`
- **整篇总结**：`总结 rag基础知识.pdf 的完整内容。`
- **知识库查询**：`当前知识库中有哪些文件？每个文件有多少页和多少 chunks？`
- **Agent 发起删除**：`删除 旧文档.pdf。` → 页面出现确认区，勾选并输入 `确认删除` 后执行（仅删除向量与原始文件，不直接改库）。
- **Agent 发起重建**：`使用当前 Chunk 参数重建 旧文档.pdf。` → 二次确认后用最新参数重新切块。

## 🧩 多步 Agent 工作流程

```text
用户问题
   │
   ▼
Planner（LLM，输出 JSON 决策）
   │ action ∈ { retrieve_documents, list_documents, document_info,
   │            request_delete_documents, request_rebuild_documents, finish }
   ▼
Tool 执行  →  Observation（原始 chunk + 元数据 + 距离，不直接作答）
   │
   ├─ 未结束  →  回到 Planner（携带已有 Observation 继续规划）
   └─ finish  →  generate_answer_from_documents（检索与生成解耦，附参考来源）
```

- `max_agent_steps` 限制工具调用步数，防止 Planner 无限循环。
- Planner 异常时自动回退到一次普通全库检索，保证问答不中断。
- 删除 / 重建工具仅“生成待确认操作”，真实写库只能在 Streamlit 确认区触发。

## 📌 说明

- 向量库使用 ChromaDB 默认嵌入模型（all-MiniLM-L6-v2），无需额外下载嵌入服务即可运行。
- 大型文档若超过数十个 chunks，建议后续升级为 Map-Reduce 分层总结。
- 本项目聚焦“私有文档问答 + 来源可信 + 多文档管理”，适合作为企业知识库 / 个人文档助手的原型。

![图片描述文字](https://github.com/GMTX100/rag/blob/main/iamges/iamge1.png)

## 📄 许可证

仅供学习与交流使用。
