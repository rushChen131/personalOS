# PersonalOS 技术详细设计文档

**版本：V1.1**

**系统名称：PersonalOS**

**定位：个人智能成长与决策系统**

---

# 1. 技术目标

PersonalOS 不是简单的：

* 日记
* Todo
* 笔记
* AI Chat
* 数据统计
* 报表系统

而是建立一套：

```text
现实生活
    ↓
记录
    ↓
Event 事实
    ↓
Memory 记忆
    ↓
AI 分析
    ↓
Insight 洞察
    ↓
Goal 目标
    ↓
Report 报告
    ↓
Action 行动
    ↓
再次产生 Event
```

最终形成：

```text
             ┌──────────────┐
             │     User     │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │    Event     │
             │   现实事实   │
             └──────┬───────┘
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       Memory     Goal      Project
          │         │         │
          └─────────┼─────────┘
                    ▼
             ┌──────────────┐
             │ AI Runtime   │
             └──────┬───────┘
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
    Insight       Report       Coach
       │            │            │
       └────────────┼────────────┘
                    ▼
                  Action
                    │
                    ▼
                  Event
```

---

# 2. 总体技术架构

```text
┌─────────────────────────────────────────────┐
│                  Frontend                   │
│                                             │
│ Next.js / React / TypeScript                │
│ Tailwind / shadcn/ui                       │
│ Zustand / TanStack Query                   │
│ ECharts / Framer Motion                    │
└─────────────────────┬───────────────────────┘
                      │ REST / SSE
                      ▼
┌─────────────────────────────────────────────┐
│                 API Layer                   │
│                                             │
│ FastAPI                                    │
│ Auth / Context / RateLimit / Permission    │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│              Application Layer              │
│                                             │
│ JournalService                              │
│ EventService                                │
│ GoalService                                 │
│ ProjectService                              │
│ MemoryService                               │
│ ReportService                               │
│ InsightService                              │
│ ChatService                                 │
└─────────────────────┬───────────────────────┘
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│ Agent Runtime│ │ RAG      │ │ Tool Runtime │
└──────┬───────┘ └────┬─────┘ └──────┬───────┘
       │              │              │
       ▼              ▼              ▼
┌─────────────────────────────────────────────┐
│                 AI Layer                    │
│                                             │
│ LLM / Embedding / Reranker                 │
│ OpenAI / Claude / Gemini / Local Model     │
└─────────────────────┬───────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────┐
│                 Data Layer                  │
│                                             │
│ PostgreSQL + pgvector                       │
│ Redis                                       │
│ Object Storage                              │
└─────────────────────────────────────────────┘
```

---

# 3. 核心领域模型

整个系统不要从“页面”开始设计。

应该从领域模型开始。

最核心的 8 个对象：

```text
User
 │
 ├── Event
 │
 ├── Goal
 │    └── GoalMetric
 │
 ├── Project
 │
 ├── Memory
 │
 ├── Insight
 │
 └── Report
```

AI 是围绕这些对象工作的。

---

# 4. Event 事件模型

Event 是整个系统最重要的数据结构。

原则：

> Event 只描述“发生了什么”，不要直接把 AI 判断写进 Event。

例如：

```text
今天 09:30：

完成了 PersonalOS 数据库设计

持续时间：2小时
项目：PersonalOS
```

而不是：

```text
今天效率很高
```

后者属于 Insight。

---

## 4.1 Event 类型

```text
WORK
LEARNING
LIFE
HEALTH
FINANCE
SOCIAL
TRAVEL
PROJECT
THOUGHT
DECISION
ACHIEVEMENT
FAILURE
OTHER
```

---

## 4.2 Event 数据结构

```json
{
  "id": "evt_001",
  "user_id": "usr_001",

  "type": "WORK",

  "title": "完成 PersonalOS 数据库设计",

  "content": "今天完成了 PersonalOS 核心数据库模型设计",

  "start_time": "2026-08-24T09:30:00",
  "end_time": "2026-08-24T11:30:00",

  "duration_minutes": 120,

  "project_id": "project_001",

  "goal_ids": [
    "goal_001"
  ],

  "tags": [
    "AI",
    "PersonalOS",
    "Architecture"
  ],

  "source": "MANUAL",

  "importance": 0.8,

  "created_at": "2026-08-24T11:35:00"
}
```

