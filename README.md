# DocuMind · 多步 RAG-Agent 本地知识库问答系统

> 基于 **RAG + 多步 Agent（LangGraph）** 的本地知识库问答系统：支持 PDF / TXT / Markdown / DOCX / PPTX / HTML / CSV 共 7 种文档的上传、解析、切块、向量化与混合检索，并通过多步 Agent 自动完成文档问答、整篇总结、多文档对比、知识库查询与文档维护任务。

---

## ✨ 亮点特性

- **7 种文档格式接入**：PDF（PyMuPDF 优先，PyPDF 自动回退）/ TXT / Markdown / DOCX / PPTX / HTML / CSV，解析与切块一站式完成。
- **混合检索（Hybrid Search）**：向量语义召回 + BM25 词法召回，RRF(k=60) 融合，`alpha` 权重可调，兼顾语义与关键词。
- **检索结果重排序（Reranker）**：零依赖的词法 Reranker 默认可用；安装 `sentence-transformers` 后自动启用 BGE Cross-Encoder 高质量精排（缺失自动回退）。
- **多步 Agent（LangGraph）**：基于 `langgraph.create_react_agent` 的 ReAct 规划—工具—综合循环，替代旧版自研循环，保留 5 个工具、二次确认、步数上限、异常回退与完整 trace。
- **对话记忆管理**：基于 token 预算的滑动窗口 + 可选 LLM 摘要压缩，取代旧版“最近 8 条”硬编码，长对话不丢上下文。
- **带页码的来源溯源**：每个 chunk 记录 `filename / page / chunk_index` 元数据，回答可精确回溯原文并列出参考来源。
- **检索与生成解耦**：`retrieve_tool` 只返回原始 chunk 与元数据，不直接生成答案，证据更可靠、可审计。
- **流式输出**：终端答案支持逐字流式返回（UI 可开关）。
- **知识库管理与二次确认**：同名覆盖、删除、整库清空、重建切块；危险操作需页面二次确认（勾选 + 输入指定短语），并带旧向量备份与异常恢复。
- **安全护栏**：启动校验 API Key；`.env` 不入库；`safe_filename` 防路径穿越；危险操作仅生成待确认指令，绝不静默执行。
- **本地化 / 可替换大模型**：向量库 ChromaDB 持久化落盘，LLM 走 OpenAI-compatible 接口，可私有化替换为任意兼容服务。

---

## 🧰 技术栈

| 层 | 选型 |
|---|---|
| UI | Streamlit |
| Agent 框架 | LangGraph（`create_react_agent`）+ LangChain-core |
| 向量库 | ChromaDB（持久化 + 默认嵌入模型） |
| 文档解析 | PyMuPDF / PyPDF · python-docx · python-pptx · beautifulsoup4 · pandas |
| 重排序 | 自研词法 Reranker + 可选 BGE Cross-Encoder |
| 混合检索 | rank_bm25（BM25）+ 向量余弦，RRF 融合 |
| LLM 接口 | OpenAI SDK（含超时/重试/流式）+ LangChain `ChatOpenAI` |
| 配置 | python-dotenv |
| 测试 | pytest |

---

## 📁 项目结构

```text
rag_kb_delete_update/
├── app.py                 # Streamlit 入口：UI、侧栏开关、构建/删除/清空知识库、问答（流式）
├── requirements.txt       # 依赖清单
├── .env.example           # 环境变量模板（占位符，不含真实密钥）
├── data/
│   ├── uploads/           # 用户上传的原始文档（不入库）
│   └── chroma_db/         # ChromaDB 持久化向量库（自动生成，不入库）
├── src/
│   ├── config.py          # 路径/模型/API/开关配置 + 启动校验
│   ├── llm.py             # OpenAI 客户端 + LangChain ChatModel 工厂（超时/重试/流式）
│   ├── document_loader.py # PDF/DOCX/PPTX/HTML/CSV/TXT/MD 解析
│   ├── splitter.py        # 段落感知切块（chunk_size / overlap 可调）
│   ├── retriever.py       # Query Rewrite + 混合检索(BM25+向量) + 重排接入
│   ├── reranker.py        # 检索结果重排序（词法 / CrossEncoder）
│   ├── vectorstore.py     # Chroma 初始化、写入、检索、文档级管理
│   ├── rag_chain.py       # 检索-生成解耦 + 流式合成 + 来源输出
│   ├── prompts.py         # Agent / Final / RAG / 摘要 等提示词
│   ├── agent.py           # 多步 Agent（LangGraph ReAct）+ 5 工具接入
│   ├── tools.py           # Agent 工具集（retrieve / list / info / delete / rebuild）
│   ├── memory.py          # 对话记忆（token 预算 + 摘要压缩）
│   ├── kb_operations.py   # 知识库构建/删除/清空/重建（含备份与异常恢复）
│   └── utils.py           # 公共工具（去重等）
└── tests/                 # pytest 单元测试（36 用例，无需真实 LLM/Chroma）
```

---

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

> ⚠️ **安全提示**：真实密钥只放在 `.env` 中（已被 `.gitignore` 忽略，不会提交）。
> `.env.example` 仅为占位模板，请勿在其中写入真实密钥。

---

## 📄 支持的文档格式

| 格式 | 解析器 | 备注 |
|---|---|---|
| PDF | PyMuPDF（优先）→ PyPDF（回退） | 文本质量更高 |
| TXT / MD | 内置读取 | — |
| DOCX | python-docx | — |
| PPTX | python-pptx | — |
| HTML | beautifulsoup4 | 提取正文文本 |
| CSV | pandas | 按行转文本块 |

