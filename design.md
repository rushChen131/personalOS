# PersonalOS

## 个人智能成长系统详细设计文档

**版本：V1.0**
**状态：设计阶段**

---

# 1. 项目概述

## 1.1 项目名称

PersonalOS

Personal Operating System —— 个人智能成长操作系统。

---

## 1.2 项目目标

PersonalOS 用于持续记录用户个人历史，并利用 AI 对长期历史进行分析。

系统核心能力：

* 个人日志
* 时间线
* 事件记录
* 目标管理
* 项目管理
* 长期记忆
* AI 洞察
* 周报
* 月报
* 季报
* 年报
* 自定义报告
* AI Copilot
* 多维度个人分析

核心闭环：

```text
记录
 ↓
Event
 ↓
Memory
 ↓
Goal
 ↓
Insight
 ↓
Report
 ↓
Action
 ↓
再次记录
```

---

# 2. 产品定位

PersonalOS 不定位为：

* 普通日记软件
* Todo 软件
* Notion 替代品
* 单纯 AI Chat

而定位为：

> **Personal Intelligence System**

即：

> 一个长期理解用户、记录用户、分析用户并帮助用户进行个人复盘的 AI 系统。

---

# 3. 核心概念

系统有六个核心对象。

```text
Event
Memory
Goal
Project
Insight
Report
```

关系：

```text
                 User
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
     Event       Goal      Project
       │          │          │
       └──────────┼──────────┘
                  ▼
               Memory
                  │
                  ▼
               Insight
                  │
                  ▼
                Report
```

---

# 4. 总体架构

```text
                         Browser
                            │
                            ▼
                 ┌──────────────────┐
                 │     Next.js      │
                 │                  │
                 │ Dashboard        │
                 │ Timeline         │
                 │ Journal          │
                 │ Goals            │
                 │ Projects         │
                 │ Reports          │
                 │ Memory           │
                 │ AI Copilot       │
                 └────────┬─────────┘
                          │
                     REST / SSE
                          │
                          ▼
                 ┌──────────────────┐
                 │     FastAPI      │
                 │                  │
                 │ Auth             │
                 │ Event            │
                 │ Goal             │
                 │ Project          │
                 │ Report           │
                 │ Memory           │
                 │ AI               │
                 └────────┬─────────┘
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
    PostgreSQL           Redis          AI Runtime
    + pgvector                              │
                                  ┌─────────┼─────────┐
                                  ▼         ▼         ▼
                                Agent      RAG       Tools
                                  │         │         │
                                  └─────────┼─────────┘
                                            ▼
                                           LLM
```

---

# 5. 技术选型

## 5.1 前端

| 技术             | 用途            |
| -------------- | ------------- |
| Next.js        | Web Framework |
| React          | UI            |
| TypeScript     | 类型安全          |
| Tailwind CSS   | CSS           |
| shadcn/ui      | UI Components |
| TanStack Query | 服务端数据         |
| Zustand        | 本地状态          |
| ECharts        | 数据可视化         |
| Framer Motion  | 动画            |
| SSE            | AI 流式输出       |

---

## 5.2 后端

| 技术                   | 用途               |
| -------------------- | ---------------- |
| Python               | 后端语言             |
| FastAPI              | Web API          |
| Pydantic             | DTO / Validation |
| SQLAlchemy           | ORM              |
| Alembic              | 数据库迁移            |
| Celery / APScheduler | 异步任务             |
| Redis                | Cache / Queue    |

---

## 5.3 数据库

主数据库：

```text
PostgreSQL
```

向量：

```text
pgvector
```

缓存：

```text
Redis
```

V1 不引入：

```text
MongoDB
Elasticsearch
Milvus
Neo4j
```

避免过早复杂化。

---

# 6. 系统模块

```text
PersonalOS
│
├── User
├── Journal
├── Event
├── Goal
├── Project
├── Memory
├── Insight
├── Report
├── AI
├── Timeline
├── Integration
└── Scheduler
```

---

# 7. User 模块

负责：