---

# 5. Event 来源

以后 Event 不应该只有手动输入。

定义统一 Source：

```text
MANUAL
CHAT
CALENDAR
GIT
TODO
EMAIL
HEALTH
LOCATION
BROWSER
AI
IMPORT
API
```

例如：

```text
Git commit
    ↓
Event

Calendar meeting
    ↓
Event

Chat
    ↓
Event

用户输入：
“今天花了两个小时研究 Agent”
    ↓
AI Extraction
    ↓
Event
```

最终形成：

```text
                Event
                  ▲
      ┌───────────┼───────────┐
      │           │           │
   Manual       Git       Calendar
      │           │           │
      └───────────┼───────────┘
                  │
                 AI
```

---

# 6. Journal 日志模型

Journal 和 Event 不一样。

Journal：

> 用户说了什么。

Event：

> 系统认为发生了什么。

例如：

用户输入：

```text
今天感觉特别乱。

上午一直在处理 CRM 的事情，
下午又研究 Agent。

本来想写 PersonalOS，
结果又去看了 DeepTutor。
```

Journal 原文必须完整保留。

然后 AI 提取：

```text
Event 1
CRM 工作

Event 2
Agent 研究

Event 3
PersonalOS 项目

Event 4
DeepTutor 调研
```

所以：

```text
Journal
   │
   ▼
AI Extraction
   │
   ├── Event
   ├── Tag
   ├── Project
   ├── Goal
   └── Emotion/State
```

---

# 7. Goal 目标模型

Goal 不是 Todo。

Goal 是：

> 一段时间内希望达到的状态。

例如：

```text
Goal

建立 PersonalOS 第一版

周期：
2026-08-01 ~ 2026-10-01

目标：
完成 MVP

KR1:
完成核心数据模型

KR2:
完成 AI Runtime

KR3:
完成报告系统

KR4:
完成 Web MVP
```

---

# 8. Goal Metric

Goal 必须支持量化。

例如：

```text
Goal
建立 PersonalOS MVP

Metric

代码完成度
0 → 100%

AI Runtime
0 → 100%

Frontend
0 → 100%

Backend
0 → 100%
```

数据库：

```text
goal_metric

id
goal_id
name
metric_type
current_value
target_value
unit
weight
created_at
updated_at
```

支持：

```text
NUMBER
PERCENT
BOOLEAN
COUNT
TIME
SCORE
CUSTOM
```

---

# 9. Project

Goal 和 Project 必须分开。

例如：

```text
Goal
成为 AI Agent 架构专家
```

下面可以有：

```text
Project
├── PersonalOS
├── Virtual Company
├── Agent Coding Team
└── DeepTutor Research
```

Project 是：

> 做什么。

Goal 是：

> 为什么做。

---

# 10. Memory

Memory 是 PersonalOS 的核心壁垒。

普通 RAG：

```text
文档 → Chunk → Vector
```

PersonalOS：

```text
Event
Journal
Goal
Project
Decision
Insight
Report
     ↓
Memory
```

---

# 11. Memory 类型

```text
FACT
PREFERENCE
DECISION
EXPERIENCE
SKILL
BELIEF
PATTERN
RELATIONSHIP
GOAL_CONTEXT
PROJECT_CONTEXT
```

例如：

```text
Memory

type:
PREFERENCE

content:
用户更喜欢先建立完整架构，再进入编码阶段。
```

又例如：

```text
Memory

type:
PATTERN

content:
用户在复杂项目开始阶段倾向于快速扩展方案范围，
容易导致项目边界扩大。
```

后一个必须有足够数据后才能由 AI 推断。

---

# 12. Memory 生命周期

```text
Event
  ↓
Candidate Memory
  ↓
AI Validation
  ↓
Memory
  ↓
Evidence
  ↓
Confidence
  ↓
Decay / Update
```

Memory 不能永远有效。

例如：

```text
2026

用户主要做 Java
```

过几年可能变成：

```text
用户主要做 AI Agent
```

所以 Memory 必须支持：

```text
confidence
importance
valid_from
valid_to
last_verified_at
source_count
```

---

# 13. Memory 数据结构

