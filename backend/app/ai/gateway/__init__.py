from __future__ import annotations

from app.ai.gateway.base import GatewayResult, LLMGateway
from app.ai.gateway.embeddings import (
    EMBEDDING_DIM,
    EmbeddingProvider,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    build_embedding_provider,
    cosine_similarity,
)
from app.ai.gateway.mock_gateway import MockGateway
from app.ai.gateway.model_router import ModelRouter
from app.ai.gateway.openai_gateway import OpenAIGateway, build_gateway

__all__ = [
    "EMBEDDING_DIM",
    "EmbeddingProvider",
    "GatewayResult",
    "LLMGateway",
    "MockEmbeddingProvider",
    "MockGateway",
    "ModelRouter",
    "OpenAIEmbeddingProvider",
    "OpenAIGateway",
    "build_embedding_provider",
    "build_gateway",
    "cosine_similarity",
]