* 注册
* 登录
* 用户信息
* 用户偏好
* 时区
* AI 设置
* 数据权限

用户核心对象：

```text
User
 ├── Profile
 ├── Preference
 ├── Goals
 ├── Events
 ├── Projects
 ├── Memories
 └── Reports
```

---

# 8. Journal 模块

负责用户主动输入。

支持：

```text
文字
语音
图片
文件
AI 对话
```

入口：

```text
“今天发生了什么？”
```

例如：

```text
今天完成了 PersonalOS 数据库设计，
下午研究了 AgentScope，
但是感觉 Agent Runtime 设计还有问题。
```

AI 自动解析：

```text
Event 1
完成 PersonalOS 数据库设计

Event 2
研究 AgentScope

Insight
Agent Runtime 设计存在疑问
```

---

# 9. Event 模块

Event 是系统最核心的数据对象。

## 9.1 Event 类型

```text
WORK
LEARNING
PROJECT
MEETING
TASK
THOUGHT
DIARY
EXERCISE
TRAVEL
RELATIONSHIP
FINANCE
HEALTH
READING
CREATION
ACHIEVEMENT
FAILURE
OTHER
```

---

## 9.2 Event 来源

```text
MANUAL
AI_CHAT
CALENDAR
GIT
TODO
FILE
IMPORT
API
SYSTEM
```

---

## 9.3 Event 数据模型

```text
event
--------------------------------
id
user_id
type
title
content
start_time
end_time
source
importance
sentiment
project_id
created_at
updated_at
metadata
```

---

## 9.4 Event 标签

```text
event_tag
-----------
event_id
tag_id
```

例如：

```text
AI
Java
CRM
学习
工作
PersonalOS
```

---

# 10. Timeline

Timeline 是 Event 的可视化。

支持：

```text
Day
Week
Month
Year
```

例如：

```text
2026-09-21

09:00
│
├── CRM 项目
│
11:30
│
├── 项目会议
│
14:00
│
├── AgentScope 学习
│
16:00
│
└── PersonalOS 开发
```

---

# 11. Goal 模块

Goal 表示：

> 用户想完成什么。

---

## 11.1 Goal 类型

```text
CAREER
LEARNING
PROJECT
FINANCE
HEALTH
RELATIONSHIP
LIFE
CREATION
CUSTOM
```

---

## 11.2 Goal 模型

```text
goal
--------------------------------
id
user_id
parent_goal_id
name
description
type
status
priority
start_date
end_date
progress
created_at
updated_at
```

---

# 12. Goal Metric

目标必须支持指标。

例如：

```text
目标：

成为 AI Agent 开发者

指标：

学习时间 >= 100h
项目 >= 3
论文 >= 10
文章 >= 3
```

数据模型：

```text
goal_metric
----------------
id
goal_id
name
metric_type
target_value
current_value
unit
```

---

# 13. Goal 与 Event

通过：

```text
goal_event
```

建立关系：

```text
Goal
 │
 ├── Event
 ├── Event
 ├── Event
 └── Event
```

系统可以根据 Event 自动计算：

```text
目标进度
```

---

# 14. Project

Project 是目标下具体执行的事情。

关系：

```text
Goal
 │
 └── Project
       │
       ├── Task
       ├── Event
       └── Document
```

例如：

```text
Goal：

成为 AI Agent 开发者

Project：

PersonalOS

Task：

设计数据库
设计 Agent Runtime
开发 Event
开发 Goal
开发 Report
```

---

# 15. Memory 模块

Memory 是 AI 对用户长期认知的载体。

分为：

```text
Short Term Memory
Episodic Memory
Semantic Memory
Goal Memory
Preference Memory
Insight Memory
```

---

# 16. Episodic Memory

记录：

> 用户发生过什么。

例如：

```text
2026-09-20
用户完成 AgentScope Demo
```

---

# 17. Semantic Memory

记录：

> 用户长期表现出的事实。

例如：

```text
用户长期关注：

AI Agent
RAG
Multi-Agent
软件架构
```