```json
{
  "id": "mem_001",

  "type": "PREFERENCE",

  "content": "喜欢先设计完整架构再开始开发",

  "confidence": 0.91,

  "importance": 0.8,

  "source_count": 12,

  "valid_from": "2026-01-01",

  "last_verified_at": "2026-08-24",

  "embedding": "..."
}
```

---

# 14. Insight

Insight 和 Memory 也必须分开。

Memory：

> 长期知道的东西。

Insight：

> AI 最近发现的东西。

例如：

```text
过去 30 天：

你在 AI Agent 方向投入了 42 小时。

其中：

AgentScope：15h
DeepTutor：8h
Coding Agent：11h
其他：8h

Insight：

你最近的主要技术探索已经从传统业务开发
明显转向 Agent Infrastructure。
```

这就是 Insight。

---

# 15. Insight Pipeline

```text
Event
   ↓
Aggregation
   ↓
Pattern Detection
   ↓
LLM Analysis
   ↓
Insight Candidate
   ↓
Confidence Check
   ↓
Insight
```

Insight 可以包含：

```text
发现
原因
证据
影响
建议
```

但注意：

AI 不应该直接替用户决定。

例如：

```text
发现：
最近 30 天投入 Agent 的时间增加 180%。

证据：
Event #123
Event #145
Event #167

可能原因：
项目驱动 / 兴趣驱动

需要进一步确认：
是否希望将 Agent 作为长期方向？
```

---

# 16. Report Engine

Report 是整个系统的输出层。

不是简单：

```text
本周完成了 10 个任务。
```

而应该形成：

```text
事实
 ↓
趋势
 ↓
目标进展
 ↓
问题
 ↓
洞察
 ↓
下一阶段建议
```

---

# 17. Report 类型

```text
DAILY
WEEKLY
MONTHLY
QUARTERLY
YEARLY
CUSTOM
```

---

# 18. Report Dimension

报告不能写死。

设计：

```text
dimension
```

例如：

```text
ALL

WORK

LEARNING

PROJECT

HEALTH

FINANCE

RELATIONSHIP

AI

CAREER

PERSONAL
```

所以同一周可以生成：

```text
2026 Week 34

├── 综合周报
├── 工作周报
├── AI 学习周报
├── PersonalOS 项目周报
└── 个人成长周报
```

这就是你之前提到的：

> 不同用户有不同目标，不同维度输出不同报告。

---

# 19. Report Definition

报告模板也不能写死。

```json
{
  "name": "AI 学习周报",

  "period": "WEEKLY",

  "dimension": "AI",

  "sections": [
    "activity",
    "time_distribution",
    "knowledge",
    "progress",
    "insight",
    "risk",
    "next_action"
  ]
}
```

未来用户甚至可以：

```text
创建自己的报告：

“每周帮我分析一下
我在 AI 领域到底学到了什么。”
```

AI 自动生成 Report Definition。

---

# 20. AI Runtime

这里是整个系统最关键的技术抽象。

不要把业务代码写死：

```python
openai.chat(...)
```

而应该：

```python
agent_runtime.run(...)
```

---

# 21. Agent Runtime 接口

```python
class AgentRuntime:

    async def run(
        self,
        agent_name: str,
        context: AgentContext,
        input: AgentInput
    ) -> AgentResult:
        pass
```

---

# 22. AgentContext

```python
class AgentContext:

    user_id: str

    current_page: str

    current_object_type: str | None

    current_object_id: str | None

    goal_ids: list[str]

    project_ids: list[str]

    memory_ids: list[str]

    conversation_id: str | None
```

这就是前面说的：

> Context-aware AI。

---

# 23. Agent 类型

第一版不要搞几十个 Agent。

先建立：

```text
PersonalManagerAgent
JournalAgent
GoalAgent
MemoryAgent
InsightAgent
ReportAgent
CoachAgent
```

---

# 24. PersonalManagerAgent

这是总调度 Agent。

用户：

```text
帮我看看最近为什么感觉越来越忙。
```

它判断：

```text
需要：

Event 查询
↓
时间统计
↓
Goal 查询
↓
Project 查询
↓
Memory 查询
↓
Insight
```

然后：

```text
PersonalManagerAgent
        │
        ├── EventTool
        ├── GoalTool
        ├── MemoryTool
        ├── ReportTool
        └── InsightTool
```

---

# 25. JournalAgent

负责：

```text
自然语言
    ↓
结构化
```

