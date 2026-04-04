"""
Validate tool-calling capability of the Ollama model used by the CU Student AI Assistant.

Sends 30 representative student queries to the model and checks that it selects
the correct tool on the first call.

Run with: uv run python scripts/test_tool_calling.py
"""

import argparse
import json
import sys

import httpx

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "gpt-oss:20b"

SYSTEM_MESSAGE = (
    "You are an AI academic advisor for CU Boulder students. "
    "Answer questions about courses, schedules, prerequisites, and degree requirements "
    "using the tools provided. Always use a tool when one is relevant rather than "
    "guessing from memory.\n\n"
    "The current student's user ID is 'user_123'. Their session is authenticated — "
    "use this ID when calling tools that require user_id.\n\n"
    "Tool usage guidelines:\n"
    "- When a student mentions a course by name (not code), use search_courses first "
    "to find the correct code. Do not guess course codes.\n"
    "- When a student provides an exact course code (e.g. CSCI 2270), use lookup_course "
    "or check_prerequisites directly.\n"
    "- When a student asks you to save, plan, or mark a course, use save_decision.\n"
    "- When a student asks about scheduling multiple courses together, use "
    "find_schedule_conflicts."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_courses",
            "description": "Search for courses by keyword, department, or filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "department": {"type": "string"},
                    "instruction_mode": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_course",
            "description": (
                "Get full details for a specific course by its exact code (e.g. CSCI 2270). "
                "Use search_courses first if you only have a name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {"type": "string"},
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_prerequisites",
            "description": "Get the full prerequisite chain for a course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_code": {"type": "string"},
                },
                "required": ["course_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_degree_requirements",
            "description": "Get all requirements for a degree program.",
            "parameters": {
                "type": "object",
                "properties": {
                    "program": {"type": "string"},
                },
                "required": ["program"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_student_profile",
            "description": "Get a student's declared program and completed courses with grades.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_schedule_conflicts",
            "description": "Check for time conflicts between selected courses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["course_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_decision",
            "description": "Save a student's course planning decision for future reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "course_code": {"type": "string"},
                    "decision_type": {
                        "type": "string",
                        "enum": ["planned", "interested", "not_interested"],
                    },
                    "notes": {"type": "string"},
                },
                "required": ["user_id", "course_code", "decision_type"],
            },
        },
    },
]

TEST_QUERIES = [
    # search_courses (9)
    ("What machine learning courses are available?", "search_courses"),
    ("I'm looking for something about databases", "search_courses"),
    ("Show me online computer science courses", "search_courses"),
    ("Any data science classes offered in the evening?", "search_courses"),
    ("I need a writing course to satisfy my gen ed", "search_courses"),
    ("What does the biology department offer about genetics?", "search_courses"),
    ("Are there any upper-division ethics courses?", "search_courses"),
    ("I want to learn about operating systems, what's offered?", "search_courses"),
    ("Find me a 3-credit seminar on software engineering", "search_courses"),
    # lookup_course (5)
    ("Tell me about CSCI 2270", "lookup_course"),
    ("What is MATH 2400?", "lookup_course"),
    ("Give me the details for CSCI 3308", "lookup_course"),
    ("What's APPM 1350 about?", "lookup_course"),
    ("Can you pull up INFO 4604?", "lookup_course"),
    # check_prerequisites (4)
    ("What do I need to take before CSCI 3104?", "check_prerequisites"),
    ("What are the prereqs for CSCI 2270?", "check_prerequisites"),
    ("Can I jump straight into CSCI 4831 or do I need something first?", "check_prerequisites"),
    ("What's the prerequisite chain for CSCI 3155?", "check_prerequisites"),
    # get_degree_requirements (3)
    ("What courses do I need to graduate with a CS degree?", "get_degree_requirements"),
    ("What are the requirements for the data science major?", "get_degree_requirements"),
    ("I'm thinking of switching to computer engineering — what would I need?", "get_degree_requirements"),
    # get_student_profile (3)
    ("What courses have I already taken?", "get_student_profile"),
    ("What's my declared major?", "get_student_profile"),
    ("How far along am I in my program?", "get_student_profile"),
    # find_schedule_conflicts (3)
    ("Do CSCI 3308 and MATH 2400 conflict with each other?", "find_schedule_conflicts"),
    ("Can I take CSCI 2270, MATH 2400, and APPM 1350 at the same time?", "find_schedule_conflicts"),
    ("Check if these courses overlap: CSCI 4831, INFO 4604", "find_schedule_conflicts"),
    # save_decision (3)
    ("I want to plan CSCI 3308 for next semester", "save_decision"),
    ("Mark CSCI 3104 as not interested", "save_decision"),
    ("Save INFO 4604 as a course I'm interested in", "save_decision"),
    # Edge cases (4)
    ("Data structures", "search_courses"),
    ("Algorithms is supposed to be really hard, what does it cover?", "search_courses"),
    ("I heard CSCI 3104 is brutal. Should I take it?", "lookup_course"),
    ("What do I still need for my degree?", "get_student_profile"),
]


