#!/bin/bash

echo "🔍 Phase 2 完整验证"
echo "===================="
echo ""

# 1. 验证路由注册
echo "1️⃣ 验证路由注册"
echo "----------------"
docker exec open-webui cat /app/backend/open_webui/main.py | grep -A 5 "images"

echo ""
echo "2️⃣ 验证端点是否可访问"
echo "--------------------"
curl -I http://localhost:3000/api/v1/images/config 2>&1 | head -5

echo ""
echo "3️⃣ 检查smart端点的参数定义"
echo "----------------------------"
docker exec -i open-webui python3 << 'PY'
import sys
sys.path.insert(0, '/app/backend')

# 读取images.py并查找SmartGenerateImageForm
with open('/app/backend/open_webui/routers/images.py', 'r') as f:
    content = f.read()
    
# 查找表单定义
import re
pattern = r'class.*SmartGenerateImageForm.*?(?=class |@router)'
match = re.search(pattern, content, re.DOTALL)

if match:
    print("Found SmartGenerateImageForm:")
    print(match.group(0)[:500])
else:
    print("❌ SmartGenerateImageForm not found")
PY

echo ""
echo "4️⃣ 检查前端如何调用图片生成"
echo "------------------------------"
docker exec open-webui find /app/build -name "*.js" -exec grep -l "generations" {} \; | head -3

echo ""
echo "5️⃣ 测试实际API调用（需要token）"
echo "-------------------------------"
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjAwZjcyYmU1LTVkNWMtNDc1ZC1hMjgwLWI0YjE5OThjMWYwZSJ9.4mCPR5aTUnjh7bADE7piE13Y2UO9I7IePQTULM4thm8"

# 测试smart端点是否真的可以访问
curl -X POST http://localhost:3000/api/v1/images/generations/smart \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "test"}' \
  -w "\nHTTP Status: %{http_code}\n" 2>&1 | tail -20

echo ""
echo "6️⃣ 检查用户上传图片的格式"
echo "--------------------------"
docker exec -i open-webui python3 << 'PY'
import sys
sys.path.insert(0, '/app/backend')
from open_webui.models.files import Files

# 查看最近上传的文件
with Session(engine) as db:
    files = Files(db)
    recent = db.query(File).order_by(File.created_at.desc()).limit(5).all()
    
    for f in recent:
        print(f"File: {f.filename}, Path: {f.path}, Meta: {f.meta}")
PY