例如：

```text
今天上午开了两个会，
下午写了 3 个小时代码，
晚上研究了 AgentScope。
```

输出：

```json
{
  "events": [
    {
      "type": "WORK",
      "duration": 120
    },
    {
      "type": "WORK",
      "duration": 180
    },
    {
      "type": "LEARNING",
      "duration": 120
    }
  ]
}
```

---

# 26. ReportAgent

负责：

```text
查询数据
 ↓
统计
 ↓
检索 Memory
 ↓
检索历史 Report
 ↓
生成报告
```

ReportAgent 不应该自己直接访问数据库。

应该通过 Tool：

```text
query_events
query_goals
query_projects
query_memories
query_insights
query_reports
```

---

# 27. Tool Runtime

定义统一 Tool：

```python
class Tool:

    name: str

    description: str

    async def execute(
        self,
        input: dict
    ) -> dict:
        pass
```

例如：

```text
EventQueryTool
GoalQueryTool
MemorySearchTool
ReportQueryTool
CalendarTool
GitTool
WebSearchTool
```

---

# 28. AI 权限模型

这是 PersonalOS 非常重要的一点。

AI 不能拥有无限权限。

定义：

```text
READ
WRITE
DELETE
EXECUTE
```

例如：

```text
JournalAgent

READ:
Event
Goal

WRITE:
Event

DELETE:
NONE

EXECUTE:
NONE
```

而：

```text
ReportAgent

READ:
Event
Goal
Project
Memory
Insight

WRITE:
Report

DELETE:
NONE
```

---

# 29. AI 操作审批

对于高风险动作：

```text
删除数据
修改目标
修改长期 Memory
发送邮件
创建外部任务
```

必须：

```text
AI
 ↓
Proposal
 ↓
User Confirm
 ↓
Execute
```

而不是：

```text
AI
 ↓
直接执行
```

---

# 30. RAG 架构

PersonalOS 的 RAG 不应该只有：

```text
Vector Search
```

应该是：

```text
Hybrid Retrieval
```

包含：

```text
Keyword Search
+
Vector Search
+
Metadata Filter
+
Time Filter
+
Relationship Search
```

---

# 31. RAG Query

用户：

```text
我最近为什么一直想做 AI Agent？
```

系统：

```text
Query
 ↓
Semantic Search
 ↓
Memory Search
 ↓
Event Search
 ↓
Goal Search
 ↓
Project Search
 ↓
Time Filter
 ↓
Rerank
 ↓
LLM
```

---

# 32. Embedding 数据

建议 pgvector：

```text
event.embedding
journal.embedding
memory.embedding
insight.embedding
report.embedding
```

但不要给所有字段都向量化。

重点：

```text
content
summary
meaning
```

---

# 33. 数据库核心表

第一版至少：

```text
users

journals

events

goals

goal_metrics

projects

memories

memory_sources

insights

reports

report_definitions

conversations

messages

agent_runs

tool_runs
```

---

# 34. users

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,

    email VARCHAR(255),

    name VARCHAR(100),

    timezone VARCHAR(64),

    locale VARCHAR(32),

    created_at TIMESTAMP NOT NULL,

    updated_at TIMESTAMP NOT NULL
);
```

---

# 35. events

```sql
CREATE TABLE events (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL,

    type VARCHAR(32) NOT NULL,

    title VARCHAR(500),

    content TEXT,

    start_time TIMESTAMP,

    end_time TIMESTAMP,

    duration_minutes INTEGER,

    source VARCHAR(32),

    project_id UUID,

    importance FLOAT,

    embedding VECTOR(1536),

    created_at TIMESTAMP NOT NULL,

    updated_at TIMESTAMP NOT NULL
);
```

---

# 36. goals

```sql
CREATE TABLE goals (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL,

    title VARCHAR(500) NOT NULL,

    description TEXT,

    status VARCHAR(32),

    priority INTEGER,

    start_date DATE,

    target_date DATE,

    progress FLOAT,

    created_at TIMESTAMP NOT NULL,

    updated_at TIMESTAMP NOT NULL
);
```

---

# 37. memories

```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL,

    type VARCHAR(32),

    content TEXT NOT NULL,

    confidence FLOAT,

    importance FLOAT,

    source_count INTEGER,

    valid_from TIMESTAMP,

    valid_to TIMESTAMP,

    last_verified_at TIMESTAMP,

    embedding VECTOR(1536),

    created_at TIMESTAMP NOT NULL,

    updated_at TIMESTAMP NOT NULL
);
```

---

# 38. reports

```sql
CREATE TABLE reports (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL,

    definition_id UUID,

    type VARCHAR(32),

    dimension VARCHAR(64),

    period_start DATE,

    period_end DATE,

    title VARCHAR(500),

    content JSONB,

    summary TEXT,

    created_at TIMESTAMP NOT NULL
);
```

---

# 39. conversations

```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY,

    user_id UUID NOT NULL,

    title VARCHAR(500),

    context_type VARCHAR(64),

    context_id UUID,

    created_at TIMESTAMP NOT NULL,

    updated_at TIMESTAMP NOT NULL
);
```

---

# 40. messages

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,

    conversation_id UUID NOT NULL,

    role VARCHAR(32),

    content TEXT,

    token_count INTEGER,

    created_at TIMESTAMP NOT NULL
);
```

