# Hook Guidelines

> How hooks are used in this project.

---

## Overview

Two hook modules exist, with a hard split:

- **`hooks/useApi.ts`** — *all* server state. Every query and mutation for the
  app lives here, exported per entity.
- **`hooks/useSession.ts`** — lifecycle glue for the auth store.

Components consume these; they never define their own data-fetching hooks.

---

## Custom Hook Patterns

A data hook is a one-liner over the typed API client, so the query key and the
fetcher can never drift apart:

```ts
export function useMemories(type?: string) {
  return useQuery({ queryKey: queryKeys.memories(type), queryFn: () => api.listMemories(type) });
}
```

A mutation hook wires invalidation in the same place it defines the write:

```ts
export function useCreateEvent() {
  const invalidate = useInvalidateActivity();
  return useMutation({
    mutationFn: (body: { title: string; type?: string }) => api.createEvent(body),
    onSuccess: invalidate,
  });
}
```

When several mutations share a side effect, extract one private helper
(`useInvalidateActivity`) rather than repeating the key list.

---

## Data Fetching

Server state is **TanStack Query**. Rules:

1. Every query has a stable key from the exported `queryKeys` object — never an
   inline string.
2. Keys include the parameters that change the result (`memories(type)`), so
   caches do not collide.
3. Mutations invalidate the keys they affect; use `useInvalidateActivity()` for
   anything activity-derived.
4. Defaults (`staleTime`, `retry`, `refetchOnWindowFocus`) are set once in
   `app/providers.tsx` — do not override them per hook without a reason.
5. Loading and error states are rendered explicitly (`EmptyState` / `ErrorState`),
   never as a bare spinner with no text.

**Streaming is the exception.** `POST /chat` is SSE, which `EventSource` cannot
do (it only issues GET and cannot set an `Authorization` header). `lib/sse.ts`
therefore exposes an async generator that reads the response body directly:

```ts
for await (const event of streamChat(message, { conversationId })) {
  // event.event is start | thinking | tool_call | tool_result | content | done | error
}
```

Consume it inside an event handler with a local `busy` flag; do not model the
stream as a query.

---

## Naming Conventions

| Kind | Pattern | Example |
|---|---|---|
| Read hook | `use` + plural entity | `useGoals`, `useMemories` |
| Mutation hook | `use` + verb + entity | `useCreateEvent`, `useGenerateReport` |
| Private helper | `use` + effect | `useInvalidateActivity` |
| Query key | `queryKeys.<entity>(params)` | `queryKeys.memories(type)` |

---

## Common Mistakes

- **Fetching in `useEffect`.** Use TanStack Query; manual effects lose caching,
  dedupe and invalidation.
- **Inline query keys** (`useQuery({ queryKey: ["goals"] })`) scattered across
  files — invalidation then silently misses. Always go through `queryKeys`.
- **Forgetting invalidation**, so a new event does not refresh the dashboard.
- **Awaiting a mutation and reading its result as truth.** The authoritative data
  is the invalidated query; let it refetch.
- **Calling `streamChat` in a `useEffect`** without an abort guard, which leaks a
  reader on unmount. Pass `signal` from an `AbortController`.

---

## Related

- [State Management](./state-management.md)
- [Directory Structure](./directory-structure.md)