---

# 18. Goal Memory

记录：

```text
用户当前目标：

构建 PersonalOS
学习 Agent 技术
```

---

# 19. Preference Memory

记录：

```text
用户偏好：

喜欢技术架构
偏好系统化设计
喜欢 Markdown 文档
```

---

# 20. Memory 数据模型

```text
memory
--------------------------------
id
user_id
type
content
importance
confidence
source
embedding
created_at
updated_at
expires_at
metadata
```

---

# 21. RAG

PersonalOS 的 RAG 是：

```text
Personal Knowledge Base
```

数据来源：

```text
日志
报告
项目
文档
目标
AI 对话
用户上传文件
```

处理流程：

```text
Document
 ↓
Parser
 ↓
Chunk
 ↓
Embedding
 ↓
pgvector
```

检索：

```text
Query
 ↓
Embedding
 ↓
Vector Search
 ↓
Metadata Filter
 ↓
Rerank
 ↓
Context
```

---

# 22. AI Runtime

不强绑定 DeepTutor。

定义自己的抽象：

```python
class AgentRuntime:

    async def run(
        self,
        agent,
        context,
        tools=None
    ):
        pass
```

---

# 23. Agent 抽象

```text
Agent
├── id
├── name
├── system_prompt
├── model
├── tools
├── memory_policy
└── output_schema
```

---

# 24. Agent 类型

```text
PersonalManagerAgent

JournalAgent
GoalAgent
MemoryAgent
InsightAgent
ReportAgent
CoachAgent
ResearchAgent
```

---

# 25. PersonalManagerAgent

负责：

```text
理解用户需求
 ↓
分析任务
 ↓
选择 Agent
 ↓
调用 Tool
 ↓
整合结果
```

例如：

> 分析我过去三个月的学习情况。

执行：

```text
Manager
 │
 ├── EventAgent
 ├── GoalAgent
 ├── MemoryAgent
 └── InsightAgent
        │
        ▼
      Report
```

---

# 26. Tool 系统

Tool 采用统一接口：

```python
class Tool:

    name: str

    description: str

    async def execute(
        self,
        arguments
    ):
        pass
```

---

# 27. 第一批 Tool

```text
EventQueryTool
GoalQueryTool
ProjectQueryTool
MemorySearchTool
RAGSearchTool
ReportQueryTool
CalendarTool
GitTool
TodoTool
```

---

# 28. AI Chat

AI Chat 不是独立的数据孤岛。

它必须绑定：

```text
User
Session
Context
Current Page
Current Object
Memory
```

例如用户在 Goal 页面问：

> 为什么这个目标一直没有完成？

AI 自动获得：

```text
当前 Goal
Goal Events
Goal Metrics
Recent Events
Historical Reports
Memory
```

---

# 29. Context System

定义：

```text
Context
├── user
├── current_page
├── current_object
├── time_range
├── selected_goal
├── selected_project
├── recent_events
├── memories
└── retrieved_documents
```

---

# 30. AI Copilot

桌面端右侧：

```text
┌──────────────────────────────┬──────────────┐
│                              │ AI Copilot   │
│                              │              │
│      Main Content            │ 你最近问：   │
│                              │              │
│                              │ 为什么我的   │
│                              │ 学习时间下降 │
│                              │ 了？         │
│                              │              │
│                              │ AI：         │
│                              │ ……           │
└──────────────────────────────┴──────────────┘
```

Copilot 根据当前页面自动获取上下文。

---

# 31. Insight Engine

Insight 是：

> AI 从事实中发现的规律。

输入：

```text
Events
Goals
Projects
Memory
Reports
```

输出：

```text
Trend
Pattern
Risk
Achievement
Anomaly
Suggestion
```

---

# 32. Insight 模型

```text
insight
--------------------------------
id
user_id
type
title
content
period_start
period_end
dimension
confidence
evidence
created_at
```

---

# 33. Insight 类型