---

# 41. Agent Run

AI 调用必须记录。

```sql
CREATE TABLE agent_runs (

    id UUID PRIMARY KEY,

    user_id UUID NOT NULL,

    agent_name VARCHAR(100),

    model VARCHAR(100),

    input JSONB,

    output JSONB,

    status VARCHAR(32),

    latency_ms INTEGER,

    token_input INTEGER,

    token_output INTEGER,

    created_at TIMESTAMP NOT NULL
);
```

这样以后可以分析：

```text
今天 AI 调用了多少次？

哪个 Agent 最常用？

成本多少？

失败率多少？

哪个模型效果最好？
```

---

# 42. Tool Run

```sql
CREATE TABLE tool_runs (

    id UUID PRIMARY KEY,

    agent_run_id UUID,

    tool_name VARCHAR(100),

    input JSONB,

    output JSONB,

    status VARCHAR(32),

    latency_ms INTEGER,

    created_at TIMESTAMP NOT NULL
);
```

---

# 43. API 设计

## Journal

```http
POST /api/v1/journals
GET  /api/v1/journals
GET  /api/v1/journals/{id}
```

---

## Event

```http
POST /api/v1/events

GET /api/v1/events

GET /api/v1/events/timeline

GET /api/v1/events/stats
```

---

## Goal

```http
POST /api/v1/goals

GET /api/v1/goals

GET /api/v1/goals/{id}

PUT /api/v1/goals/{id}

POST /api/v1/goals/{id}/metrics
```

---

## Memory

```http
GET /api/v1/memories

GET /api/v1/memories/{id}

POST /api/v1/memories/search
```

---

## Report

```http
POST /api/v1/reports/generate

GET /api/v1/reports

GET /api/v1/reports/{id}
```

---

# 44. AI Chat API

```http
POST /api/v1/chat
```

采用：

```text
SSE
```

例如：

```text
event: start

event: thinking

event: tool_call

event: tool_result

event: content

event: content

event: done
```

前端就可以实现类似 ChatGPT 的实时输出。

---

# 45. Context API

前端打开：

```text
/goal/goal_001
```

请求：

```http
GET /api/v1/context
```

返回：

```json
{
  "page": "goal",

  "object": {
    "type": "goal",
    "id": "goal_001"
  },

  "related_events": [],
  "related_projects": [],
  "related_memories": [],
  "related_reports": []
}
```

然后用户问：

```text
这个目标为什么最近进展这么慢？
```

AI 已经知道：

```text
当前 Goal
+
相关 Event
+
相关 Project
+
历史 Report
```

不需要用户重复描述。

---

# 46. 前端路由

```text
/
├── dashboard
│
├── journal
│
├── timeline
│
├── goals
│   └── [id]
│
├── projects
│   └── [id]
│
├── memory
│
├── insights
│
├── reports
│   └── [id]
│
├── chat
│
└── settings
```

---

# 47. Dashboard

首页只解决一个问题：

> 我现在的人生/工作状态怎么样？

布局：

