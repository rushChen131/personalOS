"""AI orchestration primitives for PersonalOS.

This package owns agent orchestration, model providers, tool dispatch,
retrieval, and action proposals. Import from the submodules directly:

- ``app.ai.runtime``   — AgentRuntime, AgentContext/Input/Result, ``sse``
- ``app.ai.gateway``   — LLMGateway, MockGateway, OpenAIGateway, ModelRouter
- ``app.ai.tools``     — ToolRegistry, ToolDefinition, action proposals
- ``app.ai.agents``    — BaseAgent + the seven agents and AgentRegistry
- ``app.ai.rag``       — RAGRuntime (hybrid retrieval)
- ``app.ai.context``   — ContextRuntime
"""
