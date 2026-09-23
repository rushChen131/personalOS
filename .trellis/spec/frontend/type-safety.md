# Type Safety

> Type safety patterns in this project.

---

## Overview

TypeScript with `strict: true`. Types are the contract with the backend: the
files in `src/types/api.ts` mirror `backend/app/schemas/common.py` field-for-field,
so no runtime translation layer is needed.

---

## Type Organization

| Where | What |
|---|---|
| `src/types/api.ts` | Every backend entity + the response envelope |
| Component file | Props for a component used in one place |
| `hooks/useApi.ts` | Mutation payload types, inferred from the API client |
| `lib/*.ts` | Return types of the client's own functions |

**Backend shape changes start here.** If the API returns a new field, add it to
`types/api.ts` first; TypeScript then points at every place that needs updating.

---

## The Response Envelope

Every non-SSE endpoint returns `{success, data, request_id}`, and errors return
`{success: false, error: {code, message}, request_id}`:

```ts
export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  request_id: string;
}
```

The generic is unwrapped once, in `lib/api.ts`, so callers receive `T` directly:

```ts
export const api = {
  listGoals: () => request<Goal[]>("/goals"),
};
```

Never re-check `success` at a call site — `request` throws `ApiError` instead, and
the caller catches one error type:

```ts
class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) { /* ... */ }
}
```

---

## Validation

There is no runtime validation library. The trust boundary is `lib/api.ts`, which:

1. Parses the response body with `JSON.parse` inside a typed wrapper.
2. Converts the envelope or error body into either `T` or a thrown `ApiError`.
3. Is the only module allowed to construct `RequestInit` / read `fetch`.

Form input is validated with the HTML constraint attributes already present
(`type="email"`, `type="number"`, `min`, `required`) plus an explicit guard before
mutating. All domain validation stays server-side — the backend rejects invalid
payloads with a typed error code, and the UI surfaces `error.message`.

---

## Common Patterns

**Union types for closed sets.** Event types, memory types and goal statuses are
unions, not `string`:

```ts
export type EventType = "WORK" | "LEARNING" | "LIFE" | /* ... */ "OTHER";
export type GoalStatus = "ACTIVE" | "COMPLETED" | "PAUSED" | "ABANDONED";
```

Keeping the union in sync with the backend enum makes an invalid value a compile
error at the call site.

**Nullable is explicit.** Backend `Optional[...]` fields are `T | null`, never
`?` — the key is always present in JSON, only the value may be null:

```ts
export interface Event {
  project_id: string | null;
  duration_minutes: number | null;
}
```

**Discriminated unions for stream events.** `ChatStreamEvent` in `lib/sse.ts` is a
union on `event`, so `switch (item.event)` narrows `item.data` automatically.

**`as const` for key factories**, `Record<string, T>` for maps whose keys come
from data (e.g. `by_type`).

---

## Forbidden Patterns

| Pattern | Why | Instead |
|---|---|---|
| `any` | Erases the contract at the exact boundary that needs it | `unknown` + a narrowing guard, or add the type to `types/api.ts` |
| `as SomeType` on API data | Hides a real backend drift | Fix the type definition |
| `@ts-ignore` / `@ts-expect-error` | Silences without fixing | Correct the type |
| `object` / `{}` as a prop type | Accepts anything | Name the fields |
| Optional (`?`) for backend nullables | Wrongly implies the key may be absent | `T \| null` |
| Duplicating a backend shape in a component | Two sources of truth | Import from `types/api.ts` |

---

## Related

- [State Management](./state-management.md)
- [Directory Structure](./directory-structure.md)
