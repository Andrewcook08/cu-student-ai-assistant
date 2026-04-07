"""Neo4j async service for vector search.

Queries the 'course-embeddings' vector index (768-dim cosine) that is
populated by data/ingest/build_embeddings.py.

The AsyncDriver is injected rather than constructed per call so the
connection pool is reused across requests (see lifespan in main.py).
"""

from typing import Any

from neo4j import AsyncDriver


async def vector_search(
    driver: AsyncDriver,
    embedding: list[float],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return up to *limit* courses ranked by cosine similarity to *embedding*.

    Each result dict has:
        code  — course code (e.g. "CSCI 3308")
        title — course title
        score — cosine similarity score (0–1, higher is more relevant)

    Args:
        driver:    The shared AsyncDriver from app.state (lifespan-managed).
        embedding: 768-dim vector to query against.
        limit:     Maximum number of results to return.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            CALL db.index.vector.queryNodes('course-embeddings', $limit, $embedding)
            YIELD node, score
            RETURN node.code AS code, node.title AS title, score
            ORDER BY score DESC
            """,
            limit=limit,
            embedding=embedding,
        )
        return await result.data()  # type: ignore[no-any-return]
