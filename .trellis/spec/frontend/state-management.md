# State Management

> How state is managed in this project.

---

## Overview

State is split into exactly three layers. The rule that decides which one to use:
**if the backend owns the data, it is server state — never mirror it into a store.**

---

## State Categories

| Layer | Tool | Where | Use for |
|---|---|---|---|
| Server state | TanStack Query | `src/hooks/useApi.ts` | Anything the API owns |
| Global client state | Zustand | `src/stores/*` | Auth/session only |
| Local UI state | `useState` | Component | Form inputs, selection, toggles |

URL state is not used yet; route params are read via `usePathname` in
`components/AppShell.tsx`.

---

## Server State

All queries and mutations live in `src/hooks/useApi.ts` and are keyed through the
exported `queryKeys` object.

```ts
export const queryKeys = {
  journals: (category?: Category) => ["journals", category ?? "all"] as const,
  todos: (completed?: boolean) => ["todos", completed === undefined ? "all" : String(completed)] as const,
  // ...
};

export function useTodos(completed?: boolean) {
  return useQuery({
    queryKey: queryKeys.todos(completed),
    queryFn: () => api.listTodos({ completed }),
  });
}
```

**Mutations invalidate what they affect.** Creating a journal changes journals
*and* memories — because the backend triggers the embedding + memory-analysis
jobs on `JournalCreated`. Todos are independent of that pipeline, so they get
their own helper. The fan-out lives in a single helper so no mutation forgets a
key:

```ts
function useInvalidateActivity() {
  const client = useQueryClient();
  return () => {
    for (const key of [["journals"], ["todos"], ["memories"]]) {
      void client.invalidateQueries({ queryKey: key });
    }
  };
}
```

Defaults are set once in `app/providers.tsx`: `staleTime: 30_000`,
`refetchOnWindowFocus: false`, `retry: 1`.

---

## When to Use Global State

Only two justifications:

1. **Non-React code must read it.** The auth token qualifies: `lib/api.ts` is a
   plain module, so it reads the token from `localStorage` via `getToken()`.
2. **Many distant components must agree**, and prop-drilling would cross three or
   more levels.

Everything else is local or server state. There is currently **one** Zustand
store (`stores/auth.ts`) and adding a second requires a reason from the list above.

---

## Common Mistakes

- **Copying query data into `useState`.** It goes stale immediately and breaks
  invalidation. Render from the query result instead.
- **Calling `fetch` in a component.** All HTTP goes through `lib/api.ts`.
- **Forgetting cache invalidation.** If a mutation changes a list, invalidate its
  key — use `useInvalidateActivity()` for anything activity-related.
- **Storing the auth token in Zustand.** It would not survive a reload for the
  non-React client; use `localStorage` through `getToken`/`setToken`.
- **Widening `staleTime` to hide flicker.** Fix the query key instead.

---

## Related

- [Hook Guidelines](./hook-guidelines.md)
- [Directory Structure](./directory-structure.md)