```text
┌────────────────────────────────────────────┐
│ Good afternoon                            │
│ 今天发生了什么？                          │
│                                            │
│ [ 输入今天发生的事情................ ]      │
└────────────────────────────────────────────┘

┌─────────────┬─────────────┬───────────────┐
│ 今日时间    │ Goal进度     │ AI Insight    │
│ 8.5h        │ 63%          │ 3条           │
└─────────────┴─────────────┴───────────────┘

┌────────────────────────────────────────────┐
│                  Timeline                  │
│                                            │
│ 09:00  CRM                                  │
│ 11:30  PersonalOS                           │
│ 14:00  Agent Research                       │
│ 19:00  Reading                              │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│                  Goals                     │
│                                            │
│ PersonalOS MVP              ███████░ 72%   │
│ Agent Team                  █████░░░ 51%   │
└────────────────────────────────────────────┘
```

---

# 48. Journal 页面

核心操作：

```text
今天发生了什么？
```

支持：

```text
文本
语音
图片
文件
快捷记录
```

输入：

```text
今天研究了一下午 AgentScope，
感觉这个方向可能很有意思。
```

AI 自动显示：

```text
发现 2 个事件

✓ AgentScope 学习 3h

✓ AI Agent 方向探索

关联 Goal：

AI Agent 能力建设

是否保存？
```

用户确认。

---

# 49. Timeline

Timeline 是系统的核心页面之一。

支持：

```text
Day
Week
Month
```

显示：

```text
时间
事件
项目
目标
标签
AI Insight
```

例如：

```text
08:30 ────────────────
       CRM

10:30 ────────────────
       PersonalOS

13:30 ────────────────
       AgentScope

16:00 ────────────────
       Coding

21:00 ────────────────
       Reading
```

---

# 50. Goal 页面

```text
┌───────────────────────────────────────┐
│ PersonalOS MVP                        │
│                                      │
│ 72%                                  │
│ ███████████████░░░░                  │
│                                      │
│ 目标日期：2026-10-01                  │
└───────────────────────────────────────┘

WHY

建立自己的个人智能系统

KEY RESULTS

✓ 数据模型
✓ Event 系统
□ AI Runtime
□ Report Engine

TIMELINE

...

AI COACH

“这个目标过去 7 天进度明显下降，
主要原因是同时投入了三个新项目。”
```

---

# 51. Report 页面

报告不应该只有文字。

应该：

```text
Summary
↓
数据图
↓
Timeline
↓
Goal
↓
Insight
↓
Risk
↓
Next Action
```

例如：

```text
本周总结

工作：42h
学习：13h
项目：3个

目标完成度：

PersonalOS       72%
Agent Team       48%
Virtual Company  35%

AI Insight：

过去两周同时推进的项目从 2 个增加到 5 个。

其中 3 个项目没有明确截止日期。
```

---

# 52. AI Copilot

建议做成全局右侧：

```text
┌─────────────────────────────┐
│ AI Copilot                  │
│                             │
│ 当前上下文：                │
│ PersonalOS MVP              │
│                             │
│ 你可以问：                  │
│                             │
│ 为什么进展变慢？            │
│ 下一步应该做什么？          │
│ 最近有哪些风险？            │
│                             │
│ [ 输入问题................ ] │
└─────────────────────────────┘
```

不同页面上下文自动变化。

---

# 53. AI Copilot 上下文

Dashboard：

```text
User Context
```

Goal：

```text
User
+
Goal
+
Metrics
+
Events
+
Project
+
Memory
+
Reports
```

Report：

```text
User
+
Report
+
Underlying Events
+
Goals
+
Historical Reports
```

---

# 54. 后端目录

```text
backend/

app/

├── api/
│   ├── auth/
│   ├── journal/
│   ├── events/
│   ├── goals/
│   ├── projects/
│   ├── memories/
│   ├── insights/
│   ├── reports/
│   └── chat/
│
├── domain/
│   ├── user/
│   ├── event/
│   ├── goal/
│   ├── project/
│   ├── memory/
│   ├── insight/
│   └── report/
│
├── application/
│   ├── services/
│   ├── commands/
│   └── queries/
│
├── ai/
│   ├── runtime/
│   ├── agents/
│   ├── tools/
│   ├── rag/
│   ├── memory/
│   └── prompts/
│
├── infrastructure/
│   ├── database/
│   ├── redis/
│   ├── llm/
│   ├── embedding/
│   └── storage/
│
├── jobs/
│
└── main.py
```

---

