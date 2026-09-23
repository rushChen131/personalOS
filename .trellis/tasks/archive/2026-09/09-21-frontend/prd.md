# frontend：Next.js 前端全量

## Goal
实现 PersonalOS 前端：Next.js App Router + TypeScript + Tailwind + Zustand + TanStack Query，全部页面，SSE 流式 Chat，全局 AI Copilot（上下文感知），ECharts 可视化。

## Requirements

### 脚手架与基础
- Next.js（App Router）+ TypeScript + Tailwind
- 依赖：zustand, @tanstack/react-query, echarts, react-markdown（渲染报告/AI 输出）
- shadcn/ui 风格组件用轻量自研等价组件（不依赖 shadcn CLI registry）
- `src/services/api.ts` fetch client（带 JWT header，401 处理）
- `src/types/`：Event/Goal/Project/Memory/Report/Journal/Chat SSE 类型

### 布局
- 侧边导航（dashboard/journal/timeline/goals/projects/memory/insights/reports/settings）
- 全局右上 AI Copilot 抽屉：读取当前 pathname → `/context` → 显示当前上下文 + 推荐问题 + 输入框 → SSE 流式回答
- 统一 loading/empty/error 状态组件

### 页面（design.md/design2.md §46-52）
1. Dashboard：今日时间投入卡片、Goal 进度、AI Insight、今日 Timeline、快捷输入"今天发生了什么"
2. Journal：文本输入 → 提交 → 显示 AI 抽取事件预览（类型/时长/项目/goal）→ 确认保存
3. Timeline：day/week/month 切换，事件时间轴卡片（含项目/goal/insight）
4. Goals：列表（进度条）+ 详情（WHY/KR/metrics/事件/AI coach 建议）
5. Projects：列表 + 详情（关联事件/goal）
6. Memory：分组视图（兴趣/长期目标/行为模式/最近变化）
7. Insights：insight 卡片列表（类型/置信度/证据）
8. Reports：类型 tab + 维度筛选 + 报告详情（summary/activity 图表/goals/insights/next_actions）
9. Chat：独立对话页（conversations 列表 + 消息流）
10. Settings：用户信息 + AI 偏好开关（占位）

### SSE
- `src/services/chat.ts`：fetch + ReadableStream，按 `event:` 行解析 start/thinking/tool_call/tool_result/content/done
- Journal 页 AI 预览复用同一解析

### 数据可视化
- ECharts 封装组件（时间分布柱/饼图、goal 进度、报告图）

## Acceptance Criteria
- [ ] `npm install && npm run dev` 启动，http://localhost:3000 访问 Dashboard
- [ ] 侧边导航全部 10+ 页面可达
- [ ] Dashboard 展示今日时间/Goal 进度/Timeline/快捷输入
- [ ] Journal 输入后显示 AI 事件预览并可确认保存
- [ ] Timeline day/week/month 切换
- [ ] AI Copilot 抽屉全局存在，上下文随页面变化，SSE 流式回答
- [ ] 无后端时页面显示友好错误（不白屏）
- [ ] `npm run lint` + `tsc --noEmit` 通过
- [ ] NEXT_PUBLIC_API_URL 可配置指向本后端

## Notes
- 后端不可用期间可用 mock service worker（`src/services/mock.ts`）保证页面可开发验收
- 与 backend-core API 契约对齐（统一响应 success/data）
- Report 图表用 ECharts JSON 配置渲染