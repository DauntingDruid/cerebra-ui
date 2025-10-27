#!/bin/bash

TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjAwZjcyYmU1LTVkNWMtNDc1ZC1hMjgwLWI0YjE5OThjMWYwZSJ9.4mCPR5aTUnjh7bADE7piE13Y2UO9I7IePQTULM4thm8"

echo "创建测试chat..."
CHAT_RESPONSE=$(curl -s -X POST http://localhost:3000/api/v1/chats/new \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": {"name": "Debug", "models": ["gpt-4"]}}')

echo "Chat响应:"
echo "$CHAT_RESPONSE"

CHAT_ID=$(echo "$CHAT_RESPONSE" | jq -r '.id')
echo ""
echo "Chat ID: $CHAT_ID"

echo ""
echo "调用Smart API..."
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}\n" \
  -X POST http://localhost:3000/api/v1/images/generations/smart \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"$CHAT_ID\", \"prompt\": \"test\"}")

echo ""
echo "=== 完整响应 ==="
echo "$RESPONSE"

# 提取HTTP状态码
HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
echo ""
echo "HTTP状态码: $HTTP_CODE"

# 提取响应体
BODY=$(echo "$RESPONSE" | grep -v "HTTP_CODE")

echo ""
echo "=== 尝试解析JSON ==="
echo "$BODY" | jq '.' 2>&1 || echo "❌ 不是有效的JSON"
