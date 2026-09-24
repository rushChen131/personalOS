/**
 * Types mirroring the backend's `{success, data, request_id}` envelope and the
 * entity schemas in `app/schemas/common.py`. Keep field names identical to the
 * API so no translation layer is needed.
 *
 * Verified field-by-field against `backend/app/schemas/common.py` — when the
 * backend schema changes, update the matching interface here in the same commit.
 */

export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  request_id: string;
}

export interface ApiErrorBody {
  success: false;
  error: { code: string; message: string };
  request_id: string;
}

/** `UserResponse`. `email` is nullable for users created without one. */
export interface User {
  id: string;
  email: string | null;
  name: string;
  timezone: string;
  locale: string;
}

/** `TokenResponse`. The backend does not emit `expires_in` today. */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
}

/**
 * Life domain shared by journals, todos and memories (`models/base.py::Category`).
 * Stored as a plain string, so the backend can add members without a migration.
 */
export type Category =
  | "WORK"
  | "LEARNING"
  | "INVESTMENT"
  | "FINANCE"
  | "HEALTH"
  | "LIFE"
  | "SOCIAL"
  | "CREATIVE"
  | "TRAVEL"
  | "OTHER";

/** `JournalCreate`. */
export interface JournalCreate {
  title?: string | null;
  content: string;
  category?: Category;
  source?: string;
  mood?: string | null;
  occurred_at?: string | null;
  metadata?: Record<string, unknown>;
}

/** `JournalResponse`. */
export interface Journal {
  id: string;
  title: string | null;
  content: string;
  category: string;
  source: string;
  mood: string | null;
  occurred_at: string | null;
  created_at: string;
}

/** `TodoCreate`. */
export interface TodoCreate {
  title: string;
  description?: string | null;
  why?: string | null;
  category?: Category;
  priority?: number;
  start_date?: string | null;
  target_date?: string | null;
  /**
   * Set to make this a step of another todo. A step keeps only its title:
   * `category` and `target_date` are copied from the parent and any values sent
   * alongside are ignored. One level only — a step cannot own steps.
   */
  parent_id?: string | null;
}

/** `TodoUpdate`. `completed` is the check/uncheck intent. */
export interface TodoUpdate {
  title?: string;
  description?: string | null;
  why?: string | null;
  category?: Category;
  priority?: number;
  start_date?: string | null;
  target_date?: string | null;
  /** True stamps `completed_at` server-side; false clears it. */
  completed?: boolean;
}

/**
 * `TodoResponse`. A checklist item, so completion is one nullable timestamp:
 * `null` means open, a value means done *and* says when.
 *
 * `children` are the steps of a top-level todo; a step itself always has an
 * empty array. `GET /todos` returns top-level rows only, so a step never shows
 * up as a row of its own. Completion is independent across the edge — ticking a
 * parent leaves its steps alone and vice versa.
 */
export interface Todo {
  id: string;
  title: string;
  description: string | null;
  why: string | null;
  category: string;
  priority: number;
  start_date: string | null;
  target_date: string | null;
  completed_at: string | null;
  created_at: string;
  /** `null` for a top-level todo; the parent's id for a step. */
  parent_id: string | null;
  children: Todo[];
}

export interface MemorySearchRequest {
  query?: string | null;
  memory_type?: string | null;
  category?: Category | null;
  importance_min?: number | null;
  from_time?: string | null;
  to_time?: string | null;
  limit?: number;
  offset?: number;
}

/** `MemoryResponse`. */
export interface Memory {
  id: string;
  type: string;
  category: string;
  content: string;
  summary: string | null;
  confidence: number;
  importance: number;
  source_count: number;
  valid_from: string | null;
  valid_to: string | null;
  last_verified_at: string | null;
  created_at: string;
}

/** `ConversationResponse`. */
export interface Conversation {
  id: string;
  title: string | null;
  context_type: string | null;
  context_id: string | null;
  created_at: string;
  updated_at: string;
}

/** `MessageResponse`. */
export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface ChatContext {
  type: string;
  id: string | null;
}

/** `ContextResponse` — the page/object-scoped Copilot context (§53). */
export interface ContextResponse {
  page: string;
  object: { type: string | null; id: string | null };
  related_journals: Journal[];
  related_memories: Memory[];
}

/** `HealthResponse`. */
export interface HealthResponse {
  status: string;
  database: string;
  version: string;
}

/** The periods the report engine can aggregate. */
export type ReportType = "DAILY" | "WEEKLY" | "MONTHLY";

/** `ReportGenerateRequest`. Omitting the dates uses the period containing today. */
export interface ReportGenerateRequest {
  type: ReportType;
  /** `ALL` (or omitted) covers every life domain. */
  dimension?: Category | null;
  period_start?: string | null;
  period_end?: string | null;
}

export interface ReportHighlight {
  journal_id: string;
  title: string | null;
  excerpt: string;
  occurred_at: string | null;
}

export interface ReportTodoRef {
  id: string;
  title: string;
  category: string;
  completed: boolean;
  completed_at: string | null;
}

export interface ReportMemoryRef {
  id: string;
  content: string;
  category: string;
}

/** The fixed `content` contract the engine emits for every report. */
export interface ReportContent {
  period: { start: string; end: string; days: number };
  journal_count: number;
  active_days: number;
  /** Counts keyed by category, ordered by size then key. */
  category_breakdown: Record<string, number>;
  mood_breakdown: Record<string, number>;
  todos: ReportTodoRef[];
  memories: ReportMemoryRef[];
  highlights: ReportHighlight[];
}

/** `ReportResponse`. */
export interface Report {
  id: string;
  type: string;
  /** `ALL` or a `Category` value. */
  dimension: string;
  period_start: string;
  period_end: string;
  title: string;
  summary: string | null;
  content: ReportContent;
  status: string;
  created_at: string;
  updated_at: string;
}
