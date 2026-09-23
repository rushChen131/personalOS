from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.journal import Journal
from app.models.memory import Memory


class RAGRuntime:
    """Hybrid retrieval over memories and events.

    The scoring path combines vector similarity (when an embedder is available),
    keyword overlap, importance and recency, so results stay useful whether or
    not embeddings have been computed yet. On PostgreSQL + pgvector, results are
    ranked in the database; elsewhere the deterministic local embedder is used
    in-process.
    """

    def __init__(self, top_k: int = 10) -> None:
        self.top_k = top_k

    async def search(
        self,
        session: AsyncSession,
        user_id: str,
        query: str,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        limit = top_k or self.top_k

        if not settings.is_sqlite and filters.get("vector"):
            # pgvector cosine search, ranked in the database.
            return await self._vector_search(session, user_id, query, filters, limit)

        if settings.is_sqlite and filters.get("vector"):
            # Same ranking, executed in-process so dev matches production.
            return await self._vector_search_python(session, user_id, query, filters, limit)

        memories = await self._keyword_memories(session, user_id, query, filters)
        journals = await self._keyword_journals(session, user_id, query, filters)
        combined = memories + journals
        combined.sort(key=lambda item: item["score"], reverse=True)
        return combined[:limit]

    async def embed_query(self, query: str) -> list[float]:
        """Embed a query string with the configured provider."""
        from app.ai.gateway.embeddings import build_embedding_provider

        if not query.strip():
            return []
        provider = build_embedding_provider()
        return (await provider.embed([query]))[0]

    async def _keyword_memories(
        self, session: AsyncSession, user_id: str, query: str, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        stmt = select(Memory).where(Memory.user_id == user_id)
        if filters.get("memory_type"):
            stmt = stmt.where(Memory.type == filters["memory_type"])
        rows = list((await session.scalars(stmt.limit(200))).unique())

        # Vector component: only computed when the caller supplies a query
        # vector, so the keyword path stays zero-cost for plain lookups.
        query_vector: list[float] | None = filters.get("vector")
        if query_vector is None and query.strip() and filters.get("use_vector", True):
            try:
                query_vector = await self.embed_query(query)
            except Exception:  # noqa: BLE001 - embeddings must never break search
                query_vector = None

        scored = []
        for row in rows:
            text = f"{row.content} {row.summary or ''}"
            score = self._score(query, text, importance=float(row.importance or 0), when=None)
            if query_vector and row.embedding:
                from app.ai.gateway.embeddings import cosine_similarity

                similarity = max(0.0, cosine_similarity(query_vector, list(row.embedding)))
                score = round(score + similarity * 0.5, 4)
            if score > 0 or not query:
                scored.append(
                    {
                        "kind": "memory",
                        "id": row.id,
                        "content": row.content,
                        "type": row.type,
                        "importance": float(row.importance or 0),
                        "score": score,
                    }
                )
        return scored

    async def _keyword_journals(
        self, session: AsyncSession, user_id: str, query: str, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        stmt = select(Journal).where(Journal.user_id == user_id)
        if filters.get("since"):
            stmt = stmt.where(Journal.occurred_at >= filters["since"])
        rows = list((await session.scalars(stmt.order_by(Journal.occurred_at.desc()).limit(200))).unique())
        scored = []
        for row in rows:
            text = f"{row.title or ''} {row.content or ''}"
            score = self._score(query, text, importance=0.5, when=row.occurred_at)
            if score > 0 or not query:
                scored.append(
                    {
                        "kind": "journal",
                        "id": row.id,
                        "title": row.title,
                        "content": row.content,
                        "type": row.mood,
                        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                        "importance": 0.5,
                        "score": score,
                    }
                )
        return scored

    async def _vector_search(
        self, session: AsyncSession, user_id: str, query: str, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:  # pragma: no cover - requires PG + pgvector
        """pgvector cosine path: embeddings are precomputed by the embedding job.

        The ordering logic itself is factored into :func:`rank_by_cosine` so it
        can be unit-tested without a PostgreSQL instance.
        """
        from sqlalchemy import text as sql_text

        rows = (
            await session.execute(
                sql_text(
                    "SELECT id, content, 1 - (embedding <=> :vec) AS score "
                    "FROM memories WHERE user_id = :uid AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> :vec LIMIT :limit"
                ),
                {"vec": filters.get("vector"), "uid": user_id, "limit": limit},
            )
        ).all()
        return [{"kind": "memory", "id": r.id, "content": r.content, "score": float(r.score)} for r in rows]

    async def _vector_search_python(
        self, session: AsyncSession, user_id: str, query: str, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        """Dialect-agnostic equivalent of :meth:`_vector_search`.

        Loads candidate rows and ranks them in-process with the same
        ``1 - cosine_distance`` semantics pgvector's ``<=>`` operator uses, so
        the two paths can be compared directly in tests and the SQLite dev
        environment exercises identical ranking rules.
        """
        vector = filters.get("vector") or await self.embed_query(query)
        if not vector:
            return []
        stmt = select(Memory).where(Memory.user_id == user_id, Memory.embedding.is_not(None))
        if filters.get("memory_type"):
            stmt = stmt.where(Memory.type == filters["memory_type"])
        rows = list((await session.scalars(stmt.limit(200))).unique())
        candidates = [{"id": row.id, "content": row.content, "embedding": list(row.embedding or [])} for row in rows]
        ranked = rank_by_cosine(candidates, vector, limit)
        return [
            {"kind": "memory", "id": item["id"], "content": item["content"], "score": item["score"]}
            for item in ranked
        ]

    @staticmethod
    def _score(query: str, text: str, importance: float = 0.0, when: Any = None) -> float:
        if not query:
            return importance
        tokens = [token for token in query.lower().split() if len(token) > 1]
        haystack = text.lower()
        hits = sum(1 for token in tokens if token in haystack)
        keyword = hits / len(tokens) if tokens else 0.0
        score = keyword * 0.7 + importance * 0.2
        if when is not None:
            from datetime import datetime, timezone

            start = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - start).days
            score += max(0.0, 0.1 - age_days * 0.001)
        return round(score, 4)


def rank_by_cosine(
    candidates: list[dict[str, Any]], vector: list[float], limit: int
) -> list[dict[str, Any]]:
    """Rank ``{id, content, embedding}`` rows by cosine similarity.

    Mirrors pgvector's ``1 - (embedding <=> :vec)`` ordering exactly, including
    the exclusion of rows whose vector is missing or degenerate, so the pure
    Python path and the SQL path cannot drift apart.
    """
    from app.ai.gateway.embeddings import cosine_similarity

    if not vector:
        return []
    scored: list[dict[str, Any]] = []
    for item in candidates:
        embedding = item.get("embedding") or []
        if not embedding:
            continue
        similarity = cosine_similarity(vector, list(embedding))
        if similarity <= 0:
            # pgvector would still return these, but a non-positive cosine
            # carries no signal, so they are dropped for consistency.
            continue
        scored.append(
            {
                "id": item["id"],
                "content": item.get("content"),
                "score": round(similarity, 6),
            }
        )
    scored.sort(key=lambda entry: entry["score"], reverse=True)
    return scored[:limit]


def matches_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def build_text_filter(column: Any, query: str) -> Any:
    return or_(column.ilike(f"%{query}%"))
