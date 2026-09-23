"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export const queryKeys = {
  journals: ["journals"] as const,
  goals: ["goals"] as const,
  memories: (type?: string) => ["memories", type ?? "all"] as const,
  conversations: ["conversations"] as const,
};

export function useJournals() {
  return useQuery({ queryKey: queryKeys.journals, queryFn: () => api.listJournals() });
}

export function useGoals() {
  return useQuery({ queryKey: queryKeys.goals, queryFn: () => api.listGoals() });
}

export function useMemories(type?: string) {
  return useQuery({ queryKey: queryKeys.memories(type), queryFn: () => api.listMemories(type) });
}

export function useConversations() {
  return useQuery({ queryKey: queryKeys.conversations, queryFn: () => api.listConversations() });
}

/** Invalidate every list a new journal can affect (journals feed memories). */
function useInvalidateActivity() {
  const client = useQueryClient();
  return () => {
    for (const key of [["journals"], ["goals"], ["memories"]]) {
      void client.invalidateQueries({ queryKey: key });
    }
  };
}

export function useCreateJournal() {
  const invalidate = useInvalidateActivity();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; content: string; mood?: string }) => api.createJournal(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.journals });
      invalidate();
    },
  });
}

export function useCreateGoal() {
  const invalidate = useInvalidateActivity();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; description?: string; target_date?: string }) => api.createGoal(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.goals });
      invalidate();
    },
  });
}
