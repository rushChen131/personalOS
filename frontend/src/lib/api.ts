import type {
  ApiEnvelope,
  ApiErrorBody,
  ContextResponse,
  Conversation,
  Goal,
  Insight,
  Journal,
  Memory,
  Message,
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
  listJournals: () => request<Journal[]>("/journals"),
  createJournal: (body: { title: string; content: string; mood?: string }) =>
    request<Journal>("/journals", json(body)),
  getJournal: (id: string) => request<Journal>(`/journals/${id}`),
  deleteJournal: (id: string) => request<{ id: string }>(`/journals/${id}`, { method: "DELETE" }),

  // goals
  listGoals: () => request<Goal[]>("/goals"),
  createGoal: (body: { title: string; description?: string; target_date?: string }) =>
    request<Goal>("/goals", json(body)),
  getGoal: (id: string) => request<Goal>(`/goals/${id}`),
  updateGoal: (id: string, body: Partial<Goal> & { priority?: number }) =>
    request<Goal>(`/goals/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteGoal: (id: string) => request<{ id: string }>(`/goals/${id}`, { method: "DELETE" }),

  // memories
  listMemories: (type?: string) => request<Memory[]>(`/memories${type ? `?type=${type}` : ""}`),
  searchMemories: (query: string, limit = 20) =>
    request<Memory[]>("/memories/search", json({ query, limit })),
  getMemory: (id: string) => request<Memory>(`/memories/${id}`),

  // insights
  listInsights: () => request<Insight[]>("/insights"),

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