def test_tool_call(query: str, expected: str, model: str) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": query},
        ],
        "tools": TOOLS,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError as e:
        return {
            "query": query,
            "expected": expected,
            "actual": None,
            "passed": False,
            "params": None,
            "error": f"Connection error: {e}",
        }
    except httpx.HTTPStatusError as e:
        return {
            "query": query,
            "expected": expected,
            "actual": None,
            "passed": False,
            "params": None,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except Exception as e:
        return {
            "query": query,
            "expected": expected,
            "actual": None,
            "passed": False,
            "params": None,
            "error": f"Unexpected error: {e}",
        }

    message = data.get("message", {})
    tool_calls = message.get("tool_calls")

    if not tool_calls:
        return {
            "query": query,
            "expected": expected,
            "actual": None,
            "passed": False,
            "params": None,
            "error": "No tool_calls in response",
        }

    first_call = tool_calls[0]
    actual_name = first_call.get("function", {}).get("name")
    raw_args = first_call.get("function", {}).get("arguments", {})

    # Validate args parse as JSON (they may already be a dict or a JSON string)
    try:
        if isinstance(raw_args, str):
            params = json.loads(raw_args)
        else:
            params = raw_args
        # Re-encode and decode to confirm it's valid JSON-serialisable
        json.loads(json.dumps(params))
    except (json.JSONDecodeError, TypeError) as e:
        return {
            "query": query,
            "expected": expected,
            "actual": actual_name,
            "passed": False,
            "params": raw_args,
            "error": f"Args not valid JSON: {e}",
        }

    return {
        "query": query,
        "expected": expected,
        "actual": actual_name,
        "passed": actual_name == expected,
        "params": params,
        "error": None,
    }


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Ollama tool-calling for CU AI assistant")
    parser.add_argument("--model", default=OLLAMA_MODEL, help="Ollama model to test")
    parser.add_argument(
        "--verbose", action="store_true", help="Show full tool call params (default: truncated)"
    )
    args = parser.parse_args()

    model = args.model
    verbose = args.verbose

    print(f"\n{'=' * 70}")
    print(f"  CU Student AI Assistant — Tool Calling Validation")
    print(f"  Model: {model}")
    print(f"  Queries: {len(TEST_QUERIES)}")
    print(f"{'=' * 70}\n")

    results = []
    for i, (query, expected) in enumerate(TEST_QUERIES, 1):
        print(f"[{i:02d}/{len(TEST_QUERIES)}] Testing: {_truncate(query, 60)}", flush=True)
        result = test_tool_call(query, expected, model)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        actual_display = result["actual"] or "(none)"

        if result["passed"]:
            params_str = ""
            if result["params"]:
                raw = json.dumps(result["params"])
                params_str = f"  params={raw if verbose else _truncate(raw, 60)}"
            print(f"  {status}  expected={expected}  actual={actual_display}{params_str}")
        else:
            error_suffix = f"  [{result['error']}]" if result.get("error") else ""
            print(
                f"  {status}  expected={expected}  actual={actual_display}{error_suffix}"
            )
        print()

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pct = passed / total * 100

    print(f"{'=' * 70}")
    print(f"  Summary: {passed}/{total} passed ({pct:.1f}%)")
    if pct < 80:
        print(
            f"\n  WARNING: Pass rate {pct:.1f}% is below 80%. "
            "Consider switching to a model with stronger tool-calling support."
        )
    print(f"{'=' * 70}\n")

    sys.exit(0 if pct >= 80 else 1)


if __name__ == "__main__":
    main()
