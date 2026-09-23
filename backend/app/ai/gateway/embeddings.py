from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.core.config import settings
from app.core.logging import logger

EMBEDDING_DIM = 1536


class EmbeddingProvider(Protocol):
    """Contract for turning text into a fixed-dimension vector.

    Implementations must be pure and deterministic for identical input so that
    stored vectors stay comparable across runs.
    """

    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbeddingProvider:
    """Deterministic hashing embedder for local mode.

    Words are hashed into the vector space and L2-normalised, so texts sharing
    vocabulary land near each other under cosine similarity. This makes the
    vector path genuinely functional (not a no-op) without any API key, while
    remaining reproducible across processes.
    """

    provider = "mock"
    dim = EMBEDDING_DIM

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @classmethod
    def _embed_one(cls, text: str) -> list[float]:
        vector = [0.0] * cls.dim
        tokens = [token for token in text.lower().split() if token]
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # Two independent indices per token reduces collision impact.
            for offset in (0, 8):
                index = int.from_bytes(digest[offset : offset + 4], "big") % cls.dim
                sign = 1.0 if digest[offset + 4] % 2 == 0 else -1.0
                vector[index] += sign
        norm = math.sqrt(sum(component * component for component in vector))
        if norm == 0:
            return vector
        return [round(component / norm, 6) for component in vector]


class OpenAIEmbeddingProvider:
    """Real embedding provider, used when ``EMBEDDING_PROVIDER=openai``."""

    provider = "openai"
    dim = EMBEDDING_DIM

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIEmbeddingProvider")
        self.model = model or settings.embedding_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        try:
            response = await client.embeddings.create(model=self.model, input=texts)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error("embeddings.failed", error=str(exc))
            raise
        return [list(item.embedding) for item in response.data]


def build_embedding_provider() -> EmbeddingProvider:
    """Select the embedder from configuration, falling back safely.

    Local mode must always have a working embedder, so an unset key degrades to
    the deterministic mock rather than disabling the vector path entirely.
    """
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        return OpenAIEmbeddingProvider()
    if settings.embedding_provider == "openai":
        logger.warning("embeddings.fallback_to_mock", reason="EMBEDDING_PROVIDER=openai but no API key")
    return MockEmbeddingProvider()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    norm_a = math.sqrt(sum(a[i] * a[i] for i in range(size)))
    norm_b = math.sqrt(sum(b[i] * b[i] for i in range(size)))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


__all__ = [
    "EMBEDDING_DIM",
    "EmbeddingProvider",
    "MockEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "build_embedding_provider",
    "cosine_similarity",
]
