#!/bin/bash
# CerebraUI Backend Test Runner
# Comprehensive test execution with multiple modes

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test directories
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="$TEST_DIR/results"

# Create results directory
mkdir -p "$RESULTS_DIR"

# Print header
echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}  CerebraUI Backend Test Suite${NC}"
echo -e "${BLUE}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${BLUE}=================================================${NC}\n"

# Function to run tests with specific markers
run_tests() {
    local test_type=$1
    local marker=$2
    local extra_args=${3:-""}
    
    echo -e "\n${YELLOW}Running ${test_type} tests...${NC}"
    
    # Run pytest and capture exit code
    pytest -m "$marker" $extra_args --tb=short --color=yes
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}[PASS] ${test_type} tests completed successfully${NC}"
        return 0
    else
        echo -e "${RED}[FAIL] ${test_type} tests had failures${NC}"
        return 1
    fi
}

# Function to display usage
show_usage() {
    cat << EOF
Usage: $0 [options]

Options:
    all         Run all tests (default)
    unit        Run unit tests only
    integration Run integration tests only
    performance Run performance benchmarks
    e2e         Run end-to-end tests
    smoke       Run quick smoke tests
    quick       Run fast tests only (unit + smoke)
    full        Run comprehensive test suite with coverage
    ci          Run tests for CI/CD pipeline
    watch       Run tests in watch mode
    help        Show this help message

Examples:
    $0 all              # Run all tests
    $0 unit             # Run only unit tests
    $0 quick            # Run fast tests for development
    $0 full             # Run full suite with coverage reports
    $0 ci               # Run tests optimized for CI/CD
EOF
}

# Parse command line arguments
MODE=${1:-all}

