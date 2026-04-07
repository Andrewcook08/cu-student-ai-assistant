"""Neo4j async service layer for Graph RAG queries.

Exposes three parameterized Cypher queries that the LangGraph tool layer
(CHAT-005) wraps as `@tool` functions:

- ``vector_search``          → backs the ``search_courses`` tool
- ``get_prerequisite_chain`` → backs the ``check_prerequisites`` tool
- ``get_degree_requirements``→ backs the ``get_degree_requirements`` tool

The ``AsyncDriver`` is injected rather than constructed per call so that the
connection pool (created once in ``main.py`` lifespan) is reused across
requests. All inputs reach Cypher through parameters; no string
interpolation, so Cypher injection is not possible.

Graph shape (from data/ingest/*.py and architecture.md § Neo4j Graph Schema)::

    (:Course {code, title, credits, description, instruction_mode, campus,
              topic_titles, embedding})
      -[:HAS_PREREQUISITE {type, min_grade, raw_text}]-> (:Course)
    (:Program {name, type, total_credits})
      -[:HAS_REQUIREMENT]-> (:Requirement {name, requirement_type, credits,
                                           raw_text, sort_order})
        -[:SATISFIED_BY]-> (:Course)
        -[:OR_ALTERNATIVE]-> (:Requirement)   # points at predecessor
"""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver

# Bound variable-length prerequisite traversal. Real academic prereq chains
# are rarely deeper than 3; 5 leaves headroom while preventing runaway
# traversal if a parsing bug ever produces a cycle.
_MAX_PREREQ_DEPTH = 5

# Vector index name from data/ingest/build_embeddings.py.
_COURSE_VECTOR_INDEX = "course-embeddings"


async def vector_search(
    driver: AsyncDriver,
    embedding: list[float],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return courses ranked by cosine similarity to *embedding*.

    Each result dict has: ``code``, ``title``, ``credits``, ``description``,
    ``instruction_mode``, ``score``. Returns at most *limit* entries.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            CALL db.index.vector.queryNodes($index, $limit, $embedding)
            YIELD node, score
            RETURN node.code          AS code,
                   node.title         AS title,
                   node.credits       AS credits,
                   node.description   AS description,
                   node.instruction_mode AS instruction_mode,
                   score
            ORDER BY score DESC
            """,
            index=_COURSE_VECTOR_INDEX,
            limit=limit,
            embedding=embedding,
        )
        return [dict(record) async for record in result]


async def get_prerequisite_chain(
    driver: AsyncDriver,
    course_code: str,
) -> dict[str, Any]:
    """Return the full prerequisite chain for *course_code*.

    Returns::

        {
          "course": {"code", "title"} | None,        # None if course not found
          "edges": [
            {"from", "to", "type", "min_grade", "raw_text"},
            ...
          ],
        }

    Each edge represents one ``HAS_PREREQUISITE`` relationship. Depth is
    bounded at ``_MAX_PREREQ_DEPTH`` hops. ``raw_text`` is always preserved
    so the LLM can fall back to the original string when parsing was
    ambiguous.
    """
    async with driver.session() as session:
        course_result = await session.run(
            "MATCH (c:Course {code: $code}) RETURN c.code AS code, c.title AS title",
            code=course_code,
        )
        course_rows = [record async for record in course_result]
        if not course_rows:
            return {"course": None, "edges": []}

        edge_result = await session.run(
            f"""
            MATCH (:Course {{code: $code}})-[r:HAS_PREREQUISITE*1..{_MAX_PREREQ_DEPTH}]->(:Course)
            UNWIND r AS rel
            RETURN startNode(rel).code AS from_code,
                   endNode(rel).code   AS to_code,
                   rel.type            AS type,
                   rel.min_grade       AS min_grade,
                   rel.raw_text        AS raw_text
            """,
            code=course_code,
        )
        edge_rows = [record async for record in edge_result]

    course = {"code": course_rows[0]["code"], "title": course_rows[0]["title"]}

    # Deduplicate — an edge reachable via multiple paths is still one edge.
    seen: set[tuple[str, str, str]] = set()
    edges: list[dict[str, Any]] = []
    for rec in edge_rows:
        key = (rec["from_code"], rec["to_code"], rec["type"])
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "from": rec["from_code"],
                "to": rec["to_code"],
                "type": rec["type"],
                "min_grade": rec["min_grade"],
                "raw_text": rec["raw_text"],
            }
        )

    return {"course": course, "edges": edges}


async def get_degree_requirements(
    driver: AsyncDriver,
    program_name: str,
) -> dict[str, Any]:
    """Return the full requirement set for *program_name*.

    Returns::

        {
          "program": {"name", "type", "total_credits"} | None,
          "requirements": [
            {
              "name", "requirement_type", "credits", "raw_text",
              "courses": [{"code", "title"}],   # from SATISFIED_BY
              "or_alternative_to": str | None,  # predecessor requirement name
            },
            ...
          ],
        }

    Ordering follows the program's authored ``sort_order``. The query returns
    one row per (requirement, satisfying-course) pair; rows are grouped in
    Python because the result sets are small (largest program ≲ 80
    requirements) and Python grouping is clearer than Cypher ``collect()``.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Program {name: $name})
            OPTIONAL MATCH (p)-[:HAS_REQUIREMENT]->(req:Requirement)
            OPTIONAL MATCH (req)-[:SATISFIED_BY]->(c:Course)
            OPTIONAL MATCH (req)-[:OR_ALTERNATIVE]->(pred:Requirement)
            RETURN p.name           AS program_name,
                   p.type           AS program_type,
                   p.total_credits  AS program_total_credits,
                   req.sort_order   AS sort_order,
                   req.name         AS req_name,
                   req.requirement_type AS requirement_type,
                   req.credits      AS credits,
                   req.raw_text     AS raw_text,
                   c.code           AS course_code,
                   c.title          AS course_title,
                   pred.name        AS or_alternative_to
            ORDER BY req.sort_order
            """,
            name=program_name,
        )
        records = [record async for record in result]

    if not records:
        return {"program": None, "requirements": []}

    first = records[0]
    program = {
        "name": first["program_name"],
        "type": first["program_type"],
        "total_credits": first["program_total_credits"],
    }

    # Group rows by requirement sort_order. Preserves Cypher's ORDER BY.
    grouped: dict[int, dict[str, Any]] = {}
    for rec in records:
        sort_order = rec["sort_order"]
        if sort_order is None:
            # Program exists but has no requirements yet.
            continue
        if sort_order not in grouped:
            grouped[sort_order] = {
                "name": rec["req_name"],
                "requirement_type": rec["requirement_type"],
                "credits": rec["credits"],
                "raw_text": rec["raw_text"],
                "courses": [],
                "or_alternative_to": rec["or_alternative_to"],
            }
        if rec["course_code"] is not None:
            course = {"code": rec["course_code"], "title": rec["course_title"]}
            if course not in grouped[sort_order]["courses"]:
                grouped[sort_order]["courses"].append(course)

    return {"program": program, "requirements": list(grouped.values())}
