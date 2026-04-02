# LangGraph + Ollama Spike Findings (CUAI-32)

**Date:** 2026-04-02
**Models tested:** llama3.2:3b (Q4_K_M, ~2GB), llama3.1:8b (Q4_K_M, ~4.9GB), gpt-oss:20b (~13GB)
**LangGraph version:** >=0.2 (from chat-service deps)

---

## What Worked

### ReAct pattern via StateGraph — clean and predictable
The core loop is simple and works reliably:

```
START → llm_node → [has tool_calls?] → tool_node → llm_node (loop)
                  → [no tool_calls]  → END
```

Key code pattern:
```python
from langgraph.graph import END, START, MessagesState, StateGraph

graph = StateGraph(MessagesState)
graph.add_node("llm_node", llm_node)
graph.add_node("tool_node", tool_node)
graph.add_edge(START, "llm_node")
graph.add_conditional_edges("llm_node", should_continue, ["tool_node", END])
graph.add_edge("tool_node", "llm_node")
agent = graph.compile()
```

### Built-in `MessagesState` handles message accumulation
No need to define custom state — `MessagesState` provides `messages: list` with an `add` reducer that appends rather than replaces. Nodes just return `{"messages": [new_msg]}`.

### `ChatOllama.bind_tools()` works out of the box
```python
from langchain_ollama import ChatOllama
llm = ChatOllama(model="llama3.2:3b", base_url="http://localhost:11434")
llm_with_tools = llm.bind_tools([my_tool])
```
Tool schemas are auto-generated from the `@tool` decorator's type hints and docstring.

### Streaming via `agent.stream()` gives per-node updates
`stream_mode="updates"` yields dicts keyed by node name after each node runs. Good for showing progress in a chat UI.

---

## What Didn't Work (or Needs Care)

### Ollama container memory matters
The initial container had ~4.5GB memory — not enough for llama3.1:8b (~4.8GB required). After bumping to 8GB, the 8B model loaded fine. **Size the Ollama container for your target model + overhead.** For gpt-oss:20b (~13GB Q4), set `memory: 20g`.

### Fuzzy lookups remain hard even at 8B
When asked "What are the prerequisites for Data Structures?", both models struggled:
- **3B** hallucinated a non-existent course code (`CSCI 3145`)
- **8B** picked a real but wrong course (`CSCI 3155` instead of `CSCI 2270`)

Neither model could map the course name "Data Structures" to the correct code. **This is a tool design issue, not just a model size issue — the tool should accept course names, not just codes, or we need a search/fuzzy-match tool.**

### Over-triggering fixed at 8B
When asked "What is 2 + 2?":
- **3B** incorrectly called `lookup_course` before answering
- **8B** correctly skipped the tool and answered directly

The 8B model respects tool-calling boundaries much better.

### 3B vs 8B vs 20B comparison summary

| Test case | llama3.2:3b | llama3.1:8b | gpt-oss:20b (two-tool) |
|---|---|---|---|
| Direct course lookup (CSCI 3155) | Correct | Correct | Correct (direct `lookup_course`) |
| Fuzzy lookup (Data Structures → CSCI 2270) | Hallucinated fake code | Used wrong real code | **Correct** — `search_courses` → `lookup_course` |
| Non-course question (2+2) | Over-triggered tool | Correctly skipped tool | Correctly skipped tool |
| Broad search ("programming classes") | N/A (single-tool) | N/A (single-tool) | Correct — used `search_courses` only |
| Fuzzy name ("intro to robotics") | N/A (single-tool) | N/A (single-tool) | **Self-corrected** — retried broader query, then `lookup_course` |
| Response quality | Terse, sometimes cut off | Detailed, well-structured | Rich markdown tables, well-structured |

---

## gpt-oss:20b + Two-Tool Pattern Results

**Tested:** 2026-04-02 on M3 Max (40 GPU cores, 64GB unified memory), native Ollama with Metal acceleration.

### Two-tool pattern validated

The spike recommended a two-tool pattern (`search_courses` + `lookup_course`) to solve the fuzzy lookup problem that 3B and 8B both failed. gpt-oss:20b nails it:

1. **Search → Lookup chain**: When asked about "Data Structures" by name, the model correctly called `search_courses("Data Structures")` first, got back `CSCI 2270`, then called `lookup_course("CSCI 2270")`. Both 3B and 8B failed this test with a single tool.

