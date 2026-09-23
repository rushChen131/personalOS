# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

Quality gates, all runnable from the repo root:

```bash
make typecheck   # tsc --noEmit  — must be clean
make lint        # next lint     — must be clean
make install     # npm install
```

A change is not done until `typecheck` and `lint` both pass. There is no
frontend unit-test suite yet; the backend suites cover the API contracts that the
UI depends on.

---

## Forbidden Patterns

| Pattern | Why |
|---|---|
| `any`, `@ts-ignore`, `as` on API data | Erases the backend contract — see [Type Safety](./type-safety.md) |
| `fetch` outside `lib/api.ts` | Loses the envelope unwrap, auth header and error typing |
| Query keys not from `queryKeys` | Invalidation silently misses the cache entry |
| API data copied into `useState` | Goes stale, breaks invalidation |
| Hardcoded hex colors | Breaks theming; use tokens from `tailwind.config.ts` |
| Clickable `<div>` | Inaccessible; use `<button type="button">` or `<Link>` |
| Array index as `key` when an id exists | Breaks reconciliation on reorder |
| `console.log` left in committed code | Use the UI's own status/error surfaces |
| `dangerouslySetInnerHTML` | XSS risk; render as text |
| Direct DOM access (`document.querySelector`) | Fights React; use refs and state |

---

## Required Patterns

- **`"use client"`** at the top of any file using hooks, event handlers or browser
  APIs. Server components by default otherwise.
- **Named exports** for components; default export only for `page.tsx` /
  `layout.tsx` as Next.js requires.
- **Explicit loading, empty and error states.** Every list renders an
  `EmptyState` when empty and an `ErrorState` when its query fails — never a blank
  panel.
- **Disable + relabel async actions.** A pending mutation sets `disabled` and
  changes the button text (`"Saving…"`).
- **Import via the `@/` alias**, never a relative `../../` path.
- **Stable keys** derived from entity ids.
- **Clean up subscriptions.** Abort in-flight SSE streams on unmount via
  `AbortController`.

---

## Testing Requirements

- Backend behaviour is covered by `backend/tests/` (core API, AI layer, jobs
  layer). If you change an endpoint's shape, update `types/api.ts` and run
  `make test`.
- When a frontend test suite is added, prefer testing hooks and pages through the
  rendered DOM over implementation details, and mock at the `lib/api.ts` boundary.

---

## Code Review Checklist

- [ ] `make typecheck` and `make lint` pass.
- [ ] New API calls go through `lib/api.ts`; new types live in `types/api.ts`.
- [ ] Every new list handles loading, empty and error states.
- [ ] Mutations invalidate the queries they affect.
- [ ] Interactive elements are real buttons/links with labels.
- [ ] No `any`, no inline query keys, no hardcoded colors.
- [ ] Route added to `NAV` in `components/AppShell.tsx` when creating a page.

---

## Related

- [Directory Structure](./directory-structure.md)
- [Component Guidelines](./component-guidelines.md)
- [Type Safety](./type-safety.md)
