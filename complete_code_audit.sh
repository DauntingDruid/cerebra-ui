#!/bin/bash

echo "🔬 Open WebUI ComfyUI 完整代码审查"
echo "===================================="
echo ""

# 1. 找到所有与ComfyUI相关的文件
echo "📂 1. 所有ComfyUI相关文件"
echo "-------------------------"
find . -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.svelte" \) -exec grep -l "comfyui\|comfy" {} \; 2>/dev/null | grep -v node_modules | grep -v ".git"

echo ""
echo "========================================"
echo ""

# 2. 查看comfyui.py的完整内容（已有，但再确认一次）
echo "📄 2. utils/images/comfyui.py 完整内容"
echo "---------------------------------------"
cat backend/open_webui/utils/images/comfyui.py

echo ""
echo "========================================"
echo ""

# 3. 查看routers/images.py中所有ComfyUI相关代码
echo "📄 3. routers/images.py 中的 ComfyUI 代码"
echo "------------------------------------------"
grep -n "comfyui\|COMFYUI" backend/open_webui/routers/images.py -i -A 3 -B 3

echo ""
echo "========================================"
echo ""

# 4. 查看完整的图像生成端点
echo "📄 4. 完整的 /generations 端点实现"
echo "-----------------------------------"
sed -n '467,700p' backend/open_webui/routers/images.py

echo ""
echo "========================================"
echo ""

# 5. 查看前端API调用文件
echo "📄 5. 前端 API 调用实现"
echo "-----------------------"
if [ -f "src/lib/apis/images/index.ts" ]; then
    echo "找到 src/lib/apis/images/index.ts:"
    cat src/lib/apis/images/index.ts
elif [ -f "src/lib/apis/images.ts" ]; then
    echo "找到 src/lib/apis/images.ts:"
    cat src/lib/apis/images.ts
elif [ -f "src/lib/apis/images.js" ]; then
    echo "找到 src/lib/apis/images.js:"
    cat src/lib/apis/images.js
else
    echo "搜索所有images相关的API文件："
    find src/lib/apis -name "*image*" 2>/dev/null
fi

echo ""
echo "========================================"
echo ""

# 6. 查看前端Images.svelte的完整逻辑
echo "📄 6. 前端配置组件关键代码"
echo "---------------------------"
if [ -f "src/lib/components/admin/Settings/Images.svelte" ]; then
    echo "Images.svelte 中的数据提交逻辑："
    grep -n "updateImageGenerationConfig\|fetch.*config" src/lib/components/admin/Settings/Images.svelte -A 10 -B 5 | head -100
fi

echo ""
echo "========================================"
echo ""

# 7. 查看默认workflow的完整定义
echo "📄 7. 默认 Workflow 完整定义"
echo "-----------------------------"
sed -n '/COMFYUI_DEFAULT_WORKFLOW/,/"""/p' backend/open_webui/config.py | head -200

echo ""
echo "========================================"
echo ""

# 8. 查看COMFYUI_WORKFLOW_NODES的默认值
echo "📄 8. Workflow Nodes 默认配置"
echo "------------------------------"
grep -n "COMFYUI_WORKFLOW_NODES" backend/open_webui/config.py -A 10 -B 5

echo ""
echo "========================================"
echo ""

# 9. 搜索是否有任何fal相关的代码
echo "🔍 9. 搜索 Fal API 相关代码"
echo "---------------------------"
echo "在Python文件中搜索'fal'："
grep -rn "fal" backend/open_webui --include="*.py" 2>/dev/null | head -20

echo ""
echo "在前端文件中搜索'fal'："
grep -rn "fal" src --include="*.svelte" --include="*.ts" --include="*.js" 2>/dev/null | head -20

echo ""
echo "========================================"
echo ""

# 10. 查看所有图像生成引擎的实现
echo "📄 10. 所有图像生成引擎"
echo "----------------------"
grep -n "IMAGE_GENERATION_ENGINE.*==" backend/open_webui/routers/images.py | head -20

echo ""
echo "查看每个引擎的实现位置："
for engine in "openai" "automatic1111" "comfyui" "gemini"; do
    echo ""
    echo "=== $engine 引擎 ==="
    grep -n "IMAGE_GENERATION_ENGINE.*==.*\"$engine\"" backend/open_webui/routers/images.py -A 5