2. **Self-correcting search**: When asked about "intro to robotics", the model searched for `"intro to robotics"` (no match due to substring matching), then **automatically retried** with `"robotics"` and found CSCI 3302. This retry behavior was unprompted — the model reasoned about the failed search and broadened the query.

3. **Tool restraint**: Correctly answered "2 + 2 = 4" without touching any tool. Used `search_courses` alone for the broad "programming classes" query without unnecessarily looking up each result.

### Provisioning

| Factor | llama3.1:8b | gpt-oss:20b |
|---|---|---|
| Model size (Q4) | ~4.9 GB | ~13 GB |
| Docker memory (CPU-only machines) | 8g | 20g |
| GCP instance (L4 GPU, 24GB VRAM) | g2-standard-4 | g2-standard-4 (13GB fits in 24GB VRAM) |
| GCP spot cost | ~$0.28/hr | ~$0.28/hr (same instance) |
| Apple Silicon (Metal) | Fast | Fast (unified memory, no issue at 64GB) |

The L4 GPU has 24GB VRAM — the 13GB Q4 model fits comfortably. **No GCP instance type change needed.** The only infrastructure change is bumping Docker memory from 8g to 20g for teammates running on CPU-only machines.

### Recommendation update

**gpt-oss:20b is the recommended model for the chat service.** It resolves the fuzzy lookup problem, demonstrates multi-step tool reasoning (search → lookup), self-corrects on failed searches, and produces well-formatted markdown responses. The cost and infrastructure requirements are nearly identical to the 8B setup on GCP (same instance type).

---

## Patterns to Reuse in Chat Service

### 1. Node function signature
```python
def my_node(state: MessagesState) -> MessagesState:
    # Read from state["messages"], return {"messages": [new_msgs]}
```

### 2. Tool node with error handling
```python
def tool_node(state: MessagesState) -> MessagesState:
    results = []
    for call in state["messages"][-1].tool_calls:
        fn = tools_by_name[call["name"]]
        try:
            output = fn.invoke(call["args"])
        except Exception as e:
            output = f"Tool error: {e}"
        results.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
    return {"messages": results}
```

### 3. Conditional routing
```python
def should_continue(state: MessagesState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tool_node"
    return END
```

### 4. System prompt as first message (not in state)
Prepend the system prompt inside `llm_node` rather than storing it in state. This keeps the state clean and avoids accumulating duplicate system messages.

---

## Gotchas for the Team

1. **Memory sizing:** Ollama needs enough RAM for the full model. 3B Q4 ≈ 2GB, 8B Q4 ≈ 4.8GB, 20B Q4 ≈ 13GB. Budget accordingly in Docker/K8s.

2. **Tool call ID format:** Ollama generates short IDs like `call_dggbuw7q`. The `ToolMessage.tool_call_id` must match exactly or LangGraph will error.

3. **`@tool` decorator docstrings matter:** The docstring becomes the tool description sent to the LLM. Be specific — vague descriptions lead to incorrect tool use.

4. **No `create_react_agent` needed:** The LangGraph prebuilt `create_react_agent` exists but building the graph manually (5 lines) gives us full control over nodes, state, and error handling. Prefer manual construction for the chat service.

5. **Streaming considerations:** `stream_mode="updates"` is node-level. For token-level streaming in a chat UI, use `stream_mode="messages"` or `astream_events()`.

6. **Tool result must be a string:** `ToolMessage.content` expects a string. If your tool returns a dict, serialize it.

---

## Recommendation for CHAT-008

- Use the manual `StateGraph` pattern (not `create_react_agent`) for full control
- Start with `MessagesState`, extend with custom fields (e.g., `user_id`, `session_id`) via TypedDict as needed
- Wrap tool execution in try/except to prevent graph crashes
- **Use gpt-oss:20b** — validated for reliable tool calling, fuzzy search reasoning, and self-correcting behavior. Set `OLLAMA_MODEL=gpt-oss:20b` in `.env`
- Use the two-tool pattern: `search_courses` for fuzzy/vector search by name or keyword (returns codes + summaries), `lookup_course` for exact code-based retrieval of full details. **Validated with gpt-oss:20b** — the model correctly chains search → lookup without prompting
- Add a max-iterations guard to the tool loop to prevent infinite cycles
- Bump Docker Ollama memory to 20g for local development on CPU-only machines
