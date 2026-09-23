# Component Guidelines

> How components are built in this project.

---

## Overview

Components are **function components with explicit, typed props**. There is no
class-component code. Two kinds exist and must not blur together:

- **Presentational** (`components/`) — pure, prop-driven, no data fetching.
- **Page** (`app/**/page.tsx`) — owns data flow via hooks and composes the above.

---

## Component Structure

```tsx
"use client";                                  // only when hooks/events are used

import { Card, EmptyState, ProgressBar } from "@/components/ui";
import { useGoals } from "@/hooks/useApi";

export function GoalList() {                   // named export, PascalCase
  const goals = useGoals();
  if (!goals.data?.length) return <EmptyState message="No goals yet." />;
  return (
    <Card title="Goals">
      {goals.data.map((goal) => (
        <div key={goal.id}>{goal.title}</div>    // stable, entity-derived key
      ))}
    </Card>
  );
}
```

Order inside a file: directives, imports (external → `@/`), types, component,
helpers.

---

## Props Conventions

Declare props inline with an object type — no `React.FC`, no `interface` for a
single-use shape:

```tsx
export function StatTile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  // ...
}
```

- Required props first, optional last.
- `children: React.ReactNode` for containers.
- Never type a prop as `any`; if the backend shape is unknown, add it to
  `types/api.ts` first.

---

## Styling Patterns

Tailwind utility classes, with semantic colors bound to CSS variables in
`app/globals.css` and exposed in `tailwind.config.ts`:

| Token | Use |
|---|---|
| `bg-surface` / `border-surface-border` | Cards and panels |
| `bg-surface-muted` | Page background, inline code, subtle fills |
| `text-ink` / `text-ink-muted` | Primary / secondary text |
| `bg-accent` / `bg-accent-soft` / `text-accent` | Primary actions, active nav |

Never hardcode hex colors in components — add a token instead. Shared visual
primitives (`Card`, `StatTile`, `Badge`, `ProgressBar`, `EmptyState`,
`ErrorState`) live in `components/ui.tsx`; reuse them rather than re-styling.

---

## Accessibility

- Every form control has a `<label>` (or `aria-label`) tied to the input.
- Interactive elements are `<button type="button">` or `<a>`/`<Link>` — never a
  clickable `<div>`.
- Async buttons set `disabled` while pending and change their label
  (`"Saving…"`), so state is announced rather than only shown.
- Status text that changes (chat stream status) renders in a persistent node, not
  a transient tooltip.
- Charts carry a `title` attribute per bar so values are reachable without color.

---

## Common Mistakes

- **Fetching inside a presentational component.** Pass data down, or make the file
  a page.
- **Missing `"use client"`** on a component using hooks — it fails at build time.
- **Using array index as `key`** when a stable id exists (`item.id`), which breaks
  reconciliation on reorder.
- **Inlining a new object/array prop** (`data={[...]}`) on every render, defeating
  memoization.
- **Re-implementing `Card`/`ErrorState`** locally instead of importing from
  `components/ui.tsx`.

---

## Related

- [Hook Guidelines](./hook-guidelines.md)
- [Directory Structure](./directory-structure.md)