done

echo ""
echo "========================================"
echo ""

# 11. 检查是否有任何自定义的workflow模板文件
echo "🔍 11. 搜索自定义 Workflow 文件"
echo "-------------------------------"
find . -name "*workflow*.py" -o -name "*workflow*.json" 2>/dev/null | grep -v node_modules | grep -v ".git"

echo ""
echo "搜索可能的模板目录："
find backend -type d -name "*template*" -o -name "*workflow*" 2>/dev/null

echo ""
echo "========================================"
echo ""

# 12. 查看环境变量配置
echo "📄 12. ComfyUI 环境变量"
echo "----------------------"
if [ -f ".env.example" ]; then
    echo ".env.example 中的 ComfyUI 配置："
    grep -i "comfy\|image.*gen" .env.example
fi

echo ""
echo "========================================"
echo ""

# 13. 查看数据库配置表结构
echo "💾 13. 配置存储机制"
echo "-------------------"
echo "查找get_config_value函数："
grep -n "def get_config_value" backend/open_webui --include="*.py" -r -A 20

echo ""
echo "查找set_config_value函数："
grep -n "def set_config_value" backend/open_webui --include="*.py" -r -A 20

echo ""
echo "========================================"
echo ""

# 14. 查看main.py中的初始化
echo "📄 14. 应用启动时的配置初始化"
echo "------------------------------"
grep -n "COMFYUI\|IMAGE_GENERATION" backend/open_webui/main.py | head -30

echo ""
echo "========================================"
echo ""

# 15. 检查requirements.txt中的依赖
echo "📦 15. Python 依赖检查"
echo "----------------------"
if [ -f "backend/requirements.txt" ]; then
    echo "图像生成相关的依赖："
    grep -i "image\|comfy\|fal\|stable\|diffusion" backend/requirements.txt
fi

echo ""
echo "========================================"
echo ""

# 16. 查看是否有测试文件
echo "🧪 16. ComfyUI 相关测试"
echo "----------------------"
find . -path "*/test*" -name "*.py" -exec grep -l "comfyui" {} \; 2>/dev/null

echo ""
echo "========================================"
echo ""

# 17. 查看日志配置
echo "📝 17. 日志配置"
echo "---------------"
grep -n "SRC_LOG_LEVELS\|COMFYUI.*log" backend/open_webui --include="*.py" -r | head -20

echo ""
echo "========================================"
echo ""

# 18. 检查Docker配置中的ComfyUI
echo "🐳 18. Docker 配置"
echo "-----------------"
if [ -f "docker-compose.yaml" ]; then
    grep -i "comfy" docker-compose.yaml -A 5 -B 5
fi
if [ -f "docker-compose.yml" ]; then
    grep -i "comfy" docker-compose.yml -A 5 -B 5
fi

echo ""
echo "========================================"
echo ""

# 19. 查看是否有文档
echo "📚 19. 相关文档"
echo "--------------"
find . -name "*.md" -exec grep -l "comfyui\|image.*generation" {} \; 2>/dev/null | head -10

echo ""
echo "========================================"
echo ""

# 20. 总结关键信息
echo "📊 20. 关键信息总结"
echo "-------------------"
echo "Python文件数量（包含comfyui）:"
find backend -name "*.py" -exec grep -l "comfyui" {} \; 2>/dev/null | wc -l

echo ""
echo "前端文件数量（包含comfyui）:"
find src -name "*.svelte" -o -name "*.ts" -o -name "*.js" | xargs grep -l "comfyui" 2>/dev/null | wc -l

echo ""
echo "ComfyUI相关配置项数量:"
grep -c "COMFYUI" backend/open_webui/config.py 2>/dev/null || echo "0"

echo ""
echo "========================================"
echo ""

echo "✅ 完整审查完成！"
echo ""
echo "💡 接下来请："
echo "1. 仔细阅读上面的输出"
echo "2. 确认ComfyUI的实现方式"
echo "3. 告诉我你的发现"
echo "4. 我们再讨论如何增强"
