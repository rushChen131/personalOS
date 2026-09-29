import type {
  ApiEnvelope,
  ApiErrorBody,
  Category,
  ContextResponse,
  Conversation,
  Journal,
  Memory,
  MemorySearchRequest,
  Message,
  Report,
  ReportGenerateRequest,
  ReportType,
  Todo,
  TodoCreate,
  TodoUpdate,
  TokenResponse,
  User,
} from "@/types/api";

const TOKEN_KEY = "personalos.token";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

/** Resolve the API base: direct backend origin, else the Next.js rewrite. */
function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    // Browser: go through the Next dev rewrite to avoid CORS entirely.
    return "/api/backend";
  }
  return configured ? `${configured}/api/v1` : "http://localhost:8000/api/v1";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${apiBase()}${path}`, { ...init, headers });
  const text = await response.text();
  const payload = text ? (JSON.parse(text) as ApiEnvelope<T> | ApiErrorBody) : null;

  if (!response.ok || (payload && "success" in payload && payload.success === false)) {
    const errorBody = payload as ApiErrorBody | null;
    throw new ApiError(
      errorBody?.error?.code ?? "HTTP_ERROR",
      errorBody?.error?.message ?? response.statusText,
      response.status,
    );
  }
  return (payload as ApiEnvelope<T>).data;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  // auth
  bootstrap: () => request<{ needs_setup: boolean }>("/auth/bootstrap"),
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", json({ email, password })),
  me: () => request<User>("/auth/me"),

  // journals
  listJournals: (category?: Category) =>
    request<Journal[]>(`/journals${category ? `?category=${category}` : ""}`),
  createJournal: (body: { title: string; content: string; category?: Category; mood?: string }) =>
    request<Journal>("/journals", json(body)),
  getJournal: (id: string) => request<Journal>(`/journals/${id}`),
  deleteJournal: (id: string) => request<{ id: string }>(`/journals/${id}`, { method: "DELETE" }),

  // todos
  listTodos: (params: { completed?: boolean; category?: Category } = {}) => {
    const query = new URLSearchParams();
    if (params.completed !== undefined) query.set("completed", String(params.completed));
    if (params.category) query.set("category", params.category);
    const suffix = query.toString();
    return request<Todo[]>(`/todos${suffix ? `?${suffix}` : ""}`);
  },
  createTodo: (body: TodoCreate) => request<Todo>("/todos", json(body)),
  getTodo: (id: string) => request<Todo>(`/todos/${id}`),
  /** Also the check/uncheck call: `{ completed: true }` stamps `completed_at`. */
  updateTodo: (id: string, body: TodoUpdate) =>
    request<Todo>(`/todos/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTodo: (id: string) => request<{ deleted: boolean }>(`/todos/${id}`, { method: "DELETE" }),

  // memories
  listMemories: (category?: Category) =>
    request<Memory[]>(`/memories${category ? `?category=${category}` : ""}`),
  /** Hybrid search. `query` may be omitted to browse by category alone. */
  searchMemories: (body: MemorySearchRequest) =>
    request<Memory[]>("/memories/search", json(body)),
  getMemory: (id: string) => request<Memory>(`/memories/${id}`),
  /** Memories are derived rather than authored, so delete is the only write path. */
  deleteMemory: (id: string) => request<{ deleted: boolean }>(`/memories/${id}`, { method: "DELETE" }),

  // reports
  listReports: (type?: ReportType) =>
    request<Report[]>(`/reports${type ? `?type=${type}` : ""}`),
  getReport: (id: string) => request<Report>(`/reports/${id}`),
  /** Build the report for a period; regenerating the same period refreshes it. */
  generateReport: (body: ReportGenerateRequest) =>
    request<Report>("/reports/generate", json(body)),
  deleteReport: (id: string) => request<{ deleted: boolean }>(`/reports/${id}`, { method: "DELETE" }),

  // chat
  listConversations: () => request<Conversation[]>("/chat/conversations"),
  createConversation: (title?: string) => {
    const query = title ? `?title=${encodeURIComponent(title)}` : "";
    return request<Conversation>(`/chat/conversations${query}`, { method: "POST" });
  },
  getConversation: (id: string) =>
    request<{ conversation: Conversation; messages: Message[] }>(`/chat/conversations/${id}`),

  // context
  context: (page = "dashboard", objectType?: string, objectId?: string) => {
    const query = new URLSearchParams({ page });
    if (objectType) query.set("object_type", objectType);
    if (objectId) query.set("object_id", objectId);
    return request<ContextResponse>(`/context?${query.toString()}`);
  },
};
