"use client";

import { useEffect } from "react";
import { create } from "zustand";

import type { Category } from "@/types/api";

/**
 * Lightweight i18n layer.
 *
 * The spec never asked for a full i18n framework, so this stays dependency-free:
 * a flat dictionary keyed by dotted string plus a persisted Zustand store.
 * Chinese is the default locale (the primary audience), English is the fallback
 * for technical terms and enum values that come straight from the API.
 */

export type Locale = "zh" | "en";

export const LOCALES: Array<{ value: Locale; label: string; short: string }> = [
  { value: "zh", label: "中文", short: "中" },
  { value: "en", label: "English", short: "EN" },
];

export const DEFAULT_LOCALE: Locale = "zh";

/**
 * Life domains shared by journals, todos and memories, in picker order.
 * Mirrors `models/base.py::Category`; labels live under `category.*`.
 */
export const CATEGORIES: Category[] = [
  "WORK",
  "LEARNING",
  "INVESTMENT",
  "FINANCE",
  "HEALTH",
  "LIFE",
  "SOCIAL",
  "CREATIVE",
  "TRAVEL",
  "OTHER",
];

const STORAGE_KEY = "personalos.locale";

const dictionaries: Record<Locale, Record<string, string>> = {
  zh: {
    // --- shell --------------------------------------------------------------
    "shell.loading": "正在加载 PersonalOS…",
    "shell.signOut": "退出登录",
    "shell.copilot": "AI 助手",
    "shell.language": "语言",

    // --- login --------------------------------------------------------------
    "login.title": "登录 PersonalOS",
    "login.hint": "后端初始化演示用户时会自动填入演示账号。",
    "login.email": "邮箱",
    "login.password": "密码",
    "login.submit": "登录",
    "login.submitting": "登录中…",

    // --- common -------------------------------------------------------------
    "common.loading": "加载中…",
    "common.saving": "保存中…",
    "common.searching": "搜索中…",
    "common.generating": "生成中…",
    "common.generatingBtn": "生成",
    "common.search": "搜索",
    "common.clear": "清除",
    "common.cancel": "取消",
    "common.content": "内容",
    "common.type": "类型",
    "common.title": "标题",
    "common.name": "名称",
    "common.description": "描述",
    "common.status": "状态",
    "common.priority": "优先级",
    "common.details": "详情",
    "common.history": "历史",
    "common.summary": "摘要",
    "common.risks": "风险",
    "common.recommendations": "建议",
    "common.nextActions": "后续行动",
    "common.todos": "待办",
    "common.events": "事件",
    "common.start": "开始",
    "common.end": "结束",
    "common.selectHint": "请选择一项查看内容。",
    "common.optional": "可选",
    "common.prev": "上一页",
    "common.next": "下一页",
    "common.pageOf": "第 {page} / {total} 页",
    "common.delete": "删除",

    // --- dashboard ----------------------------------------------------------
    "dashboard.title": "总览",
    "dashboard.subtitle": "一览你的日志、待办与记忆。",
    "dashboard.statJournals": "日志（累计）",
    "dashboard.statMemories": "记忆",
    "dashboard.statOpenTodos": "未完成待办",
    "dashboard.recentJournals": "最近日志",
    "dashboard.recentJournalsHint": "点击任意一条进入日志页",
    "dashboard.viewReports": "查看报告",
    "dashboard.errorStats": "无法加载统计数据。",

    // --- journals -----------------------------------------------------------
    "journals.title": "日志",
    "journals.subtitle": "撰写日志会对你的近期活动触发记忆蒸馏。",
    "journals.newEntry": "新建日志",
    "journals.entryTitle": "日志标题",
    "journals.entryContent": "今天发生了什么？",
    "journals.saveEntry": "保存日志",
    "journals.allEntries": "全部日志",
    "journals.entry": "日志",
    "journals.empty": "暂无日志。",
    "journals.emptyCategory": "该类型下暂无日志。",
    "journals.errorSave": "无法保存该日志。",

    // --- todos (rendered on the dashboard) ----------------------------------
    "todos.title": "待办清单",
    "todos.newTodo": "新建待办",
    "todos.targetDate": "截止日期",
    "todos.addTodo": "添加待办",
    "todos.empty": "暂无待办。",
    "todos.summary": "{open} 项未完成 · {done} 项已完成",
    "todos.due": "截止 {date}",
    "todos.completedAt": "完成于 {date}",
    "todos.placeholder": "写一篇本周复盘",
    "todos.errorCreate": "无法创建该待办。",
    "todos.errorUpdate": "无法更新该待办。",
    "todos.errorDelete": "无法删除该待办。",
    "todos.markDone": "标记为已完成",
    "todos.markOpen": "标记为未完成",
    "todos.completed": "已完成",
    "todos.open": "未完成",
    "todos.steps": "{done}/{total} 步骤",
    "todos.expand": "展开步骤",
    "todos.collapse": "收起步骤",
    "todos.addStep": "添加步骤",
    "todos.newStep": "新建步骤",
    "todos.stepPlaceholder": "下一步做什么？",
    "todos.inheritHint": "分类与截止日期继承自父条目",
    "todos.errorCreateStep": "无法添加该步骤。",
    "todos.confirmDeleteSteps": "确认删除（含 {count} 个步骤）",

    // --- memories (rendered on the dashboard) -------------------------------
    "memories.derivedHint": "记忆由你每天填写的日志自动提炼，无需手动录入。",
    "memories.searchPlaceholder": "深度工作、Rust、健康…",
    "memories.searchResults": "搜索结果（{count}）",
    "memories.allMemories": "全部记忆",
    "memories.allCategories": "全部类型",
    "memories.importance": "重要度",
    "memories.noMatches": "没有匹配项。",
    "memories.empty": "暂无记忆。",
    "memories.errorSearch": "搜索失败。",

    // --- reports ------------------------------------------------------------
    "reports.title": "报告",
    "reports.subtitle": "从日志聚合出的日报、周报与月报。",
    "reports.daily": "日报",
    "reports.weekly": "周报",
    "reports.monthly": "月报",
    "reports.generate": "生成报告",
    "reports.generating": "正在生成…",
    "reports.scopeAll": "全部领域",
    "reports.empty": "暂无报告，点击「生成报告」创建一份。",
    "reports.selectPrompt": "从左侧选择一份报告查看详情。",
    "reports.journalCount": "日志数",
    "reports.activeDays": "有记录天数",
    "reports.period": "区间",
    "reports.breakdown": "类型分布",
    "reports.moods": "心情分布",
    "reports.todos": "涉及待办",
    "reports.memories": "本期沉淀记忆",
    "reports.highlights": "重点摘录",
    "reports.none": "本期没有记录。",
    "reports.errorGenerate": "生成报告失败。",
    "reports.errorLoad": "加载报告失败。",
    "reports.delete": "删除",
    "reports.dayCount": "{count} 天",
    "reports.summaryEmpty": "{period} 期间没有新的日志记录。",
    "reports.summaryHead": "{period} 共记录 {count} 篇日志，覆盖 {days} 天。",
    "reports.summaryCategories": "主要集中在 {top}。",
    "reports.summaryMood": "心情以 {mood} 为主。",
    "reports.summaryTodos": "涉及待办：{todos}。",
    "reports.summaryMemories": "本期沉淀 {count} 条长期记忆。",

    // --- settings -----------------------------------------------------------
    "settings.title": "设置",
    "settings.subtitle": "账号与工作区偏好设置。",
    "settings.profile": "个人信息",
    "settings.name": "姓名",
    "settings.email": "邮箱",
    "settings.timezone": "时区",
    "settings.locale": "语言",
    "settings.session": "会话",

    // --- copilot ------------------------------------------------------------
    "copilot.title": "AI 助手",
    "copilot.newChat": "新对话",
    "copilot.history": "历史",
    "copilot.back": "返回",
    "copilot.untitled": "未命名会话",
    "copilot.historyEmpty": "暂无历史会话。",
    "copilot.historyError": "无法加载历史会话。",
    "copilot.send": "发送",
    "copilot.context": "上下文：{label}",
    "copilot.close": "关闭",
    "copilot.askHint": "你可以问：",
    "copilot.placeholder": "就当前页面提问…",
    "copilot.tools": "工具：{tools}",
    "copilot.error": "请求失败。",
    "copilot.ctx.journal": "日志",
    "copilot.ctx.dashboard": "总览",
    "copilot.suggestion.0": "我还有哪些待办？",
    "copilot.suggestion.1": "我接下来该做什么？",
    "copilot.suggestion.2": "最近有哪些风险？",

    // --- not found ----------------------------------------------------------
    "notFound.body": "这个页面不存在，可能已经被合并进总览了。",
    "notFound.back": "回到总览",

    // --- chart --------------------------------------------------------------
    "chart.empty": "该周期内没有数据。",

    // --- categories (life domains, shared by journals/todos/memories) -------
    "category.WORK": "工作",
    "category.LEARNING": "学习",
    "category.INVESTMENT": "投资",
    "category.FINANCE": "财务",
    "category.HEALTH": "健康",
    "category.LIFE": "生活",
    "category.SOCIAL": "社交",
    "category.CREATIVE": "创作",
    "category.TRAVEL": "旅行",
    "category.OTHER": "其他",

    // --- enum values (API-controlled, mapped for display) -------------------
    "enum.WORK": "工作",
    "enum.LEARNING": "学习",
    "enum.LIFE": "生活",
    "enum.HEALTH": "健康",
    "enum.FINANCE": "财务",
    "enum.SOCIAL": "社交",
    "enum.TRAVEL": "旅行",
    "enum.PROJECT": "项目",
    "enum.THOUGHT": "思考",
    "enum.DECISION": "决策",
    "enum.ACHIEVEMENT": "成就",
    "enum.OTHER": "其他",
  },

  en: {
    "shell.loading": "Loading PersonalOS…",
    "shell.signOut": "Sign out",
    "shell.copilot": "AI Copilot",
    "shell.language": "Language",

    "login.title": "Sign in to PersonalOS",
    "login.hint": "Demo account is pre-filled when the backend seeds the demo user.",
    "login.email": "Email",
    "login.password": "Password",
    "login.submit": "Sign in",
    "login.submitting": "Signing in…",

    "common.loading": "Loading…",
    "common.saving": "Saving…",
    "common.searching": "Searching…",
    "common.generating": "Generating…",
    "common.generatingBtn": "Generate",
    "common.search": "Search",
    "common.clear": "Clear",
    "common.cancel": "Cancel",
    "common.content": "Content",
    "common.type": "Type",
    "common.title": "Title",
    "common.name": "Name",
    "common.description": "Description",
    "common.status": "Status",
    "common.priority": "Priority",
    "common.details": "Details",
    "common.history": "History",
    "common.summary": "Summary",
    "common.risks": "Risks",
    "common.recommendations": "Recommendations",
    "common.nextActions": "Next actions",
    "common.todos": "Todos",
    "common.events": "Events",
    "common.start": "Start",
    "common.end": "End",
    "common.selectHint": "Select an item to read it.",
    "common.optional": "Optional",
    "common.prev": "Previous",
    "common.next": "Next",
    "common.pageOf": "Page {page} of {total}",
    "common.delete": "Delete",

    "dashboard.title": "Dashboard",
    "dashboard.subtitle": "Your journals, todos and memories at a glance.",
    "dashboard.statJournals": "Journals (all time)",
    "dashboard.statMemories": "Memories",
    "dashboard.statOpenTodos": "Open todos",
    "dashboard.recentJournals": "Recent journals",
    "dashboard.recentJournalsHint": "Click an entry to open the journal page",
    "dashboard.viewReports": "View reports",
    "dashboard.errorStats": "Could not load statistics.",

    "journals.title": "Journals",
    "journals.subtitle": "Writing a journal triggers memory distillation over your recent activity.",
    "journals.newEntry": "New entry",
    "journals.entryTitle": "Entry title",
    "journals.entryContent": "What happened today?",
    "journals.saveEntry": "Save entry",
    "journals.allEntries": "All entries",
    "journals.entry": "Entry",
    "journals.empty": "No entries yet.",
    "journals.emptyCategory": "No entries in this category.",
    "journals.errorSave": "Could not save the entry.",

    "todos.title": "Todos",
    "todos.newTodo": "New todo",
    "todos.targetDate": "Due date",
    "todos.addTodo": "Add todo",
    "todos.empty": "No todos yet.",
    "todos.summary": "{open} open · {done} done",
    "todos.due": "due {date}",
    "todos.completedAt": "done {date}",
    "todos.placeholder": "Write a weekly retrospective",
    "todos.errorCreate": "Could not create the todo.",
    "todos.errorUpdate": "Could not update the todo.",
    "todos.errorDelete": "Could not delete the todo.",
    "todos.markDone": "Mark as done",
    "todos.markOpen": "Mark as open",
    "todos.completed": "Done",
    "todos.open": "Open",
    "todos.steps": "{done}/{total} steps",
    "todos.expand": "Show steps",
    "todos.collapse": "Hide steps",
    "todos.addStep": "Add step",
    "todos.newStep": "New step",
    "todos.stepPlaceholder": "What's the next step?",
    "todos.inheritHint": "Category and due date are inherited from the parent",
    "todos.errorCreateStep": "Could not add the step.",
    "todos.confirmDeleteSteps": "Confirm delete ({count} steps)",

    "memories.derivedHint": "Memories are distilled automatically from the journals you write.",
    "memories.searchPlaceholder": "deep work, Rust, health…",
    "memories.searchResults": "Search results ({count})",
    "memories.allMemories": "All memories",
    "memories.allCategories": "All categories",
    "memories.importance": "importance",
    "memories.noMatches": "No matches.",
    "memories.empty": "No memories yet.",
    "memories.errorSearch": "Search failed.",

    // --- reports ------------------------------------------------------------
    "reports.title": "Reports",
    "reports.subtitle": "Daily, weekly and monthly summaries aggregated from your journals.",
    "reports.daily": "Daily",
    "reports.weekly": "Weekly",
    "reports.monthly": "Monthly",
    "reports.generate": "Generate report",
    "reports.generating": "Generating…",
    "reports.scopeAll": "All domains",
    "reports.empty": "No reports yet — generate one to get started.",
    "reports.selectPrompt": "Pick a report on the left to see its detail.",
    "reports.journalCount": "Journal entries",
    "reports.activeDays": "Days with entries",
    "reports.period": "Period",
    "reports.breakdown": "Category breakdown",
    "reports.moods": "Mood breakdown",
    "reports.todos": "Todos touched",
    "reports.memories": "Memories distilled",
    "reports.highlights": "Highlights",
    "reports.none": "Nothing recorded this period.",
    "reports.errorGenerate": "Could not generate the report.",
    "reports.errorLoad": "Could not load reports.",
    "reports.delete": "Delete",
    "reports.dayCount": "{count} days",
    "reports.summaryEmpty": "No journal entries were recorded for {period}.",
    "reports.summaryHead": "{count} journal entries recorded over {period}, spread across {days} days.",
    "reports.summaryCategories": "Most active areas: {top}.",
    "reports.summaryMood": "Mood was mostly {mood}.",
    "reports.summaryTodos": "Todos touched: {todos}.",
    "reports.summaryMemories": "{count} long-term memories distilled this period.",

    "settings.title": "Settings",
    "settings.subtitle": "Account and workspace preferences.",
    "settings.profile": "Profile",
    "settings.name": "Name",
    "settings.email": "Email",
    "settings.timezone": "Timezone",
    "settings.locale": "Locale",
    "settings.session": "Session",

    "copilot.title": "AI Copilot",
    "copilot.newChat": "New chat",
    "copilot.history": "History",
    "copilot.back": "Back",
    "copilot.untitled": "Untitled",
    "copilot.historyEmpty": "No conversations yet.",
    "copilot.historyError": "Could not load conversation history.",
    "copilot.send": "Send",
    "copilot.context": "Context: {label}",
    "copilot.close": "Close",
    "copilot.askHint": "You can ask:",
    "copilot.placeholder": "Ask about this page…",
    "copilot.tools": "tools: {tools}",
    "copilot.error": "Request failed.",
    "copilot.ctx.journal": "Journal",
    "copilot.ctx.dashboard": "Dashboard",
    "copilot.suggestion.0": "Which todos are still open?",
    "copilot.suggestion.1": "What should I do next?",
    "copilot.suggestion.2": "What are the recent risks?",

    "notFound.body": "This page does not exist — it may have been folded into the dashboard.",
    "notFound.back": "Back to dashboard",

    "chart.empty": "No data for this period.",

    "category.WORK": "Work",
    "category.LEARNING": "Learning",
    "category.INVESTMENT": "Investment",
    "category.FINANCE": "Finance",
    "category.HEALTH": "Health",
    "category.LIFE": "Life",
    "category.SOCIAL": "Social",
    "category.CREATIVE": "Creative",
    "category.TRAVEL": "Travel",
    "category.OTHER": "Other",

    "enum.WORK": "WORK",
    "enum.LEARNING": "LEARNING",
    "enum.LIFE": "LIFE",
    "enum.HEALTH": "HEALTH",
    "enum.FINANCE": "FINANCE",
    "enum.SOCIAL": "SOCIAL",
    "enum.TRAVEL": "TRAVEL",
    "enum.PROJECT": "PROJECT",
    "enum.THOUGHT": "THOUGHT",
    "enum.DECISION": "DECISION",
    "enum.ACHIEVEMENT": "ACHIEVEMENT",
    "enum.OTHER": "OTHER",
  },
};

function readStoredLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "en" || stored === "zh" ? stored : DEFAULT_LOCALE;
}

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
}

export const useLocaleStore = create<LocaleState>((set, get) => ({
  locale: DEFAULT_LOCALE,

  setLocale(locale) {
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, locale);
    if (typeof document !== "undefined") document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    set({ locale });
  },

  toggleLocale() {
    get().setLocale(get().locale === "zh" ? "en" : "zh");
  },
}));

/** Rehydrate the persisted locale after mount (localStorage is client-only). */
export function useHydrateLocale(): void {
  const setLocale = useLocaleStore((state) => state.setLocale);
  useEffect(() => {
    const stored = readStoredLocale();
    setLocale(stored);
    // `setLocale` is stable in Zustand, so this runs once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

export type TranslateParams = Record<string, string | number>;

/**
 * Translate `key` into the active locale.
 *
 * Interpolation uses `{name}` placeholders. Unknown keys fall back to English,
 * then to the key itself, so a missing entry degrades visibly instead of
 * rendering blank.
 */
export function translate(locale: Locale, key: string, params?: TranslateParams): string {
  const template = dictionaries[locale][key] ?? dictionaries.en[key] ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
  );
}

/** Map an API enum value (memory type, numeric priority…) onto a display label. */
export function translateEnum(locale: Locale, value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return String(value);
  const key = `enum.${value.toUpperCase()}`;
  const label = dictionaries[locale][key] ?? dictionaries.en[key];
  return label ?? value;
}

/**
 * Map a life-domain category onto its display label.
 *
 * Deliberately not folded into `translateEnum`: the `enum.*` table is the
 * shared EventType vocabulary, where names like OTHER and FINANCE already
 * exist with different meanings.
 */
export function translateCategory(locale: Locale, value: string | null | undefined): string {
  const key = `category.${(value || "OTHER").toUpperCase()}`;
  return translate(locale, key);
}

/** Zero-argument strings still need the locale, so components use this hook. */
export function useT() {
  const locale = useLocaleStore((state) => state.locale);
  const t = (key: string, params?: TranslateParams) => translate(locale, key, params);
  const tEnum = (value: string | number | null | undefined) => translateEnum(locale, value);
  const tCategory = (value: string | null | undefined) => translateCategory(locale, value);
  return { t, tEnum, tCategory, locale };
}
