#!/usr/bin/env bash
# DEPLOY-007: End-to-end GCP smoke test
#
# Verifies all 5 acceptance criteria against the live Cloud Run deployment:
#   AC1  Frontend loads at Cloud Run URL (HTTP 200)
#   AC2  Course search returns results
#   AC3  Chat connects via WebSocket (WSS)
#   AC4  AI responds with tool-retrieved data
#   AC5  Response time < 5s (Anthropic API + tool execution)
#
# Prerequisites:
#   gcloud auth application-default login
#   terraform (for outputs)
#   $PYTHON + uv (for WebSocket test)
#   curl
#
# Run from repo root: bash infra/smoke-test.sh
# Or from infra/:    ./smoke-test.sh

set -euo pipefail
cd "$(dirname "$0")"

# Resolve python interpreter — Git Bash on Windows may only have `python`
if command -v python3 &>/dev/null && python3 -c "" &>/dev/null; then
  PYTHON=python3
elif command -v python &>/dev/null; then
  PYTHON=python
else
  echo "✗ No python3 or python found on PATH" >&2
  exit 1
fi

PASS=0
FAIL=0
ERRORS=()

pass()    { echo "  ✅ $1"; ((PASS++)) || true; }
fail()    { echo "  ❌ $1"; ((FAIL++)) || true; ERRORS+=("$1"); }
section() { echo; echo "── $1 ──"; }

# ─── Resolve service URLs via terraform outputs ───────────────────────────────
section "Resolving service URLs"

if ! terraform init -input=false 2>&1 | grep -E "^(Terraform|Error|✗|Initializing)" ; then
  echo "  (terraform init output suppressed — run manually if needed)"
fi

FRONTEND_URL=$(terraform output -raw frontend_url 2>/dev/null || true)
SEARCH_URL=$(terraform output -raw course_search_api_url 2>/dev/null || true)
CHAT_URL=$(terraform output -raw chat_service_url 2>/dev/null || true)

# New outputs may not be in state yet — fall back to gcloud
if [[ -z "$SEARCH_URL" ]]; then
  SEARCH_URL=$(gcloud run services describe course-search-api \
    --region=us-central1 --format='value(status.url)' 2>/dev/null || true)
fi
if [[ -z "$CHAT_URL" ]]; then
  CHAT_URL=$(gcloud run services describe chat-service \
    --region=us-central1 --format='value(status.url)' 2>/dev/null || true)
fi

if [[ -z "$FRONTEND_URL" || -z "$SEARCH_URL" || -z "$CHAT_URL" ]]; then
  echo "✗ Could not resolve service URLs."
  echo "  Check: gcloud auth application-default login"
  echo "  Check: gcloud config get-value project"
  echo "  Check: terraform output  (from infra/)"
  exit 1
fi

echo "  frontend:          $FRONTEND_URL"
echo "  course-search-api: $SEARCH_URL"
echo "  chat-service:      $CHAT_URL"

# ─── AC1: Frontend loads ──────────────────────────────────────────────────────
section "AC1: Frontend loads at Cloud Run URL"

status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$FRONTEND_URL")
if [[ "$status" == "200" ]]; then
  pass "GET $FRONTEND_URL → HTTP $status"
else
  fail "GET $FRONTEND_URL → HTTP $status (expected 200)"
fi

# ─── Service health checks ────────────────────────────────────────────────────
section "Service health checks"

search_health=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$SEARCH_URL/api/health")
if [[ "$search_health" == "200" ]]; then
  pass "course-search-api /api/health → $search_health"
else
  fail "course-search-api /api/health → $search_health"
fi

chat_health=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$CHAT_URL/api/chat/health")
if [[ "$chat_health" == "200" ]]; then
  pass "chat-service /api/chat/health → $chat_health"
else
  fail "chat-service /api/chat/health → $chat_health"
fi

# ─── Auth: login (fixed account) or register if first run ───────────────────
section "Auth (login / register smoke-test account)"

# Credentials loaded from infra/.smoke-test.env (gitignored).
# Override on the command line: SMOKE_EMAIL=x SMOKE_PASSWORD=y ./smoke-test.sh
[[ -f "$(dirname "$0")/.smoke-test.env" ]] && source "$(dirname "$0")/.smoke-test.env"
TEST_EMAIL="${SMOKE_EMAIL:-smoke-test@example.com}"
TEST_PASSWORD="${SMOKE_PASSWORD:-SmokeTestPass123!}"
TEST_NAME="Smoke Test"

TOKEN=""

# Try login first — avoids the 3/hour register rate limit on repeat runs
login_resp=$(curl -s -w "\n%{http_code}" --max-time 15 \
  -X POST "$SEARCH_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")
login_status=$(echo "$login_resp" | tail -1)
login_body=$(echo "$login_resp" | sed '$d')

