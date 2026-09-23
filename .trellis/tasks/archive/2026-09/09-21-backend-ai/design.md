# Backend AI Runtime Design

## Boundaries

`app.ai` owns agent orchestration, model providers, tool dispatch, retrieval,
and action proposals. It depends on repositories and services from
`backend-core`; API routers remain thin adapters that turn HTTP/SSE requests
into runtime calls.

## Execution flow

`POST /api/v1/chat` constructs an `AgentContext`, opens or reuses a
conversation, and streams runtime events in this order: `start`, `thinking`,
zero or more `tool_call` / `tool_result` pairs, `content`, and `done`.
`AgentRuntime` persists the run and all tool calls, including failures, before
emitting `done`.

## Provider and retrieval strategy

`MockGateway` is the default when no usable OpenAI configuration is present.
It emits deterministic structured replies and tool requests so local SQLite
development has no external dependency. `OpenAIGateway` uses the same gateway
result contract and is selected only when explicitly configured with a key.
RAG first performs repository-backed keyword retrieval; vector retrieval is an
extension point for PostgreSQL/pgvector and must not affect SQLite results.

## Safety

Every tool declares a permission. The registry validates it against the
executing agent before invocation. Write or destructive tools return an action
proposal with `requires_confirmation`; confirmation is stored in-process for
this V1.2 task and consumed by `POST /api/v1/actions/{id}/confirm`.

## Compatibility

Existing repositories and the `{success, data, request_id}` JSON envelope stay
unchanged. The chat endpoint is the sole exception: it returns
`text/event-stream` on success so client applications can render incremental
agent events.
