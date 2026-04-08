"""Auth-enforcing tool executor for the chat service (CHAT-006 / CUAI-38).

Wraps every LLM-generated tool call with the security controls mandated by
`ADR-14 <../../../../docs/decisions.md>`_ (backend-enforced tool authorization)
and ADR-17 (defense in depth):

1. **JWT user_id override** — the ``user_id`` parameter is ALWAYS replaced
   with the authenticated user from the JWT, never trusted from the LLM.
2. **Parameter whitelisting** — unknown keys the LLM hallucinates are
   dropped before invocation.  Combined with Pydantic validation inside
   ``@tool``, this means only fields the schema declares can ever reach
   the underlying function.
3. **Pydantic validation** — LangChain's ``@tool`` decorator validates each
   parameter against the tool's ``args_schema``.  A validation failure is
   caught and returned as a *retry-eligible* error so the LLM can try again
   with corrected arguments.
4. **Rate limiting** — no more than 10 tool calls per conversation turn,
   preventing runaway loops (malicious or otherwise).
5. **Audit logging** — every invocation (success *or* failure) is persisted
   to ``tool_audit_log`` for post-hoc investigation.  Failures are marked
   ``flagged=True`` so anomaly detection can zero in on them.
6. **Retry signalling** — validation errors return ``{"retry": True}`` so
   the LangGraph caller can re-prompt the LLM with the error message before
   giving up.

The executor is intentionally **stateless**: the conversation turn owns the
``call_count`` counter and passes it in on every invocation.  This keeps a
single :class:`ToolExecutor` instance trivially safe to share across
concurrent websocket sessions and makes every branch unit-testable in
isolation.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.tools import BaseTool
from pydantic import ValidationError
from shared.models import ToolAuditLog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# ─── Tunables ────────────────────────────────────────────────────────────

MAX_TOOL_CALLS_PER_TURN = 10
"""Hard cap on tool calls per conversation turn.

