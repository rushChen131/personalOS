"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useParams } from "next/navigation";
import { api } from "@/lib/api";
import { streamChat, type ChatStreamEvent } from "@/lib/sse";
import { useAuthStore } from "@/stores/auth";
import { useT } from "@/lib/i18n";
import type { Conversation } from "@/types/api";

/** Map a route onto the context object the backend expects (design2.md §53). */
function useContextTarget(): { type: string; id: string | null; labelKey: string } {
  const pathname = usePathname();
  const params = useParams<{ id?: string }>();
  const id = params?.id ?? null;

  if (pathname.startsWith("/goals")) {
    return { type: "goal", id, labelKey: id ? "copilot.ctx.goal" : "copilot.ctx.goals" };
  }
  if (pathname.startsWith("/insights")) return { type: "insight", id, labelKey: "copilot.ctx.insights" };
  if (pathname.startsWith("/memories")) return { type: "memory", id, labelKey: "copilot.ctx.memory" };
  if (pathname.startsWith("/journals")) return { type: "journal", id, labelKey: "copilot.ctx.journal" };
  return { type: "dashboard", id: null, labelKey: "copilot.ctx.dashboard" };
}

const SUGGESTION_KEYS = ["copilot.suggestion.0", "copilot.suggestion.1", "copilot.suggestion.2"];

interface Turn {
  role: "user" | "assistant";
  content: string;
  tools?: string[];
}

type View = "chat" | "history";

export function CopilotPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useT();
  const status = useAuthStore((state) => state.status);
  const target = useContextTarget();
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<View>("chat");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns]);

  // Context changes when the user navigates between pages (§53).
  useEffect(() => {
    setConversationId(undefined);
  }, [target.type, target.id]);

  // The panel closes and reopens freely, so drop stale history state on close.
  useEffect(() => {
    if (!open) setView("chat");
  }, [open]);

  async function openHistory() {
    setView("history");
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      setConversations(await api.listConversations());
    } catch {
      setHistoryError(t("copilot.historyError"));
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadConversation(id: string) {
    setBusy(true);
    try {
      const { messages } = await api.getConversation(id);
      setConversationId(id);
      setTurns(
        messages
          .filter((item) => item.role === "user" || item.role === "assistant")
          .map((item) => ({ role: item.role as "user" | "assistant", content: item.content })),
      );
      setView("chat");
    } catch {
      setHistoryError(t("copilot.historyError"));
    } finally {
      setBusy(false);
    }
  }

  function startNewConversation() {
    setConversationId(undefined);
    setTurns([]);
    setView("chat");
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setBusy(true);
    setMessage("");
    const userTurn: Turn = { role: "user", content: text.trim() };
    // Placeholder assistant turn filled in as SSE frames arrive.
    setTurns((prev) => [...prev, userTurn, { role: "assistant", content: "", tools: [] }]);

    const patch = (fn: (last: Turn) => Turn) =>
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = fn(next[next.length - 1]);
        return next;
      });

    try {
      for await (const event of streamChat(text.trim(), {
        conversationId,
        context: { type: target.type, id: target.id },
      }) satisfies AsyncGenerator<ChatStreamEvent>) {
        if (event.event === "start") {
          setConversationId(event.data.conversation_id);
        } else if (event.event === "tool_call") {
          patch((last) => ({ ...last, tools: [...(last.tools ?? []), event.data.name] }));
        } else if (event.event === "content") {
          patch((last) => ({ ...last, content: last.content + event.data.content }));
        } else if (event.event === "error") {
          patch((last) => ({ ...last, content: t("copilot.error") }));
        }
      }
    } catch {
      patch((last) => ({ ...last, content: last.content || t("copilot.error") }));
    } finally {
      setBusy(false);
    }
  }

  if (!open || status !== "authenticated") return null;

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-surface-border bg-surface">
      <header className="flex items-center justify-between border-b border-surface-border px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{t("copilot.title")}</p>
          <p className="truncate text-xs text-ink-muted">
            {view === "history" ? t("copilot.history") : t("copilot.context", { label: t(target.labelKey) })}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {view === "history" ? (
            <button
              type="button"
              onClick={() => setView("chat")}
              className="rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-surface-muted"
            >
              {t("copilot.back")}
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={startNewConversation}
                className="rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-surface-muted"
              >
                {t("copilot.newChat")}
              </button>
              <button
                type="button"
                onClick={() => void openHistory()}
                className="rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-surface-muted"
              >
                {t("copilot.history")}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-surface-muted"
          >
            {t("copilot.close")}
          </button>
        </div>
      </header>

      {view === "history" ? (
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {historyLoading ? <p className="text-xs text-ink-muted">{t("common.loading")}</p> : null}
          {historyError ? <p className="text-xs text-danger">{historyError}</p> : null}
          {!historyLoading && !historyError && conversations.length === 0 ? (
            <p className="text-xs text-ink-muted">{t("copilot.historyEmpty")}</p>
          ) : null}
          {conversations.length ? (
            <ul className="space-y-1">
              {conversations.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => void loadConversation(conversation.id)}
                    className={`w-full rounded-md px-2.5 py-2 text-left text-sm ${
                      conversationId === conversation.id ? "bg-accent-soft text-accent" : "hover:bg-surface-muted"
                    }`}
                  >
                    <span className="block truncate">{conversation.title ?? t("copilot.untitled")}</span>
                    <span className="mt-0.5 block text-[10px] text-ink-muted">
                      {conversation.updated_at.slice(0, 16).replace("T", " ")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <>
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {turns.length === 0 ? (
              <div className="space-y-2">
                <p className="text-xs text-ink-muted">{t("copilot.askHint")}</p>
                {SUGGESTION_KEYS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => void send(t(key))}
                    className="block w-full rounded-md border border-surface-border px-3 py-2 text-left text-xs text-ink-muted hover:bg-surface-muted"
                  >
                    {t(key)}
                  </button>
                ))}
              </div>
            ) : null}

            {turns.map((turn, index) => (
              <div key={index} className={turn.role === "user" ? "text-right" : ""}>
                <div
                  className={`inline-block max-w-full whitespace-pre-wrap rounded-lg px-3 py-2 text-left text-sm ${
                    turn.role === "user" ? "bg-accent text-white" : "bg-surface-muted"
                  }`}
                >
                  {turn.content || (busy && index === turns.length - 1 ? "…" : "")}
                </div>
                {turn.tools?.length ? (
                  <p className="mt-1 text-xs text-ink-muted">{t("copilot.tools", { tools: turn.tools.join(", ") })}</p>
                ) : null}
              </div>
            ))}
          </div>

          <form
            className="flex gap-2 border-t border-surface-border px-4 py-3"
            onSubmit={(event) => {
              event.preventDefault();
              void send(message);
            }}
          >
            <input
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder={t("copilot.placeholder")}
              className="flex-1 rounded-md border border-surface-border px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {t("copilot.send")}
            </button>
          </form>
        </>
      )}
    </aside>
  );
}