```text
TREND
PATTERN
RISK
ACHIEVEMENT
ANOMALY
GOAL_PROGRESS
BEHAVIOR_CHANGE
SUGGESTION
```

---

# 34. Report Engine

报告必须动态配置。

核心对象：

```text
ReportDefinition
```

---

# 35. ReportDefinition

```text
report_definition
--------------------------------
id
user_id
name
period_type
dimensions
metrics
sections
schedule
enabled
```

例如：

```json
{
  "name": "技术成长月报",
  "period_type": "MONTH",
  "dimensions": [
    "AI",
    "Java",
    "Architecture"
  ],
  "metrics": [
    "learning_hours",
    "project_count",
    "reading_count"
  ],
  "sections": [
    "summary",
    "achievement",
    "progress",
    "problem",
    "trend",
    "next_plan"
  ]
}
```

---

# 36. Report 类型

```text
DAILY
WEEKLY
MONTHLY
QUARTERLY
YEARLY
CUSTOM
```

---

# 37. Report 维度

```text
WORK
LEARNING
PROJECT
HEALTH
FINANCE
CAREER
RELATIONSHIP
LIFE
AI
TECHNOLOGY
CUSTOM
```

---

# 38. Report 生成流程

```text
Report Request
      │
      ▼
Report Definition
      │
      ▼
Data Query
      │
 ┌────┼─────┐
 ▼    ▼     ▼
Event Goal Memory
 └────┼─────┘
      ▼
Data Aggregator
      │
      ▼
Insight Engine
      │
      ▼
Report Agent
      │
      ▼
Report
```

---

# 39. 报告层级

不要每次从原始 Event 重新分析全部历史。

采用：

```text
Event
 ↓
Daily Insight
 ↓
Weekly Insight
 ↓
Monthly Insight
 ↓
Quarterly Insight
 ↓
Yearly Insight
```

---

# 40. Weekly Report

核心内容：

```text
本周发生了什么

完成了什么

目标进度

时间投入

重要事件

主要问题

AI Insight

下周建议
```

---

# 41. Monthly Report

增加：

```text
趋势

目标完成率

时间分配

行为变化

项目成果

能力成长

重要决策

下月建议
```

---

# 42. Quarterly Report

关注：

```text
长期趋势

目标完成情况

能力变化

方向变化

重大成果

长期问题
```

---

# 43. Yearly Report

重点回答：

```text
这一年发生了什么？

我完成了什么？

我发生了什么变化？

我的时间主要花在哪里？

哪些目标完成？

哪些目标失败？

哪些事情重复发生？

我真正成长了什么？

下一年应该往哪里走？
```

---

# 44. Report UI

```text
Reports

┌─────────────────────────────────────────────┐
│ WEEK    MONTH    QUARTER    YEAR            │
├─────────────────────────────────────────────┤
│                                             │
│ 2026 September                              │
│                                             │
│ Dimension:                                  │
│ [All] [Work] [Learning] [Project] [AI]    │
│                                             │
│ ──────────────────────────────────────────  │
│                                             │
│ Overview                                    │
│                                             │
│ Work       ███████████                      │
│ Learning   ███████                          │
│ Project    █████████                        │
│                                             │
│ AI Insights                                 │
│                                             │
│ ……                                          │
└─────────────────────────────────────────────┘
```

---

# 45. Dashboard

Dashboard 采用“今天 + 长期”的结构。

```text
┌─────────────────────────────────────────────┐
│ Good afternoon                              │
│ 2026-09-21                                  │
├─────────────────────────────────────────────┤
│                                             │
│ 今天发生了什么？                             │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │ 输入今天发生的事情……                    │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ 工作 6.2h     学习 2.5h     生活 3.1h      │
│                                             │
├─────────────────────────────────────────────┤
│ Timeline                                    │
│                                             │
│ 09:00 CRM                                   │
│ 11:30 Meeting                               │
│ 14:00 Learning                              │
│ 16:00 PersonalOS                            │
│                                             │
├─────────────────────────────────────────────┤
│ Goals                                       │
│                                             │
│ AI Agent          ███████████░ 72%          │
│ PersonalOS        ██████░░░░░ 45%           │
│                                             │
├─────────────────────────────────────────────┤
│ Latest Insights                             │
└─────────────────────────────────────────────┘
```