Sized against the architecture doc (§ Security, Defense 1): a legitimate
multi-tool flow (``get_student_profile`` → ``get_degree_requirements`` →
``search_courses`` → ``lookup_course`` ×2 → ``check_prerequisites`` ×2)
tops out around 7–8 tools.  Ten leaves headroom for pathological-but-benign
flows while still blocking runaway loops.
"""

RESULT_SUMMARY_MAX_CHARS = 500
"""Per architecture doc — keep audit rows small and cheap to scan."""


# ─── Public types ────────────────────────────────────────────────────────


class ToolCallResult(TypedDict, total=False):
    """Structured return shape from :meth:`ToolExecutor.execute`.

    Exactly one of ``result`` (on success) or ``error`` (on failure) is set.
    ``retry`` is set only when the caller should re-prompt the LLM with the
    error message and let it try again; absence of ``retry`` (or ``False``)
    means the caller should drop the call and move on.
    """

    result: Any
    error: str
    retry: bool


# ─── Executor ────────────────────────────────────────────────────────────


class ToolExecutor:
    """Auth-enforcing wrapper around LangChain tool invocation.

    Construct once from ``main.py`` lifespan (after :func:`make_tools`) and
    store on ``app.state``.  The LangGraph engine calls :meth:`execute`
    once per LLM-generated tool call, passing the running turn-local
    ``call_count`` so the rate limit can enforce a per-turn cap.

    Parameters
    ----------
    tool_registry:
        Dict of tool name → ``BaseTool`` produced by
        :func:`chat_service.core.tools.make_tools`.
    postgres_sessionmaker:
        The same ``async_sessionmaker`` that the tools themselves use;
        the executor opens its own short-lived session per audit-log
        insert, matching the project-wide "one session per DB op" pattern.
    """

    def __init__(
        self,
        *,
        tool_registry: dict[str, BaseTool],
        postgres_sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._registry = tool_registry
        self._sessionmaker = postgres_sessionmaker
        # Cache the full input-schema field set for every tool: used for
        # both the "does this tool take user_id?" check and the
        # parameter-whitelisting filter below.  Computed once at construction
        # (tools are immutable closures from make_tools) so each call is a
        # dict lookup rather than a schema walk.
        self._allowed_fields: dict[str, frozenset[str]] = {
            name: frozenset(tool.get_input_schema().model_fields)
            for name, tool in tool_registry.items()
        }
        # Which tools declare a ``user_id`` parameter (even when injected)?
        # Detected against the FULL schema, not ``tool_call_schema`` —
        # ``InjectedToolArg``-marked fields are stripped from the LLM-visible
        # schema but must still be recognised here so the executor knows to
        # inject them.
        self._user_id_tools: frozenset[str] = frozenset(
            name for name, fields in self._allowed_fields.items() if "user_id" in fields
        )

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        user_id: int,
        call_count: int,
        session_id: str | None = None,
    ) -> ToolCallResult:
        """Run one LLM-generated tool call with full auth + audit enforcement.

        Parameters
        ----------
        tool_name:
            The ``@tool``-decorated function name the LLM selected.
        params:
            The LLM-generated parameter dict.  **Not mutated** — the executor
            copies internally before sanitising, so the caller's dict is
            safe to reuse for history/logging.
        user_id:
            The authenticated user's database ID (from the JWT subject).
            Always overrides whatever the LLM tried to pass.
        call_count:
            1-indexed sequence number of this call in the current turn.
            The executor is stateless; the LangGraph turn owns the counter.
            ``call_count == 11`` (and above) is refused.
        session_id:
            Optional websocket session ID for audit-log correlation.

        Returns
        -------
        ToolCallResult
            ``{"result": ...}`` on success; ``{"error": ..., "retry": True}``
            if the LLM should re-prompt with the error; ``{"error": ...}``
            (no ``retry``) if the call should be dropped.
        """
        # 1. Rate limit — the 11th call in a turn is refused outright.
        #    Not retryable: re-prompting the LLM won't reset the counter.
        if call_count > MAX_TOOL_CALLS_PER_TURN:
            return {
                "error": (
                    f"Rate limit exceeded: more than {MAX_TOOL_CALLS_PER_TURN} "
                    "tool calls in one conversation turn."
                ),
            }

        # 2. Dispatch — an unknown tool name is a hard error.  Not
        #    retryable: re-prompting won't conjure a tool into existence.
        tool = self._registry.get(tool_name)
        if tool is None:
            return {"error": f"Unknown tool: {tool_name!r}"}

        # 3. Copy the caller's dict before mutating.  LangChain's message
        #    history holds references to the original ``tool_call.args``
        #    dict; mutating it in place would leak the internal JWT user_id
        #    back into the prompt context on the next turn (minor info-leak
        #    + confusing debug experience).
        sanitised: dict[str, Any] = dict(params)

        # 4. CRITICAL: JWT user_id enforcement (ADR-14).  For tools that
        #    take user_id, force-set to the authenticated value regardless
        #    of what the LLM supplied — ``InjectedToolArg`` should already
        #    prevent the LLM from seeing the field, but we enforce the
        #    trust boundary here anyway (belt and suspenders).
        if tool_name in self._user_id_tools:
            sanitised["user_id"] = str(user_id)

        # 5. Parameter whitelisting — drop any key the tool's schema doesn't
        #    declare.  Pydantic's default is ``extra="ignore"`` so most
        #    unknown fields would be stripped inside validation anyway, but
        #    doing it up front is cheap, makes the audit log faithful to
        #    what actually reached the tool, and forecloses any future
        #    LangChain release that might change its schema's extras policy.
        allowed = self._allowed_fields[tool_name]
        sanitised = {k: v for k, v in sanitised.items() if k in allowed}

        # ``user_id`` lives on its own audit column and is therefore
        # scrubbed from the logged parameters to keep audit rows small and
        # avoid storing the JWT subject twice.
        logged_params = {k: v for k, v in sanitised.items() if k != "user_id"}

        # 6. Invoke — LangChain validates ``params`` against the tool's
        #    Pydantic ``args_schema`` inside ``ainvoke``.  A ``ValidationError``
        #    signals bad LLM output; return a retry-eligible error so the
        #    LangGraph caller can re-prompt the model with the error text
        #    (Defense 1 — retry-on-malformed-call).  Any *other* exception
        #    (DB driver error, Neo4j timeout, HTTP failure) means the tool
        #    itself blew up — record a flagged audit row so post-hoc
        #    investigation can find it, then return a non-retryable error.
        try:
            result = await tool.ainvoke(sanitised)
        except ValidationError as exc:
            # No audit row on validation failure: the invocation never
            # reached the tool body, so there's nothing semantically to
            # "audit" — the LLM is about to retry anyway.
            return {
                "error": f"Invalid parameters for {tool_name}: {exc}",
                "retry": True,
            }
        except Exception as exc:
            await self._write_audit_log(
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                parameters=logged_params,
                result_summary=f"ERROR: {type(exc).__name__}: {exc}",
                flagged=True,
            )
            return {
                "error": f"Tool {tool_name} failed: {type(exc).__name__}: {exc}",
            }

        # 7. Audit log (Defense 6) — one row per successful invocation.
        await self._write_audit_log(
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            parameters=logged_params,
            result_summary=str(result)[:RESULT_SUMMARY_MAX_CHARS],
            flagged=False,
        )

        return {"result": result}

    async def _write_audit_log(
        self,
        *,
        user_id: int,
        session_id: str | None,
        tool_name: str,
        parameters: dict[str, Any],
        result_summary: str,
        flagged: bool,
    ) -> None:
        """Best-effort audit-log writer.

        Opens its own short-lived session (matching every other DB write in
        this service) and swallows any exception with a logged warning.
        This is deliberate: if the audit log is unwritable (Postgres hiccup,
        schema drift), the tool has *already run* — possibly with side
        effects like a new ``student_decisions`` row — and propagating the
        audit failure would either lose the successful result or, worse,
        trigger the LangGraph retry loop to re-run a mutating tool and
        produce duplicates.  Audit-log gaps are visible via alerting on the
        logger; duplicate ``save_decision`` rows are not recoverable.
        """
        try:
            async with self._sessionmaker() as session:
                session.add(
                    ToolAuditLog(
                        user_id=user_id,
                        session_id=session_id,
                        tool_name=tool_name,
                        parameters=parameters,
                        result_summary=result_summary[:RESULT_SUMMARY_MAX_CHARS],
                        flagged=flagged,
                    )
                )
                await session.commit()
        except Exception:
            logger.exception(
                "Failed to write tool_audit_log for tool=%s user_id=%s",
                tool_name,
                user_id,
            )
