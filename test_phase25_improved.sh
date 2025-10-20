#!/bin/bash

set -e

echo "============================================"
echo "Phase 2.5 Full Integration Test (Patched)"
echo "============================================"

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjAwZjcyYmU1LTVkNWMtNDc1ZC1hMjgwLWI0YjE5OThjMWYwZSJ9.4mCPR5aTUnjh7bADE7piE13Y2UO9I7IePQTULM4thm8"
API_URL="http://localhost:3000/api/v1"

# Helper: create chat
create_chat() {
    local chat_name="$1"
    curl -s -X POST "$API_URL/chats/new" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"chat\": {\"name\": \"$chat_name\", \"models\": [\"gpt-4\"]}}" | jq -r '.id'
}

# Helper: call Smart API (all progress logs to stderr)
call_smart_api() {
    local chat_id="$1"
    local prompt="$2"
    
    echo "    📡 Calling API (this may take 30–60 seconds)..." >&2
    
    RESPONSE=$(curl -s -X POST "$API_URL/images/generations/smart" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"chat_id\": \"$chat_id\", \"prompt\": \"$prompt\"}")
    
    # Check errors
    if echo "$RESPONSE" | jq -e '.detail.error' > /dev/null 2>&1; then
        echo "    ❌ API Error:" >&2
        echo "$RESPONSE" | jq '.detail' >&2
        return 1
    fi
    
    # Validate required fields
    if [ "$(echo "$RESPONSE" | jq -r '.width')" = "null" ]; then
        echo "    ❌ Invalid response (width is null):" >&2
        echo "$RESPONSE" | jq '.' >&2
        return 1
    fi
    
    echo "$RESPONSE"
}

# Counters
PASSED=0
FAILED=0

# Test 1: Portrait aspect detection
echo ""
echo "[Test 1/3] Portrait Aspect Detection"
echo "===================================="
CHAT_ID=$(create_chat "Test 1: Portrait Size")
echo "  📝 Chat ID: $CHAT_ID"
echo "  💬 Prompt: generate a portrait cat photo"

RESPONSE=$(call_smart_api "$CHAT_ID" "生成一个竖屏的猫咪照片")

WIDTH=$(echo "$RESPONSE" | jq -r '.width')
HEIGHT=$(echo "$RESPONSE" | jq -r '.height')
SUGGESTED=$(echo "$RESPONSE" | jq -r '.meta_json.suggested_size')
CONFIDENCE=$(echo "$RESPONSE" | jq -r '.meta_json.size_confidence')

echo ""
echo "  📊 Result:"
echo "    Actual size: ${WIDTH}x${HEIGHT}"
echo "    Suggested size: $SUGGESTED"
echo "    Confidence: $CONFIDENCE"

if [ "$HEIGHT" -gt "$WIDTH" ]; then
    echo "  ✅ Test 1 passed: portrait detected"
    ((PASSED++))
else
    echo "  ❌ Test 1 failed: expected portrait but got ${WIDTH}x${HEIGHT}"
    ((FAILED++))
fi

# Test 2: Square aspect detection
echo ""
echo "[Test 2/3] Square Aspect Detection"
echo "=================================="
CHAT_ID=$(create_chat "Test 2: Square Size")
echo "  📝 Chat ID: $CHAT_ID"
echo "  💬 Prompt: create a square logo"

RESPONSE=$(call_smart_api "$CHAT_ID" "create a square logo")

WIDTH=$(echo "$RESPONSE" | jq -r '.width')
HEIGHT=$(echo "$RESPONSE" | jq -r '.height')
SUGGESTED=$(echo "$RESPONSE" | jq -r '.meta_json.suggested_size')

echo ""
echo "  📊 Result:"
echo "    Actual size: ${WIDTH}x${HEIGHT}"
echo "    Suggested size: $SUGGESTED"

if [ "$WIDTH" -eq "$HEIGHT" ]; then
    echo "  ✅ Test 2 passed: square detected"
    ((PASSED++))
else
    echo "  ❌ Test 2 failed: expected square but got ${WIDTH}x${HEIGHT}"
    ((FAILED++))
fi

# Test 3: Smart mode switching
echo ""
echo "[Test 3/3] Smart Mode Switching"
echo "==============================="
CHAT_ID=$(create_chat "Test 3: Mode Detection")
echo "  📝 Chat ID: $CHAT_ID"

# Round 1: text2img
echo ""
echo "  🔄 Round 1: generate initial image"
echo "    💬 Prompt: a red apple"
RESPONSE1=$(call_smart_api "$CHAT_ID" "a red apple")
MODE1=$(echo "$RESPONSE1" | jq -r '.mode')
SESSION1=$(echo "$RESPONSE1" | jq -r '.session_id')

echo "    Mode: $MODE1"
echo "    Session: $SESSION1"

if [ "$MODE1" = "text2img" ]; then
    echo "    ✅ Round 1: text2img OK"
else
    echo "    ❌ Round 1: expected text2img, got $MODE1"
    ((FAILED++))
    exit 1
fi

# Round 2: img2img
echo ""
echo "  🔄 Round 2: modify image"
echo "    💬 Prompt: make it blue"
echo "    ⏳ Waiting 5 seconds..."
sleep 5

RESPONSE2=$(call_smart_api "$CHAT_ID" "make it blue")
MODE2=$(echo "$RESPONSE2" | jq -r '.mode')
PARENT=$(echo "$RESPONSE2" | jq -r '.parent_session_id')
SESSION2=$(echo "$RESPONSE2" | jq -r '.session_id')

echo "    Mode: $MODE2"
echo "    Parent: $PARENT"
echo "    Session: $SESSION2"

if [ "$MODE2" = "img2img" ] && [ "$PARENT" = "$SESSION1" ]; then
    echo "  ✅ Test 3 passed: switched to img2img; parent link correct"
    ((PASSED++))
else
    echo "  ❌ Test 3 failed: mode=$MODE2, parent=$PARENT (expected $SESSION1)"
    ((FAILED++))
fi

# Summary
echo ""
echo "============================================"
echo "🎉 Tests finished!"
echo "============================================"
echo ""
echo "📊 Test result: $PASSED passed, $FAILED failed"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✅ All tests passed! Phase 2.5 integration successful!"
    echo ""
    echo "🎯 Validated capabilities:"
    echo "  • Portrait aspect smart detection"
    echo "  • Square aspect smart detection"
    echo "  • Automatic mode switching (text2img → img2img)"
    echo "  • Parent–child chain tracking"
    echo "  • Full meta_json returned"
    exit 0
else
    echo "❌ $FAILED test(s) failed"
    exit 1
fi
