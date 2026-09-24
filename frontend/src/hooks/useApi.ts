"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Category, ReportGenerateRequest, ReportType, TodoCreate, TodoUpdate } from "@/types/api";

export const queryKeys = {
  // Keyed by filter so switching category refetches, while a bare
  // ["journals"] prefix still invalidates every variant.
  journals: (category?: Category) => ["journals", category ?? "all"] as const,
  // Keyed by the completion filter; a bare ["todos"] prefix invalidates all.
  todos: (completed?: boolean) =>
    ["todos", completed === undefined ? "all" : String(completed)] as const,
  memories: (category?: Category) => ["memories", category ?? "all"] as const,
  conversations: ["conversations"] as const,
  // Keyed by report type, so a bare ["reports"] prefix still invalidates all.
  reports: (type?: ReportType) => ["reports", type ?? "all"] as const,
};

export function useJournals(category?: Category) {
  return useQuery({
    queryKey: queryKeys.journals(category),
    queryFn: () => api.listJournals(category),
  });
}

export function useTodos(completed?: boolean) {
  return useQuery({
    queryKey: queryKeys.todos(completed),
    queryFn: () => api.listTodos({ completed }),
  });
}

export function useMemories(category?: Category) {
  return useQuery({
    queryKey: queryKeys.memories(category),
    queryFn: () => api.listMemories(category),
  });
}

export function useConversations() {
  return useQuery({ queryKey: queryKeys.conversations, queryFn: () => api.listConversations() });
}

export function useReports(type?: ReportType) {
  return useQuery({
    queryKey: queryKeys.reports(type),
    queryFn: () => api.listReports(type),
  });
}

/** Generate (or refresh) one period report. */
export function useGenerateReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ReportGenerateRequest) => api.generateReport(body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["reports"] }),
  });
}

export function useDeleteReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteReport(id),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["reports"] }),
  });
}

/** Invalidate every list a new journal can affect (journals feed memories). */
function useInvalidateActivity() {
  const client = useQueryClient();
  return () => {
    for (const key of [["journals"], ["todos"], ["memories"]]) {
      void client.invalidateQueries({ queryKey: key });
    }
  };
}

export function useCreateJournal() {
  // `useInvalidateActivity` already invalidates every journal/todo/memory
  // variant via the bare ["journals"] prefix key.
  const invalidate = useInvalidateActivity();
  return useMutation({
    mutationFn: (body: { title: string; content: string; category?: Category; mood?: string }) =>
      api.createJournal(body),
    onSuccess: () => invalidate(),
  });
}

/** Creating a todo only affects the todo lists, not the journal-derived data. */
function useInvalidateTodos() {
  const client = useQueryClient();
  return () => void client.invalidateQueries({ queryKey: ["todos"] });
}

export function useCreateTodo() {
  const invalidate = useInvalidateTodos();
  return useMutation({
    mutationFn: (body: TodoCreate) => api.createTodo(body),
    onSuccess: () => invalidate(),
  });
}

/** Check / uncheck: `completed: true` stamps `completed_at` server-side. */
export function useUpdateTodo() {
  const invalidate = useInvalidateTodos();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & TodoUpdate) => api.updateTodo(id, body),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteTodo() {
  const invalidate = useInvalidateTodos();
  return useMutation({
    mutationFn: (id: string) => api.deleteTodo(id),
    onSuccess: () => invalidate(),
  });
}
