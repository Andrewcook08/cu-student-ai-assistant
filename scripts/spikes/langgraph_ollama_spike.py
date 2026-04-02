"""LangGraph + Ollama spike — two-tool pattern with gpt-oss:20b.

Extends the CUAI-32 spike to test:
  1. gpt-oss:20b model (vs previous 3b/8b tests)
  2. Two-tool pattern: search_courses (fuzzy) + lookup_course (exact)

Run with:
    uv run --package chat-service python scripts/spikes/langgraph_ollama_spike.py
"""

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, MessagesState, StateGraph

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gpt-oss:20b"

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
COURSE_DATA = {
    "CSCI 1300": {
        "title": "Introduction to Computer Science",
        "credits": 4,
        "prerequisites": [],
        "description": "Teaches techniques for writing computer programs in higher level languages.",
    },
    "CSCI 2270": {
        "title": "Data Structures",
        "credits": 4,
        "prerequisites": ["CSCI 1300"],
        "description": "Studies data abstractions including stacks, queues, trees, and graphs.",
    },
    "CSCI 2400": {
        "title": "Computer Systems",
        "credits": 4,
        "prerequisites": ["CSCI 2270"],
        "description": "Computer organization, machine-level programming, system software.",
    },
    "CSCI 3104": {
        "title": "Algorithms",
        "credits": 4,
        "prerequisites": ["CSCI 2270"],
        "description": "Design and analysis of algorithms: sorting, searching, graph algorithms.",
    },
    "CSCI 3155": {
        "title": "Principles of Programming Languages",
        "credits": 3,
        "prerequisites": ["CSCI 2270"],
        "description": "Study of principles of programming language design and implementation.",
    },
    "CSCI 3202": {
        "title": "Introduction to Artificial Intelligence",
        "credits": 3,
        "prerequisites": ["CSCI 2270", "CSCI 2820"],
        "description": "Survey of AI techniques: search, logic, machine learning, NLP.",
    },
    "CSCI 3302": {
        "title": "Introduction to Robotics",
        "credits": 3,
        "prerequisites": ["CSCI 2270"],
        "description": "Introduction to robotics concepts: kinematics, sensors, planning.",
    },
    "CSCI 3753": {
        "title": "Operating Systems",
        "credits": 4,
        "prerequisites": ["CSCI 2400", "CSCI 2270"],
        "description": "Fundamentals of operating systems: processes, memory, file systems.",
    },
}


@tool
def search_courses(query: str) -> str:
    """Search for courses by name or keyword. Use this when you don't know the
    exact course code. Returns a list of matching course codes and titles.

    Example: search_courses("data structures") or search_courses("robotics")
    """
    query_lower = query.lower()
    matches = []
    for code, info in COURSE_DATA.items():
        searchable = f"{code} {info['title']} {info['description']}".lower()
        if query_lower in searchable:
            matches.append(f"{code}: {info['title']}")
    if not matches:
        return f"No courses found matching '{query}'."
    return "Matching courses:\n" + "\n".join(matches)


@tool
def lookup_course(course_code: str) -> str:
    """Look up full details for a course by its exact code (e.g. 'CSCI 3155').
    Use search_courses first if you don't know the code.

    Returns course title, credits, prerequisites, and description.
    """
    course = COURSE_DATA.get(course_code.upper().strip())
    if not course:
        return f"No course found for code '{course_code}'."
    return (
        f"{course_code} — {course['title']}\n"
        f"Credits: {course['credits']}\n"
        f"Prerequisites: {', '.join(course['prerequisites']) or 'None'}\n"
        f"Description: {course['description']}"
    )


# ---------------------------------------------------------------------------
# LLM + tool binding
# ---------------------------------------------------------------------------
tools = [search_courses, lookup_course]
tools_by_name = {t.name: t for t in tools}

llm = ChatOllama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)
llm_with_tools = llm.bind_tools(tools)

# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = SystemMessage(
    content=(
        "You are a helpful CU Boulder course advisor. "
        "You have two tools: search_courses (find courses by name or keyword) "
        "and lookup_course (get full details by exact course code). "
        "When a student asks about a course by name, search first to find the code, "
        "then look up the full details. Do not guess course codes."
    )
)


def llm_node(state: MessagesState) -> MessagesState:
    """Invoke the LLM with the current message history."""
    messages = [SYSTEM_PROMPT, *state["messages"]]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def tool_node(state: MessagesState) -> MessagesState:
    """Execute any tool calls from the last LLM message."""
    results: list[ToolMessage] = []
    last_message = state["messages"][-1]
    for call in last_message.tool_calls:
        fn = tools_by_name[call["name"]]
        try:
            output = fn.invoke(call["args"])
        except Exception as e:
            output = f"Tool error: {e}"
        results.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
    return {"messages": results}


def should_continue(state: MessagesState) -> str:
    """Route to tool_node if the LLM made tool calls, otherwise end."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tool_node"
    return END


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
graph_builder = StateGraph(MessagesState)
graph_builder.add_node("llm_node", llm_node)
graph_builder.add_node("tool_node", tool_node)

graph_builder.add_edge(START, "llm_node")
graph_builder.add_conditional_edges("llm_node", should_continue, ["tool_node", END])
graph_builder.add_edge("tool_node", "llm_node")

agent = graph_builder.compile()

# ---------------------------------------------------------------------------
# Run demo queries
# ---------------------------------------------------------------------------
QUERIES = [
    "What can you tell me about CSCI 3155?",                # Direct lookup by code
    "What are the prerequisites for Data Structures?",       # Fuzzy → search then lookup
    "What is 2 + 2?",                                       # Should NOT trigger any tool
    "What programming classes are available?",               # Broad search, no specific lookup
    "Tell me about the intro to robotics course",            # Fuzzy name → search → lookup
]


def run_query(query: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"USER: {query}")
    print("=" * 70)

    messages = [HumanMessage(content=query)]
    for step, event in enumerate(
        agent.stream({"messages": messages}, stream_mode="updates"), start=1
    ):
        for node_name, update in event.items():
            msgs = update.get("messages", [])
            for msg in msgs:
                label = type(msg).__name__
                content = msg.content or "(no content)"
                tool_calls = getattr(msg, "tool_calls", None)

                print(f"\n  Step {step} [{node_name}] -> {label}")
                if tool_calls:
                    for tc in tool_calls:
                        print(f"    Tool call: {tc['name']}({tc['args']})")
                if content and content != "(no content)":
                    print(f"    Content: {content[:300]}")

    print()


if __name__ == "__main__":
    print("LangGraph + Ollama Spike")
    print(f"Model: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")
    print(f"Tools: {[t.name for t in tools]}")

    for q in QUERIES:
        run_query(q)

    print("\nDone.")
