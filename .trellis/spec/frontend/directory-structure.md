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
│   │   ├── dashboard/          Overview: stats, todos, journals, memories
│   │   ├── journals/           Journal editor and reader
│   │   ├── reports/            Report generation and rendering
│   │   └── settings/           Account, language switch, sign-out
│   ├── components/             Presentational components
│   │   ├── AppShell.tsx        Header + auth gate + Copilot panel host
│   │   ├── CopilotPanel.tsx    SSE streaming chat sidebar
│   │   ├── LoginPanel.tsx      Credential form
│   │   ├── BarChart.tsx        Dependency-free SVG chart
│   │   └── ui.tsx              Card, StatTile, Badge, Modal, states
│   ├── hooks/
│   │   ├── useApi.ts           All TanStack Query hooks + query keys
│   │   └── useSession.ts       Session restore on mount
│   ├── lib/
│   │   ├── api.ts              Typed fetch client over the API envelope
│   │   ├── i18n.ts             zh/en dictionaries, locale store, formatters
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
- **New pages**: create `src/app/<route>/page.tsx` and add the query hooks to
  `hooks/useApi.ts`. There is no sidebar `NAV` to update — the header's account
  chip is the only navigation, and it leads to Settings.

---

## Naming Conventions

| Kind | Convention | Example |
|---|---|---|
| Page | `page.tsx` in a lowercase route dir | `app/journals/page.tsx` |
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
