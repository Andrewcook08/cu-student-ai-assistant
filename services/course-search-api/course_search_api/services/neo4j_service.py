"""Neo4j async service for vector search.

Queries the 'course-embeddings' vector index (768-dim cosine) that is
populated by data/ingest/build_embeddings.py.
"""

from neo4j import AsyncGraphDatabase
from shared.config import settings


async def vector_search(embedding: list[float], limit: int = 10) -> list[dict]:
    """Return up to *limit* courses ranked by cosine similarity to *embedding*.

    Each result dict has:
        code  — course code (e.g. "CSCI 3308")
        title — course title
        score — cosine similarity score (0–1, higher is more relevant)
    """
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
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
            records: list[dict] = await result.data()
    finally:
        await driver.close()
    return records
