# LangGraph + Ollama Spike Findings (CUAI-32)

**Date:** 2026-04-02
**Model tested:** llama3.2:3b (Q4_K_M, ~2GB) via Ollama in Docker
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

### llama3.1:8b was too large for the Docker container
The 8B model required ~4.8GB but only 4.5GB was available. We dropped to llama3.2:3b (2GB). **For production, size the Ollama container with enough memory for the target model, or use a quantized variant.**

### Small models hallucinate tool arguments
When asked "What are the prerequisites for Data Structures?", llama3.2:3b invented `CSCI 3145` as the course code instead of looking up the correct one (`CSCI 2270`). A larger model (8B+) or better prompting (e.g., asking the user to provide the course code) would help.

### Small models over-trigger tool calls
When asked "What is 2 + 2?", the model still called `lookup_course` before answering. The system prompt said "Always call the tool before answering course questions" but the model generalized this too aggressively. **For production, use more precise system prompts and/or a larger model.**

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

1. **Memory sizing:** Ollama needs enough RAM for the full model. 8B Q4 ≈ 4.8GB, 3B Q4 ≈ 2GB. Budget accordingly in Docker/K8s.

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
- Use a model >= 8B for production tool-calling accuracy; 3B is fine for dev/testing
- Add a max-iterations guard to the tool loop to prevent infinite cycles
