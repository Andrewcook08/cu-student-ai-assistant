"""Generate course embeddings via Ollama and store on Neo4j Course nodes."""

from __future__ import annotations

import os
import time

import httpx
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "development")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

MAX_RETRIES = 3
RETRY_DELAY = 2.0


def get_embedding(text: str, client: httpx.Client) -> list[float]:
    """Call Ollama embed API and return the embedding vector."""
    resp = client.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": OLLAMA_EMBED_MODEL, "input": text},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def create_vector_index(session) -> None:
    """Create the course-embeddings vector index if it doesn't exist."""
    session.run(
        "CREATE VECTOR INDEX `course-embeddings` IF NOT EXISTS "
        "FOR (c:Course) ON (c.embedding) "
        "OPTIONS {indexConfig: {`vector.dimensions`: 768, "
        "`vector.similarity_function`: 'cosine'}}"
    )
    print("Vector index 'course-embeddings' ensured (768 dims, cosine).")


def build_embedding_text(record: dict) -> str:
    """Construct the text string used to generate a course embedding.

    Format: "{code} {title} {topic_titles} {description} {attributes}"
    """
    attrs = " ".join(record.get("attributes") or [])
    return (
        f"{record['code']} {record['title']} "
        f"{record.get('topic_titles') or ''} "
        f"{record.get('description') or ''} "
        f"{attrs}"
    ).strip()


def build_all_embeddings() -> None:
    """Generate embeddings for all Course nodes missing them."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        create_vector_index(session)

    # Fetch courses that need embeddings (include attributes for gen-ed search).
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
        print("All courses already have embeddings, nothing to do.")
        driver.close()
        return

    print(f"Generating embeddings for {total} courses...")

    failed: list[str] = []
    client = httpx.Client()

    try:
        for i, record in enumerate(records, 1):
            code = record["code"]
            text = build_embedding_text(record)

            embedding = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    embedding = get_embedding(text, client)
                    break
                except (httpx.HTTPError, KeyError) as exc:
                    if attempt < MAX_RETRIES:
                        print(f"  Retry {attempt}/{MAX_RETRIES} for {code}: {exc}")
                        time.sleep(RETRY_DELAY)
                    else:
                        print(f"  FAILED {code} after {MAX_RETRIES} attempts: {exc}")
                        failed.append(code)

            if embedding is not None:
                with driver.session() as session:
                    session.run(
                        "MATCH (c:Course {code: $code}) SET c.embedding = $embedding",
                        code=code,
                        embedding=embedding,
                    )

            if i % 100 == 0 or i == total:
                print(f"  Progress: {i}/{total} courses processed.")
    finally:
        client.close()
        driver.close()

    print(f"\nDone. {total - len(failed)}/{total} embeddings written.")
    if failed:
        print(f"Failed courses ({len(failed)}): {', '.join(failed)}")
        raise SystemExit(1)


if __name__ == "__main__":
    build_all_embeddings()
