# backend-ai：AI Runtime / Agent / Tool / RAG

## Goal
实现 PersonalOS AI 层：AgentRuntime、AgentContext、AgentInput/Result、BaseAgent + 7 个 Agent、ToolRegistry + 权限、Model Gateway + Router、RAG Runtime（Hybrid）、Action Proposal、agent_runs/tool_runs 全量可追踪。无 OpenAI key 时 Mock 模式全链路可用。

## Requirements

### 抽象层（`技术设计.md` §44-55）
- `AgentRuntime.run(agent_name, context, input) -> AgentResult`（ABC）
- `AgentContext` dataclass: user_id, conversation_id, current_page, current_object_type/id, goal_ids, project_ids, memory_ids, metadata
- `AgentInput`: message, variables, attachments
- `AgentResult`: success, content, structured_output, tool_calls, usage, metadata
- `Agent(ABC)/BaseAgent`: name, description, system_prompt, tools, permissions, execute()
- `Tool(ABC)`: name, description, permission, execute(arguments, context)
- `ToolDefinition`: name, description, input_schema(JSON Schema), permission
- `ToolRegistry` / `AgentRegistry`
- `ModelRouter.select(task_type) -> model name`
- `ContextRuntime.build(context) -> {user, goals, projects, memories, recent_events}`

### Model Gateway（§54）
- `LLM.generate(messages, tools=None, model=None, temperature=0.2)`
- 实现：`OpenAIGateway`（key 存在时）；`MockGateway`（无 key 缺省）——规则式产出
- Gateway 注入环节点：真实模式用 openai SDK（chat.completions, tool calling ≤3 轮）

### Agents（§23-26, 60-63）
- personal_manager: tools=[query_events, query_goals, query_projects, search_memory, query_reports], perms=READ —— 理解→拆解→调工具→综合回答
- journal_agent: tools=[create_event, search_projects, search_goals], perms=READ+WRITE_EVENT —— 自然语言→结构化事件 JSON
- goal_agent / memory_agent / insight_agent / report_agent / coach_agent（coach 只读，建议非决定）

### Tools（§27, 49-52）
query_events, query_goals, query_projects, search_memory, query_insights, query_reports, create_event, calendar_tool(占位)
- 权限校验：agent permissions ∩ tool permission；无权限返回 TOOL_PERMISSION_DENIED

### RAG（§30-32, 58-59）
- `RAGRuntime.search(user_id, query, filters, top_k)`
- Hybrid：关键词（memory/event/content/summary）+ 元数据 filter + 时间 filter + importance 排序
- SQLite 环境关键词检索（instr/ILIKE）；PG 环境 pgvector 余弦（标注切换点）

### Action Proposal（§66-67）
- 高风险 tool（delete_*, modify_goal, send_email, external write）需 requires_confirmation
- `POST /api/v1/actions/{id}/confirm` 路由（backend-core 或本任务补）
- Mock 模式直接跳过需确认动作，返回 proposal 请求

### 可追踪（§41-42, 100）
- 每次 run 落 agent_runs（agent/model/input/output/status/latency/tokens/error）
- 每次 tool 执行落 tool_runs（agent_run_id/tool/input/output/status/latency）

## Acceptance Criteria
- [ ] `POST /api/v1/chat` SSE 流输出完整事件序列 start→thinking→(tool_call/tool_result)*→content*→done（Mock 可走）
- [ ] Mock Gateway 下：journal_agent 把"今天研究 AgentScope 3小时"抽成 Event JSON
- [ ] personal_manager 回答"我最近在研究什么"时调 query_events+search_memory 并综合回答
- [ ] 每条 run 产生 agent_runs + tool_runs 记录（SQLite 可查）
- [ ] 设置 OPENAI_API_KEY 后可切换到真实调用（代码路径存在，可标注跳过）
- [ ] 权限拦截生效（无权限 tool 返回 TOOL_PERMISSION_DENIED）
- [ ] RAG 检索对 memory/event 生效（关键词+时间+重要度）
- [ ] ContextRuntime.build 返回完整上下文
- [ ] ActionProposal 对 delete_event 等触发 confirm 流程
- [ ] ruff 通过

## Notes
- Mock 与真 LLM 走同一结构解析路径（json.loads + pydantic schema 校验），保证可替换
- 依赖 backend-core 的 repositories/schemas/api
- /chat SSE 由本任务接管，替换 backend-core 的占位实现