# 55. Frontend目录

```text
frontend/

src/

├── app/
│
├── components/
│   ├── ui/
│   ├── timeline/
│   ├── goal/
│   ├── report/
│   ├── journal/
│   └── ai/
│
├── features/
│   ├── dashboard/
│   ├── journal/
│   ├── timeline/
│   ├── goals/
│   ├── projects/
│   ├── memory/
│   ├── insights/
│   └── reports/
│
├── stores/
│
├── hooks/
│
├── services/
│
├── lib/
│
└── types/
```

---

# 56. 异步任务

使用：

```text
Redis
+
Celery / ARQ
```

执行：

```text
Event embedding
Memory extraction
Insight analysis
Report generation
Daily summary
Weekly report
Monthly report
```

例如：

```text
用户输入 Journal
       ↓
API
       ↓
保存 Journal
       ↓
Queue
       ↓
JournalAgent
       ↓
Event Extraction
       ↓
Event
       ↓
Embedding
       ↓
Memory Candidate
       ↓
Insight
```

---

# 57. 定时任务

每天：

```text
00:00
Daily aggregation
```

每周：

```text
Sunday 23:00

Weekly Report
```

每月：

```text
Last day

Monthly Report
```

每季度：

```text
Quarter End

Quarterly Report
```

每年：

```text
Year End

Yearly Report
```

---

# 58. 报告生成流程

```text
Scheduler
   ↓
ReportJob
   ↓
Load ReportDefinition
   ↓
Load Events
   ↓
Load Goals
   ↓
Load Projects
   ↓
Load Memories
   ↓
Load Historical Reports
   ↓
Statistics
   ↓
Insight Engine
   ↓
ReportAgent
   ↓
Report
   ↓
Notification
```

---

# 59. 事件驱动架构

未来建议内部采用 Event Bus。

例如：

```text
EventCreated

   ↓

┌────────────────────┐
│ MemoryWorker       │
└────────────────────┘

┌────────────────────┐
│ InsightWorker      │
└────────────────────┘

┌────────────────────┐
│ GoalProgressWorker │
└────────────────────┘

┌────────────────────┐
│ EmbeddingWorker    │
└────────────────────┘
```

这样不会把所有逻辑塞进：

```text
POST /events
```

---

# 60. 数据流

最核心的数据流：

```text
User Input

    ↓

Journal

    ↓

Event Extraction

    ↓

Event

    ↓

Embedding

    ↓

Memory Candidate

    ↓

Memory

    ↓

Insight Engine

    ↓

Insight

    ↓

Goal Analysis

    ↓

Report

    ↓

Coach

    ↓

Action

    ↓

New Event
```

---

# 61. DeepTutor 的位置

如果后续接入 DeepTutor，不建议：

```text
PersonalOS
    ↓
DeepTutor
    ↓
所有业务
```

而应该：

```text
             PersonalOS
                  │
            AgentRuntime
                  │
       ┌──────────┼──────────┐
       │          │          │
   LocalAgent  DeepTutor   Other
       │          │          │
       └──────────┼──────────┘
                  │
                LLM
```

定义：

```python
class IAgentRuntime:

    async def run(...):
        pass
```

然后：

```text
LocalRuntime
DeepTutorRuntime
LangGraphRuntime
AgentScopeRuntime
```

都实现这个接口。

这样以后替换框架不会影响业务层。

---

# 62. 第一版不要做的事情

非常重要。

MVP 阶段不要一开始做：

```text
❌ 全自动人生规划

❌ 自动替用户做重大决定

❌ 复杂 Multi-Agent

❌ 20+ Agent

❌ 所有第三方数据接入

❌ 手机 App

❌ 浏览器插件

❌ 社交功能

❌ 复杂知识图谱

❌ 自研向量数据库

❌ 自研 LLM
```

先把：

```text
Event
Goal
Memory
Report
AI Chat
```

做扎实。

---

# 63. MVP 开发顺序

## Phase 1

```text
User
 ↓
Journal
 ↓
Event
 ↓
Timeline
```

先实现：

> 我每天发生了什么？

---

## Phase 2

```text
Goal
 ↓
Goal Metric
 ↓
Project
```

实现：

> 我正在做什么？

---

## Phase 3

```text
Memory
 ↓
RAG
 ↓
AI Chat
```

