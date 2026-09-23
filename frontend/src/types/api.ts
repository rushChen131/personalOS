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

/** `JournalCreate`. */
export interface JournalCreate {
  title?: string | null;
  content: string;
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
  source: string;
  mood: string | null;
  occurred_at: string | null;
  created_at: string;
}

export interface GoalCreate {
  title: string;
  description?: string | null;
  why?: string | null;
  priority?: number;
  start_date?: string | null;
  target_date?: string | null;
}

export interface GoalUpdate {
  title?: string;
  description?: string | null;
  why?: string | null;
  status?: string;
  priority?: number;
  start_date?: string | null;
  target_date?: string | null;
  /** 0–100 (see `models/project.py` CHECK constraint). */
  progress?: number;
}

/** `GoalResponse`. `progress` is 0–100, not 0–1. */
export interface Goal {
  id: string;
  title: string;
  description: string | null;
  why: string | null;
  status: "ACTIVE" | "COMPLETED" | "PAUSED" | "ABANDONED";
  priority: number;
  progress: number;
  start_date: string | null;
  target_date: string | null;
  created_at: string;
}

export interface MetricCreate {
  name: string;
  metric_type: string;
  current_value?: number | null;
  target_value?: number | null;
  unit?: string | null;
  weight?: number;
}

/** `MetricResponse` (backed by the `GoalMetric` model). */
export interface Metric {
  id: string;
  goal_id: string;
  name: string;
  metric_type: string;
  current_value: number | null;
  target_value: number | null;
  unit: string | null;
  weight: number;
}
export interface MemorySearchRequest {
  query?: string | null;
  memory_type?: string | null;
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
