#!/bin/bash
# Quick validation script to verify test framework is working


set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}  CerebraUI Test Framework Validation${NC}"
echo -e "${BLUE}=================================================${NC}\n"

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "Python version: ${GREEN}$PYTHON_VERSION${NC}"

# Check if pytest is installed
echo -e "\n${YELLOW}Checking pytest installation...${NC}"
if command -v pytest &> /dev/null; then
    PYTEST_VERSION=$(pytest --version | head -n1)
    echo -e "${GREEN}✓ $PYTEST_VERSION${NC}"
else
    echo -e "${RED}✗ pytest not found${NC}"
    exit 1
fi

# Check Open WebUI structure
echo -e "\n${YELLOW}Checking Open WebUI structure...${NC}"
if [ -d "../open_webui" ]; then
    echo -e "${GREEN}✓ Found ../open_webui/${NC}"
else
    echo -e "${YELLOW}⚠️  ../open_webui/ not found${NC}"
fi

# Test imports
echo -e "\n${YELLOW}Testing imports from Open WebUI...${NC}"
python3 -c "
import sys
from pathlib import Path
test_dir = Path.cwd()
backend_dir = test_dir.parent
sys.path.insert(0, str(backend_dir))
from open_webui.utils.images.prompt_analyzer import PromptAnalyzer
print('✓ Import successful')
"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Validation complete!${NC}"
else
    echo -e "${RED}❌ Validation failed${NC}"
    exit 1
fi