所有格式统一输出为 `[{"text": ..., "page": ...}]`，后续切块、向量化、检索流程完全一致。

---

## 🔎 检索与重排管线

一次检索的执行顺序：

```text
用户问题
  → Query Rewrite（LLM 改写为完整检索问句）
  → 向量召回（Chroma，取候选池 RERANK_TOP_N）
  → BM25 词法召回（开启 HYBRID_SEARCH 时）
  → RRF(k=60) 融合（alpha 加权，0=纯向量 / 1=纯 BM25）
  → Reranker 重排（词法 / CrossEncoder）
  → top_k chunks
```

可通过 `.env` 开关控制（见下）。

---

## 🤖 多步 Agent 工作流程（LangGraph）

```text
用户问题
   │
   ▼
LangGraph ReAct Agent（LLM 决策下一步 Action）
   │ action ∈ { retrieve_documents, list_documents, document_info,
   │            request_delete_documents, request_rebuild_documents }
   ▼
Tool 执行  →  通过 RunnableConfig 注入的 ToolContext 收集证据 / 待确认操作
   │
   ├─ 证据充足  →  rag_chain 专用合成器生成带引用答案
   ├─ 待确认操作 →  返回 pending_operation，等待 UI 二次确认（绝不静默执行）
   ├─ 无检索    →  采用 Agent 自身自然语言回答（闲聊/纯管理）
   └─ 异常      →  安全回退，保证问答不中断
```

- `max_agent_steps` 限制工具调用步数（`recursion_limit`），防止无限循环。
- 每一步 action / reason / input / output 写入完整 trace，UI 可展开查看。

---

## 💬 对话记忆

`src/memory.py` 以 token 预算（默认 2000，中文按字、英文/数字按词估算）做滑动窗口：

- 预算内：完整保留全部历史。
- 超预算：保留最近的若干条；较早消息由 LLM 压缩为一段摘要（关闭 `MEMORY_USE_SUMMARY` 时退化为截断），既控制上下文长度又保留长期信息。

---

## 🧩 使用示例

在侧边栏上传文档后，直接用自然语言提问：

- **文件过滤检索**：`只根据 rag基础知识.pdf 解释 RAG 的定义和基本流程。`
- **多文档比较**：`比较 A.pdf 和 B.pdf 中对 RAG 与 Agent 的定位差异。`
- **整篇总结**：`总结 rag基础知识.pdf 的完整内容。`
- **知识库查询**：`当前知识库中有哪些文件？每个文件有多少页和多少 chunks？`
- **Agent 发起删除**：`删除 旧文档.pdf。` → 页面出现确认区，勾选并输入 `确认删除` 后执行。
- **Agent 发起重建**：`使用当前 Chunk 参数重建 旧文档.pdf。` → 二次确认后用最新参数重新切块。

---

## ⚙️ 配置项（.env）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | （必填） | 模型服务密钥；缺失则启动时报错 |
| `OPENAI_BASE_URL` | `https://apihub.agnes-ai.com/v1` | OpenAI-compatible 端点 |
| `OPENAI_MODEL` | `agnes-2.0-flash` | 模型名 |
| `COLLECTION_NAME` | `documind_collection` | Chroma 集合名 |
| `HYBRID_SEARCH` | `false` | 是否启用 BM25+向量 混合检索 |
| `HYBRID_ALPHA` | `0.5` | 词法权重（0=纯向量，1=纯 BM25） |
| `RERANK_ENABLED` | `false` | 是否启用 Reranker |
| `RERANK_TOP_N` | `12` | 重排候选池大小 |
| `RERANK_TYPE` | `auto` | `auto` / `lexical` / `cross_encoder` |
| `MEMORY_MAX_TOKENS` | `2000` | 对话记忆 token 预算 |
| `MEMORY_USE_SUMMARY` | `true` | 超预算时是否用 LLM 摘要压缩 |

---

## ✅ 测试

```bash
pytest tests/ -q
```

覆盖去重、文件名解析、Agent 图构建、工具上下文注入、Reranker 评分、记忆裁剪、文档解析、混合检索融合等，**36 个用例全部通过**，且均不触发真实 LLM / Chroma。

---

## 🔒 安全说明

- 真实密钥仅存于 `.env`（已被 `.gitignore` 忽略）；`.env.example` 只含占位符。
- `src/config.py` 在启动时校验 `OPENAI_API_KEY`，缺失即 fail-fast。
- 删除 / 重建等危险操作只生成“待确认操作”，真实写库只能在 Streamlit 确认区触发。
- `kb_operations.safe_filename` 去除 `..` 与路径分隔符，防止路径穿越。
- 仓库已忽略 `.workbuddy/`（本地记忆）、`.idea/`（IDE）、`data/uploads/`、`data/chroma_db/`。

---

## 📌 说明

- 向量库默认使用 ChromaDB 自带嵌入模型，无需额外下载嵌入服务即可运行。
- 启用 BGE Cross-Encoder 精排：取消 `requirements.txt` 中 `sentence-transformers` 注释并安装，设 `RERANK_TYPE=cross_encoder`。
- 大型文档若超过数十个 chunks，建议后续升级为 Map-Reduce 分层总结。
- 本项目聚焦“私有文档问答 + 来源可信 + 多文档管理”，适合作为企业知识库 / 个人文档助手原型。

---

## 📄 许可证

仅供学习与交流使用。
