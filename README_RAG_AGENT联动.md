# DocuMind 多步 RAG-Agent 使用说明

## 1. 本版本新增能力

- 按精确文件名限定检索范围。
- `retrieve_tool` 只返回原始 chunks、metadata 与距离，不直接生成答案。
- Planner → Tool → Observation → Final Answer 多步循环。
- `max_steps` 限制，避免 Agent 无限调用。
- 文档列表、文档信息、删除申请、重建申请等管理工具。
- 删除和重建均先生成 `pending_operation`；真正执行必须在 Streamlit 页面二次确认。
- 删除确认后同时删除 Chroma 向量和 `data/uploads` 原文件。
- 重建确认后使用 `data/uploads` 原文件及当前 Chunk 参数重新切块。

## 2. 替换文件

将本压缩包内容覆盖原项目。主要新增或修改：

- `app.py`
- `src/agent.py`
- `src/tools.py`
- `src/retriever.py`
- `src/rag_chain.py`
- `src/vectorstore.py`
- `src/prompts.py`
- `src/kb_operations.py`（新增）

## 3. 安装与运行

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## 4. 测试问题

### 文件过滤

```text
只根据 rag基础知识.pdf，解释 RAG 的定义和基本流程。
```

### 多文件比较

```text
比较 rag基础知识.pdf 和 AI Agent智能体基础知识标准化文档.pdf 中对 RAG 与 Agent 的定位差异。
```

### 整篇总结

```text
总结 rag基础知识.pdf 的完整内容。
```

### 文档管理查询

```text
当前知识库中有哪些文件？每个文件有多少页和多少 chunks？
```

### Agent 发起删除

```text
删除 rag基础知识.pdf。
```

Agent 不会立即删除。页面会出现确认区，需要：

1. 勾选确认框；
2. 输入 `确认删除`；
3. 点击执行按钮。

### Agent 发起重建

```text
使用当前 Chunk 参数重建 rag基础知识.pdf。
```

重建要求 `data/uploads/rag基础知识.pdf` 仍存在。

## 5. 重要说明

- `full_document` 默认每个文件最多读取 40 个 chunks，以防上下文过长；可在 Planner 参数中调整，但代码限制最大 100。
- 大型论文若超过几十个 chunks，后续建议继续升级为 Map-Reduce 分层总结。
- Agent 的删除/重建工具只是“申请工具”，数据库写操作只能由 Streamlit 确认区调用。
- 如果模型不能稳定输出 JSON，系统会退回普通全库检索，不会直接执行写操作。