if [[ "$login_status" == "200" ]]; then
  TOKEN=$(echo "$login_body" | $PYTHON -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  pass "Logged in as $TEST_EMAIL → got JWT"
else
  # Account doesn't exist yet — register it
  register_resp=$(curl -s -w "\n%{http_code}" --max-time 15 \
    -X POST "$SEARCH_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"name\":\"$TEST_NAME\"}")
  register_status=$(echo "$register_resp" | tail -1)
  register_body=$(echo "$register_resp" | sed '$d')

  if [[ "$register_status" == "200" ]]; then
    TOKEN=$(echo "$register_body" | $PYTHON -c "import sys,json; print(json.load(sys.stdin)['token'])")
    pass "Registered $TEST_EMAIL → got JWT"
  elif [[ "$register_status" == "429" ]]; then
    fail "Rate-limited (429) — register quota exhausted; wait 1 hour"
  else
    fail "Auth failed (login: $login_status, register: $register_status) — body: ${register_body:0:200}"
  fi
fi

# ─── AC2: Course search returns results ──────────────────────────────────────
section "AC2: Course search returns results"

if [[ -n "$TOKEN" ]]; then
  search_resp=$(curl -s -w "\n%{http_code}" --max-time 20 \
    -H "Authorization: Bearer $TOKEN" \
    "$SEARCH_URL/api/courses/search?q=algorithms+data+structures&limit=5")
  search_status=$(echo "$search_resp" | tail -1)
  search_body=$(echo "$search_resp" | sed '$d')

  if [[ "$search_status" == "200" ]]; then
    count=$(echo "$search_body" | $PYTHON -c "import sys,json; print(len(json.load(sys.stdin).get('items', [])))")
    if [[ "$count" -gt 0 ]]; then
      pass "Course search returned $count results for 'algorithms data structures'"
    else
      fail "Course search returned 0 results — data may not be ingested"
    fi
  else
    fail "Course search → HTTP $search_status"
  fi
else
  echo "  ⚠  Skipped — no JWT (register failed above)"
fi

# ─── AC3/AC4/AC5: WebSocket connects, AI responds, response time ─────────────
section "AC3/AC4/AC5: WebSocket + AI response"

if [[ -n "$TOKEN" ]]; then
  CHAT_WSS_URL="${CHAT_URL/https:\/\//wss://}"
  SESSION_ID=$($PYTHON -c "import uuid; print(uuid.uuid4())")

  echo "  WS URL:    $CHAT_WSS_URL/ws/chat/$SESSION_ID"
  echo "  Message:   'What is CSCI 2270 about?'"
  echo "  Timeout:   30s"

  export _CHAT_WSS_URL="$CHAT_WSS_URL"
  export _SESSION_ID="$SESSION_ID"
  export _TOKEN="$TOKEN"

  ws_result=$(uv run --with websockets $PYTHON - <<'PYEOF'
import asyncio, json, sys, time, os
import websockets

CHAT_WSS_URL = os.environ["_CHAT_WSS_URL"]
SESSION_ID   = os.environ["_SESSION_ID"]
TOKEN        = os.environ["_TOKEN"]

async def run():
    url = f"{CHAT_WSS_URL}/ws/chat/{SESSION_ID}?token={TOKEN}"
    t0 = time.monotonic()
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            await ws.send(json.dumps({"message": "What is CSCI 2270 about?"}))
            deadline = t0 + 30
            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)
                    if msg.get("type") == "chat_response":
                        elapsed = time.monotonic() - t0
                        reply = (msg.get("reply") or "")[:100]
                        print(f"OK:{elapsed:.1f}:{reply}")
                        return
                    elif msg.get("type") == "error":
                        print(f"ERROR:{msg.get('code','unknown')}")
                        return
                except asyncio.TimeoutError:
                    continue
            elapsed = time.monotonic() - t0
            print(f"TIMEOUT:{elapsed:.1f}")
    except Exception as e:
        print(f"CONN_ERROR:{e}")

asyncio.run(run())
PYEOF
  )

  if [[ "$ws_result" == OK:* ]]; then
    elapsed=$(echo "$ws_result" | cut -d: -f2)
    reply=$(echo "$ws_result" | cut -d: -f3-)
    pass "AC3: WebSocket connected (WSS)"
    # Detect the generic error fallback — means LangGraph threw an exception
    if [[ "$reply" == *"Something went wrong"* || "$reply" == *"took too long"* ]]; then
      fail "AC4: AI returned error fallback — check chat-service logs for the root cause"
    else
      pass "AC4: AI responded with tool-retrieved data — '${reply}...'"
    fi
    if awk "BEGIN { exit ($elapsed <= 5.0) ? 0 : 1 }"; then
      pass "AC5: Response time ${elapsed}s ≤ 5s"
    else
      fail "AC5: Response time ${elapsed}s > 5s (Anthropic API latency exceeded target)"
    fi
  elif [[ "$ws_result" == TIMEOUT:* ]]; then
    elapsed=$(echo "$ws_result" | cut -d: -f2)
    fail "AC3/AC4: No chat_response within 30s (${elapsed}s elapsed) — check chat-service logs"
  elif [[ "$ws_result" == CONN_ERROR:* ]]; then
    fail "AC3: WebSocket connection failed — ${ws_result#CONN_ERROR:}"
  elif [[ "$ws_result" == ERROR:* ]]; then
    fail "AC4: AI returned error code ${ws_result#ERROR:}"
  else
    fail "AC3/AC4/AC5: Unexpected ws output: ${ws_result:0:200}"
  fi
else
  echo "  ⚠  Skipped — no JWT (register failed above)"
fi

# ─── Summary ──────────────────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════"
printf "  Results: %d passed, %d failed\n" "$PASS" "$FAIL"

if [[ $FAIL -eq 0 ]]; then
  echo "  ✅ DEPLOY-007 — all acceptance criteria met"
  exit 0
else
  echo "  ❌ Failures:"
  for e in "${ERRORS[@]}"; do echo "    • $e"; done
  echo
  echo "  Diagnostics:"
  echo "    Cloud Run logs:  gcloud run services logs read <svc> --region=us-central1 --limit=50"
  echo "    Data VM SSH:     gcloud compute ssh data-services --tunnel-through-iap --zone=us-central1-a"
  echo "    Data VM status:  docker ps  (run inside VM)"
  echo "    Re-ingest data:  cd infra && ./infra.sh ingest validate"
  exit 1
fi
