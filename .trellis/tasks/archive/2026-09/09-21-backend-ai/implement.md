# backend-ai 执行计划

## Step 1. AI 基础设施
- `app/ai/runtime/{base.py, runtime.py, context.py, model_router.py}`
- `app/ai/gateway/{base.py, openai_gateway.py, mock_gateway.py}`

## Step 2. ContextRuntime
- 读取 backend-core repositories → user/goals/projects/memories/recent_events
- 供 agent 注入 + 供 `/context` API 复用

## Step 3. Tools
- `app/ai/tools/`：query_events, query_goals, query_projects, search_memory, query_insights, query_reports, create_event, delete_event, calendar(占位)
- ToolDefinition 带 JSON-Schema input_schema；ToolRegistry
- Permission 常量；高风险标记（requires_confirmation）

## Step 4. Agents + Registry
- BaseAgent(ABC)；7 个 agent 类；AgentRegistry
- System prompts 英文/中文双语，instructions 强制结构化 JSON

## Step 5. Runtime 装配
- AgentRuntime.run：加载 agent → context build → 循环(prompt→LLM→tool_call?→execute→back)→结果 → 落 agent_runs/tool_runs → 返回 AgentResult
- MockGateway 规则：按 prompt 内标记返回事件抽取结果 / 检索综合 / 对话
- OpenAIGateway：chat.completions create with tools，tool_choice=auto，循环≤3

## Step 6. /chat SSE 接管
- 替换 backend-core 占位：POST /api/v1/chat → asyncc stream
- 事件顺序 D4；structlog 记录 run_id

## Step 7. Action Proposal
- proposals 内存暂存 + `POST /actions/{id}/confirm`（backend-core 补路由，本任务实现 store）
- 需确认工具在 mock 模式返回需确认标记

## Step 8. 验证
- 无 key：chat SSE 全事件；journal 抽取事件落库；agent_runs 有记录
- 权限：给 agent 去掉某 tool 权限，验证拦截
- RAG：search_memory 关键词命中
- ruff check
- 手工 curl /docs 验证