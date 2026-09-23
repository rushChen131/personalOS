"use client";

import { useEffect } from "react";
import { create } from "zustand";

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

const STORAGE_KEY = "personalos.locale";

const dictionaries: Record<Locale, Record<string, string>> = {
  zh: {
    // --- shell / navigation -------------------------------------------------
    "nav.dashboard": "总览",
    "nav.settings": "设置",
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
    "common.goals": "目标",
    "common.events": "事件",
    "common.start": "开始",
    "common.end": "结束",
    "common.selectHint": "请选择一项查看内容。",
    "common.optional": "可选",
    "common.prev": "上一页",
    "common.next": "下一页",
    "common.pageOf": "第 {page} / {total} 页",

    // --- dashboard ----------------------------------------------------------
    "dashboard.title": "总览",
    "dashboard.subtitle": "一览你的日志、目标与记忆。",
    "dashboard.statJournals": "日志（累计）",
    "dashboard.statMemories": "记忆",
    "dashboard.statActiveGoals": "进行中目标",
    "dashboard.recentJournals": "最近日志",
    "dashboard.recentJournalsHint": "点击任意一条进入日志页",
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
    "journals.errorSave": "无法保存该日志。",

    // --- goals (rendered on the dashboard) ----------------------------------
    "goals.newGoal": "新建目标",
    "goals.targetDate": "目标日期",
    "goals.addGoal": "添加目标",
    "goals.empty": "暂无目标。",
    "goals.activeGoals": "进行中的目标",
    "goals.total": "共 {count} 个",
    "goals.due": "截止 {date}",
    "goals.placeholder": "发布 PersonalOS v1.2",
    "goals.errorCreate": "无法创建该目标。",

    // --- memories (rendered on the dashboard) -------------------------------
    "memories.derivedHint": "记忆由你每天填写的日志自动提炼，无需手动录入。",
    "memories.searchPlaceholder": "深度工作、Rust、健康…",
    "memories.searchResults": "搜索结果（{count}）",
    "memories.allMemories": "全部记忆",
    "memories.importance": "重要度",
    "memories.noMatches": "没有匹配项。",
    "memories.empty": "暂无记忆。",
    "memories.errorSearch": "搜索失败。",

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
    "copilot.suggestion.0": "为什么进度变慢了？",
    "copilot.suggestion.1": "我接下来该做什么？",
    "copilot.suggestion.2": "最近有哪些风险？",

    // --- chart --------------------------------------------------------------
    "chart.empty": "该周期内没有数据。",

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
    "nav.dashboard": "Dashboard",
    "nav.settings": "Settings",
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
    "common.goals": "Goals",
    "common.events": "Events",
    "common.start": "Start",
    "common.end": "End",
    "common.selectHint": "Select an item to read it.",
    "common.optional": "Optional",
    "common.prev": "Previous",
    "common.next": "Next",
    "common.pageOf": "Page {page} of {total}",

    "dashboard.title": "Dashboard",
    "dashboard.subtitle": "Your journals, goals and memories at a glance.",
    "dashboard.statJournals": "Journals (all time)",
    "dashboard.statMemories": "Memories",
    "dashboard.statActiveGoals": "Active goals",
    "dashboard.recentJournals": "Recent journals",
    "dashboard.recentJournalsHint": "Click an entry to open the journal page",
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
    "journals.errorSave": "Could not save the entry.",

    "goals.newGoal": "New goal",
    "goals.targetDate": "Target date",
    "goals.addGoal": "Add goal",
    "goals.empty": "No goals yet.",
    "goals.activeGoals": "Active goals",
    "goals.total": "{count} total",
    "goals.due": "due {date}",
    "goals.placeholder": "Ship PersonalOS v1.2",
    "goals.errorCreate": "Could not create the goal.",

    "memories.derivedHint": "Memories are distilled automatically from the journals you write.",
    "memories.searchPlaceholder": "deep work, Rust, health…",
    "memories.searchResults": "Search results ({count})",
    "memories.allMemories": "All memories",
    "memories.importance": "importance",
    "memories.noMatches": "No matches.",
    "memories.empty": "No memories yet.",
    "memories.errorSearch": "Search failed.",

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
    "copilot.suggestion.0": "Why did progress slow down?",
    "copilot.suggestion.1": "What should I do next?",
    "copilot.suggestion.2": "What are the recent risks?",

    "chart.empty": "No data for this period.",

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

/** Map an API enum value (event type, goal status, numeric priority…) onto a display label. */
export function translateEnum(locale: Locale, value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return String(value);
  const key = `enum.${value.toUpperCase()}`;
  const label = dictionaries[locale][key] ?? dictionaries.en[key];
  return label ?? value;
}

/** Zero-argument strings still need the locale, so components use this hook. */
export function useT() {
  const locale = useLocaleStore((state) => state.locale);
  const t = (key: string, params?: TranslateParams) => translate(locale, key, params);
  const tEnum = (value: string | number | null | undefined) => translateEnum(locale, value);
  return { t, tEnum, locale };
}
