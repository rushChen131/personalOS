import { getToken } from "@/lib/api";

/**
 * SSE event contract emitted by `POST /api/v1/chat`.
 *
 * start -> thinking -> (tool_call -> tool_result)* -> content -> done
 * An `error` event may replace `done` when the agent run fails.
 */
export type ChatStreamEvent =
  | { event: "start"; data: { conversation_id: string; agent: string } }
  | { event: "thinking"; data: { agent: string } }
  | { event: "tool_call"; data: { name: string; arguments: Record<string, unknown> } }
  | { event: "tool_result"; data: { name: string; result: Record<string, unknown> } }
  | { event: "content"; data: { content: string } }
  | { event: "done"; data: { conversation_id: string; success: boolean; agent?: string } }
  | { event: "error"; data: { message: string } };

function apiBase(): string {
  if (typeof window !== "undefined") return "/api/backend";
  const configured = process.env.NEXT_PUBLIC_API_URL;
  return configured ? `${configured}/api/v1` : "http://localhost:8000/api/v1";
}

function parseChunk(raw: string): ChatStreamEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) } as ChatStreamEvent;
  } catch {
    return null;
  }
}

/**
 * POST to the chat endpoint and yield parsed SSE events.
 *
 * `EventSource` only supports GET, and the chat endpoint needs an auth header,
 * so the stream is read manually from the fetch response body.
 */
export async function* streamChat(
  message: string,
  options: { conversationId?: string; context?: { type: string; id: string | null }; signal?: AbortSignal } = {},
): AsyncGenerator<ChatStreamEvent> {
  const token = getToken();
  const response = await fetch(`${apiBase()}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message,
      conversation_id: options.conversationId ?? null,
      context: options.context ?? { type: "chat", id: null },
    }),
    signal: options.signal,
  });

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    yield { event: "error", data: { message: text || response.statusText } };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line.
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseChunk(frame);
      if (parsed) yield parsed;
      boundary = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) {
    const parsed = parseChunk(buffer);
    if (parsed) yield parsed;
  }
}
