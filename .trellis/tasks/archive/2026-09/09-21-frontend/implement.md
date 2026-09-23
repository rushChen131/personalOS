# frontend 执行计划

## Step 1. 脚手架
- `frontend/` create-next-app（TypeScript, App Router, Tailwind, lint）
- 依赖安装：zustand, @tanstack/react-query, echarts, react-markdown
- `src/lib/`, `src/types/`, `src/services/`, `src/stores/`, `src/components/ui/`, `src/features/`, `src/app/`
- `next.config.js` 允许跨域（backend dev）

## Step 2. 基础设施
- `services/api.ts`：fetch + token；`services/chat.ts` SSE
- `stores/auth.ts`（JWT + user），`stores/memory.ts`（上下文缓存）
- hooks：useEvents, useGoals, useReports, useMemories, useContext

## Step 3. Layout + Copilot
- `app/layout.tsx` 侧边栏 + AI Copilot 抽屉（SSE 流式）
- Copilot 读取 `usePathname` → `/context` → 快捷问题 + 输入

## Step 4. Dashboard + Journal
- dashboard 卡片/Timeline/快捷输入
- journal 页 AI 抽取预览 + 确认保存（调 journals API）

## Step 5. Timeline + Goals + Projects
- timeline 页 day/week/month
- goals 列表/详情；projects 列表/详情

## Step 6. Memory + Insights + Reports + Chat + Settings
- memory 分组视图；insights 卡片；reports 类型 tab + 详情（echarts）；chat 独立页（conversations + 消息）；settings 占位

## Step 7. 验证
- `npm run lint`、`npx tsc --noEmit`
- 无后端 mock 数据可渲染
- 联调后端：Dashboard/Journal/Reports 真实数据