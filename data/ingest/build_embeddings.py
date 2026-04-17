"""Generate course embeddings via Ollama and store on Neo4j Course nodes."""

from __future__ import annotations

import logging

import httpx

from data.ingest.retry import with_retry

FAILURE_THRESHOLD = 0.05  # exit non-zero only if > 5% of courses fail


def get_embedding(text: str, client: httpx.Client, *, base_url: str, model: str) -> list[float]:
    resp = client.post(
        f"{base_url}/api/embed",
        json={"model": model, "input": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def create_vector_index(session) -> None:
    session.run(
        "CREATE VECTOR INDEX `course-embeddings` IF NOT EXISTS "
        "FOR (c:Course) ON (c.embedding) "
        "OPTIONS {indexConfig: {`vector.dimensions`: 768, "
        "`vector.similarity_function`: 'cosine'}}"
    )


def build_embedding_text(record: dict) -> str:
    attrs = " ".join(record.get("attributes") or [])
    return (
        f"{record['code']} {record['title']} "
        f"{record.get('topic_titles') or ''} "
        f"{record.get('description') or ''} "
        f"{attrs}"
    ).strip()


def build_all_embeddings(logger: logging.Logger | None = None) -> None:
    """Generate embeddings for all Course nodes missing them."""
    from neo4j import GraphDatabase
    from shared.config import settings

    log = logger or logging.getLogger(__name__)

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    with driver.session() as session:
        create_vector_index(session)

    with driver.session() as session:
        records = session.run(
            "MATCH (c:Course) WHERE c.embedding IS NULL "
            "OPTIONAL MATCH (c)-[:HAS_ATTRIBUTE]->(a:Attribute) "
            "RETURN c.code AS code, c.title AS title, "
            "c.topic_titles AS topic_titles, c.description AS description, "
            "collect(a.college + ': ' + a.category) AS attributes"
        ).data()

    total = len(records)
    if total == 0:
        log.info("all courses already have embeddings, skipping")
        driver.close()
        return

    log.info(f"generating embeddings for {total} courses", extra={"step": "embeddings"})

    failed: list[str] = []
    client = httpx.Client()

    try:
        for i, record in enumerate(records, 1):
            code = record["code"]
            text = build_embedding_text(record)

            embedding = None
            try:
                embedding = with_retry(
                    lambda: get_embedding(
                        text,
                        client,
                        base_url=settings.ollama_url,
                        model=settings.ollama_embed_model,
                    ),
                    on_retry=lambda attempt, exc: log.warning(
                        f"embed retry {attempt}: {exc}",
                        extra={"step": "embeddings", "course_code": code},
                    ),
                )
            except Exception as exc:
                log.error(
                    f"embed failed after all attempts: {exc}",
                    extra={"step": "embeddings", "course_code": code},
                )
                failed.append(code)

            if embedding is not None:
                with driver.session() as session:
                    session.run(
                        "MATCH (c:Course {code: $code}) SET c.embedding = $embedding",
                        code=code,
                        embedding=embedding,
                    )

            if i % 100 == 0 or i == total:
                log.info(
                    f"progress {i}/{total}",
                    extra={"step": "embeddings"},
                )
    finally:
        client.close()
        driver.close()

    fail_rate = len(failed) / total if total else 0
    log.info(
        f"embeddings done: {total - len(failed)}/{total} written, {len(failed)} failed",
        extra={"step": "embeddings"},
    )

    if failed and fail_rate > FAILURE_THRESHOLD:
        raise RuntimeError(
            f"Embedding failure rate {fail_rate:.1%} exceeds threshold "
            f"{FAILURE_THRESHOLD:.0%} ({len(failed)}/{total} failed)"
        )


if __name__ == "__main__":
    build_all_embeddings()
