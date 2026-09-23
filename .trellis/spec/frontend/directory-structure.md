# Directory Structure

> How frontend code is organized in this project.

---

## Overview

The frontend is a Next.js 15 App Router application. Source lives in `src/` and is
split by *role*, not by feature domain: routing in `app/`, reusable UI in
`components/`, data access in `lib/` and `hooks/`, client state in `stores/`, and
shared contracts in `types/`.

---

## Directory Layout

```
frontend/
├── src/
│   ├── app/                    App Router (routing + page composition)
│   │   ├── layout.tsx          Root layout: Providers + AppShell
│   │   ├── providers.tsx       TanStack Query client
│   │   ├── globals.css         Tailwind entry + CSS design tokens
│   │   ├── page.tsx            Redirects to /dashboard
│   │   ├── dashboard/          Overview: stats, goals, insights, recent events
│   │   ├── timeline/           Event list + manual event creation
│   │   ├── journals/           Journal editor and reader
│   │   ├── goals/              Goal list + creation
│   │   ├── projects/           Project list + creation
│   │   ├── memories/           Memory browse, search, creation
│   │   ├── reports/            Report generation and rendering
│   │   └── chat/               SSE streaming chat
│   ├── components/             Presentational components
│   │   ├── AppShell.tsx        Sidebar nav + auth gate
│   │   ├── LoginPanel.tsx      Credential form
│   │   ├── BarChart.tsx        Dependency-free SVG chart
│   │   └── ui.tsx              Card, StatTile, Badge, ProgressBar, states
│   ├── hooks/
│   │   ├── useApi.ts           All TanStack Query hooks + query keys
│   │   └── useSession.ts       Session restore on mount
│   ├── lib/
│   │   ├── api.ts              Typed fetch client over the API envelope
│   │   ├── sse.ts              POST-based SSE stream reader for /chat
│   │   └── format.ts           Duration / date / relative-time formatters
│   ├── stores/
│   │   └── auth.ts             Zustand auth store
│   └── types/
│       └── api.ts              Types mirroring backend schemas
├── Dockerfile                  Multi-stage build (standalone output)
└── next.config.ts              Rewrites /api/backend/* to the API origin
```

---

## Module Organization

- **A page owns its data flow.** Pages call hooks from `hooks/useApi.ts`; they
  never call `fetch` directly.
- **`lib/api.ts` is the only place that talks HTTP.** Add new endpoints there,
  not in components.
- **Presentational components take props.** Anything in `components/` that is
  reused across pages must be pure and prop-driven; page-specific composition
  stays in the page file.
- **New pages**: create `src/app/<route>/page.tsx`, add the route to `NAV` in
  `components/AppShell.tsx`, and add query hooks to `hooks/useApi.ts`.

---

## Naming Conventions

| Kind | Convention | Example |
|---|---|---|
| Page | `page.tsx` in a lowercase route dir | `app/goals/page.tsx` |
| Component | `PascalCase.tsx` | `components/LoginPanel.tsx` |
| Hook | `use` + PascalCase, `.ts` | `hooks/useApi.ts` |
| Store | lowercase noun, `.ts` | `stores/auth.ts` |
| Utility module | lowercase noun, `.ts` | `lib/format.ts` |

---

## Path Aliases

`@/*` maps to `src/*` (configured in `tsconfig.json`). Always import via the
alias, never via `../../`.

---

## Examples

`src/app/memories/page.tsx` is the reference page: it uses query hooks for reads,
a mutation hook for writes, local `useState` for the search box, and shared
components from `components/ui.tsx`.

---

## Related

- [Component Guidelines](./component-guidelines.md)
- [Hook Guidelines](./hook-guidelines.md)
- [State Management](./state-management.md)
