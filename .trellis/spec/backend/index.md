# Backend Development Guidelines

> Best practices for backend development in this project.

---

## Overview

This directory contains guidelines for backend development. Fill in each file with your project's specific conventions.

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | Done |
| [Database Guidelines](./database-guidelines.md) | ORM patterns, queries, migrations | Done |
| [Error Handling](./error-handling.md) | Error types, handling strategies | Done |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | Done |
| [Logging Guidelines](./logging-guidelines.md) | Structured logging, log levels | Done |

---

## How to Fill These Guidelines

For each guideline file:

1. Document your project's **actual conventions** (not ideals)
2. Include **code examples** from your codebase
3. List **forbidden patterns** and why
4. Add **common mistakes** your team has made

The goal is to help AI assistants and new team members understand how YOUR project works.

---

## Key Contracts at a Glance

- **Response envelope**: `{success, data, request_id}` (errors: `{success:false, error:{code,message}, request_id}`)
- **Error codes**: `app/core/errors.py::ErrorCode` — stable public contract
- **Chat stream**: `POST /api/v1/chat` → `text/event-stream`, order
  `start → thinking → (tool_call → tool_result)* → content → done`
- **Agent loop**: bounded to 3 tool rounds; tools gated by `ToolRegistry` permissions
- **Event chain**: `EventCreated` → goal progress → memory candidate → insight/report
- **Job draining**: follow-up jobs run in `get_db()` **after** commit

---

**Language**: All documentation should be written in **English**.