case $MODE in
    help)
        show_usage
        exit 0
        ;;
    
    unit)
        echo -e "${BLUE}Mode: Unit Tests Only${NC}"
        run_tests "Unit" "unit"
        exit $?
        ;;
    
    integration)
        echo -e "${BLUE}Mode: Integration Tests Only${NC}"
        run_tests "Integration" "integration"
        exit $?
        ;;
    
    performance)
        echo -e "${BLUE}Mode: Performance Benchmarks${NC}"
        run_tests "Performance" "performance or benchmark" "--durations=0"
        exit $?
        ;;
    
    e2e)
        echo -e "${BLUE}Mode: End-to-End Tests${NC}"
        run_tests "E2E" "e2e"
        exit $?
        ;;
    
    smoke)
        echo -e "${BLUE}Mode: Smoke Tests${NC}"
        run_tests "Smoke" "smoke"
        exit $?
        ;;
    
    quick)
        echo -e "${BLUE}Mode: Quick Tests (Unit + Smoke)${NC}"
        FAILED=0
        
        run_tests "Unit" "unit" || FAILED=1
        run_tests "Smoke" "smoke" || FAILED=1
        
        echo -e "\n${BLUE}=================================================${NC}"
        echo -e "${BLUE}  Quick Test Summary${NC}"
        echo -e "${BLUE}=================================================${NC}"
        
        if [ $FAILED -eq 0 ]; then
            echo -e "${GREEN}[PASS] All quick tests completed successfully${NC}"
            exit 0
        else
            echo -e "${RED}[FAIL] Some quick tests had failures${NC}"
            echo -e "${YELLOW}Check logs above for details${NC}"
            exit 1
        fi
        ;;
    
    full)
        echo -e "${BLUE}Mode: Full Test Suite with Coverage${NC}"
        FAILED=0
        
        run_tests "Unit" "unit" || FAILED=1
        run_tests "Integration" "integration" || FAILED=1
        run_tests "Performance" "performance" "--durations=10" || FAILED=1
        run_tests "E2E" "e2e" || FAILED=1
        
        echo -e "\n${BLUE}=================================================${NC}"
        echo -e "${BLUE}  Full Test Summary${NC}"
        echo -e "${BLUE}=================================================${NC}"
        
        if [ $FAILED -eq 0 ]; then
            echo -e "${GREEN}[PASS] All tests completed successfully${NC}"
            
            if [ -d "$RESULTS_DIR/coverage" ]; then
                echo -e "\n${BLUE}Coverage Report: file://$RESULTS_DIR/coverage/index.html${NC}"
            fi
            exit 0
        else
            echo -e "${RED}[FAIL] Some tests had failures${NC}"
            echo -e "${YELLOW}Check logs above for details${NC}"
            exit 1
        fi
        ;;
    
    ci)
        echo -e "${BLUE}Mode: CI/CD Pipeline${NC}"
        
        pytest \
            -v \
            --strict-markers \
            --tb=short \
            --color=yes \
            --maxfail=5 \
            --junit-xml="$RESULTS_DIR/junit.xml" \
            --cov=. \
            --cov-report=xml:"$RESULTS_DIR/coverage.xml" \
            --cov-report=html:"$RESULTS_DIR/coverage" \
            --cov-report=term-missing \
            -m "not slow"
        
        exit_code=$?
        
        echo -e "\n${BLUE}=================================================${NC}"
        echo -e "${BLUE}  CI Test Summary${NC}"
        echo -e "${BLUE}=================================================${NC}"
        
        if [ $exit_code -eq 0 ]; then
            echo -e "${GREEN}[PASS] CI tests completed successfully${NC}"
        else
            echo -e "${RED}[FAIL] CI tests had failures${NC}"
        fi
        
        exit $exit_code
        ;;
    
    watch)
        echo -e "${BLUE}Mode: Watch Mode${NC}"
        echo -e "${YELLOW}Watching for file changes... (Press Ctrl+C to stop)${NC}"
        
        # Install pytest-watch if not installed
        if ! command -v ptw &> /dev/null; then
            echo -e "${YELLOW}Installing pytest-watch...${NC}"
            pip install pytest-watch
        fi
        
        ptw --runner "pytest -v --tb=short --color=yes -m unit"
        ;;
    
    all|*)
        echo -e "${BLUE}Mode: All Tests${NC}"
        FAILED=0
        
        # Run test suites in order
        run_tests "Unit" "unit" || FAILED=1
        run_tests "Integration" "integration" || FAILED=1
        run_tests "Performance" "performance" || FAILED=1
        run_tests "E2E" "e2e" || FAILED=1
        
        # Generate summary
        echo -e "\n${BLUE}=================================================${NC}"
        echo -e "${BLUE}  Test Summary${NC}"
        echo -e "${BLUE}=================================================${NC}"
        
        if [ $FAILED -eq 0 ]; then
            echo -e "${GREEN}[PASS] All test suites completed successfully${NC}"
            
            # Display reports
            if [ -f "$RESULTS_DIR/report.html" ]; then
                echo -e "\n${BLUE}Test Report: file://$RESULTS_DIR/report.html${NC}"
            fi
            
            if [ -d "$RESULTS_DIR/coverage" ]; then
                echo -e "${BLUE}Coverage Report: file://$RESULTS_DIR/coverage/index.html${NC}"
            fi
            
            exit 0
        else
            echo -e "${RED}[FAIL] Some test suites had failures${NC}"
            echo -e "${YELLOW}Check logs above for details${NC}"
            exit 1
        fi
        ;;
esac

# Generate test report summary (for modes that don't exit earlier)
echo -e "\n${BLUE}=================================================${NC}"
echo -e "${BLUE}  Test Reports${NC}"
echo -e "${BLUE}=================================================${NC}"

if [ -f "$RESULTS_DIR/report.html" ]; then
    echo -e "${BLUE}HTML Report:     file://$RESULTS_DIR/report.html${NC}"
fi

if [ -f "$RESULTS_DIR/junit.xml" ]; then
    echo -e "${BLUE}JUnit Report:    $RESULTS_DIR/junit.xml${NC}"
fi

if [ -d "$RESULTS_DIR/coverage" ]; then
    echo -e "${BLUE}Coverage Report: file://$RESULTS_DIR/coverage/index.html${NC}"
fi

echo -e "\n${BLUE}Test Results:    $RESULTS_DIR/${NC}"
echo ""