实现：

> AI 了解我什么？

---

## Phase 4

```text
Insight
 ↓
Weekly Report
```

实现：

> 最近发生了什么变化？

---

## Phase 5

```text
Monthly
Quarterly
Yearly
```

实现：

> 我的长期趋势是什么？

---

# 64. 最终系统

最终可以形成：

```text
                    PersonalOS
                         │
        ┌────────────────┼────────────────┐
        │                │                │
      Reality          Goals           Memory
        │                │                │
        ▼                ▼                ▼
      Events          Projects         RAG
        │                │                │
        └────────────────┼────────────────┘
                         │
                         ▼
                    AI Runtime
                         │
        ┌────────────────┼────────────────┐
        │                │                │
     Insight          Report           Coach
        │                │                │
        └────────────────┼────────────────┘
                         │
                         ▼
                       Action
                         │
                         ▼
                       Event
```

最终它不是：

```text
AI + 日记
```

而是：

```text
        Personal Intelligence OS

记录现实
    ↓
理解自己
    ↓
理解目标
    ↓
发现模式
    ↓
生成报告
    ↓
辅助决策
    ↓
推动行动
    ↓
持续积累
```

---

# 65. 第一阶段真正应该落地的版本

我建议 V0.1 就做下面这些：

```text
┌──────────────────────────────┐
│ PersonalOS                   │
├──────────────────────────────┤
│                              │
│ Dashboard                    │
│                              │
│ 今天发生了什么？             │
│                              │
│ [ 今天研究了 Agent 3 小时 ]  │
│                              │
│ ─────────────────────────── │
│                              │
│ Timeline                     │
│                              │
│ 09:00 CRM                    │
│ 11:00 PersonalOS             │
│ 14:00 Agent                  │
│ 17:00 Coding                 │
│                              │
│ ─────────────────────────── │
│                              │
│ Goals                        │
│                              │
│ PersonalOS       72%         │
│ Agent Team       48%         │
│                              │
│ ─────────────────────────── │
│                              │
│ AI Insight                   │
│                              │
│ “最近两周你的 AI 研究时间    │
│ 增长了 62%。”                │
│                              │
└──────────────────────────────┘
```

这个版本一旦跑起来，就已经不是一个普通 Todo/日记软件了。

---

# 66. 最关键的产品原则

整个项目开发过程中建议始终遵守以下原则：

### 原则一

```text
Event = 事实
```

### 原则二

```text
Memory = 长期认知
```

### 原则三

```text
Goal = 方向
```

### 原则四

```text
Project = 执行载体
```

### 原则五

```text
Insight = AI 发现
```

### 原则六

```text
Report = 阶段性解释
```

### 原则七

```text
Action = 行动
```

### 原则八

```text
AI = Copilot，不是主人
```

最终形成：

```text
FACT
 ↓
KNOWLEDGE
 ↓
INSIGHT
 ↓
DECISION
 ↓
ACTION
 ↓
FACT
```

这才是 PersonalOS 真正的核心闭环。

---

# 67. 下一步开发建议

下一步不要继续堆产品功能。

直接进入：

```text
V1.2
数据库 + API + Agent Runtime 实现设计
```

具体应该继续拆成 5 份技术文档：

```text
01-database-design.md
数据库完整设计
├── ER图
├── 全部DDL
├── 索引
├── pgvector
└── 数据生命周期

02-api-design.md
API完整设计
├── REST API
├── Request
├── Response
├── Error Code
└── SSE

03-agent-runtime.md
Agent Runtime
├── Agent
├── Tool
├── Context
├── Memory
├── RAG
├── Model Router
└── Multi-Agent

04-report-engine.md
报告引擎
├── Report Definition
├── Report Pipeline
├── Insight Engine
├── Prompt
└── Scheduler

05-frontend-design.md
前端详细设计
├── 页面
├── Component
├── State
├── API
├── SSE
└── AI Copilot
```

然后直接进入：

```text
Docker Compose
       ↓
PostgreSQL
Redis
FastAPI
Next.js
       ↓
PersonalOS V0.1
```

**这里最值得先做的是 `01-database-design.md + 02-api-design.md + 03-agent-runtime.md`。**
这三个一旦确定，后面的前端、RAG、报告、Agent 基本都可以顺着实现。