---

# 46. Journal UI

核心交互：

```text
┌─────────────────────────────────────────────┐
│ 今天发生了什么？                             │
│                                             │
│ 今天完成了……                                │
│                                             │
│                                             │
│ ──────────────────────────────────────────  │
│ AI 自动分析                                 │
│                                             │
│ 类型：学习                                  │
│ 项目：PersonalOS                            │
│ 目标：AI Agent                              │
│ 标签：Agent / RAG                           │
│                                             │
│ [保存] [编辑]                               │
└─────────────────────────────────────────────┘
```

用户确认后才写入正式 Event。

---

# 47. Timeline UI

支持：

```text
Day
Week
Month
Year
```

每个 Event 是卡片：

```text
16:00

完成 Event Engine

Project
PersonalOS

Goal
构建 PersonalOS

AI Insight
这是本周第 3 个核心开发事件
```

---

# 48. Goal UI

```text
My Goals

┌─────────────────────────────────────────────┐
│ AI Agent 技术能力                            │
│                                             │
│ 72%                                         │
│ ███████████████░░░                          │
│                                             │
│ 本周：12.5h                                 │
│ 项目：3                                     │
│ 学习：8                                     │
│                                             │
│ [查看详情]                                  │
└─────────────────────────────────────────────┘
```

---

# 49. Goal Detail

```text
Goal

AI Agent 技术能力

WHY
成为能够独立设计 Agent 系统的工程师

KR

01 AgentScope
02 Multi-Agent
03 论文 10 篇
04 技术文章 3 篇

Progress

Timeline

Related Events

Insights

Reports

AI Coach
```

---

# 50. Memory UI

Memory 不建议做成传统列表。

设计为：

```text
                    My Memory

        ┌───────────────────────┐
        │       User Profile    │
        └───────────────────────┘

兴趣
├── AI Agent
├── RAG
├── 软件架构

长期目标
├── PersonalOS
├── AI Agent 技术

行为模式
├── 经常晚上学习
├── 技术项目投入较高

最近变化
├── AI Agent 学习增加
```

---

# 51. AI 自动发现目标

系统周期性执行：

```text
Recent Events
      │
      ▼
Pattern Detection
      │
      ▼
Potential Goal
      │
      ▼
User Confirmation
      │
      ▼
Goal Created
```

例如：

> 最近 30 天你持续投入 AI Agent 相关学习，要不要建立一个“AI Agent 能力提升”的目标？

---

# 52. AI 自动发现问题

例如：

```text
目标：
阅读 10 篇论文

过去 4 周：

Week1  4
Week2  2
Week3  0
Week4  0
```

系统发现：

```text
Risk：

该目标连续两周没有推进。
```

然后：

```text
AI：

你这个目标已经连续两周没有进展，
是否调整目标或者重新规划？
```

---

# 53. Scheduler

任务：

```text
Daily
 └── Daily Insight

Weekly
 └── Weekly Report

Monthly
 └── Monthly Report

Quarterly
 └── Quarterly Report

Yearly
 └── Yearly Report
```

建议：

```text
V1：APScheduler

V2：
Celery + Redis
```

---

# 54. 外部数据接入

V2：

```text
Calendar
GitHub
GitLab
Todoist
Notion
Apple Health
Google Drive
邮件
Slack
```

统一进入：

```text
Event Pipeline
```

例如：

```text
Git Commit
      │
      ▼
Event
      │
      ▼
Project
      │
      ▼
Goal
```

---

# 55. Event Pipeline

```text
External Source
      │
      ▼
Collector
      │
      ▼
Normalizer
      │
      ▼
Event
      │
      ▼
AI Extractor
      │
      ├── Tags
      ├── Project
      ├── Goal
      └── Memory
```

---

# 56. 数据隔离

所有业务对象必须包含：

``
