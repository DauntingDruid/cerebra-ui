"""
Test fixtures and configurations for AI Agent Workflow Tests
Automatically configures paths to import from Open WebUI
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock


# =============================================================================
# 🔧 Auto-configure import paths to Open WebUI
# =============================================================================

def setup_import_paths():
    """
    Automatically find and configure paths to Open WebUI code
    Supports structure: cerebra-ui/backend/tests/ai_agent_workflow/ and cerebra-ui/backend/open_webui/
    """
    # Get the test directory (where conftest.py is located)
    test_dir = Path(__file__).parent.resolve()
    
    # Backend directory should be 2 levels up: tests/ai_agent_workflow -> tests -> backend
    backend_dir = test_dir.parent.parent
    
    # Add backend to Python path so we can import open_webui modules
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
        print(f"✓ Added to path: {backend_dir}")
    
    # Verify we can find open_webui
    open_webui_dir = backend_dir / "open_webui"
    if open_webui_dir.exists():
        print(f"✓ Found Open WebUI at: {open_webui_dir}")
        
        # Check for key modules
        workflows = open_webui_dir / "models" / "workflows.py"
        if workflows.exists():
            print(f"✓ Found workflows.py")
        
        workflow_executor = open_webui_dir / "utils" / "workflow_executor.py"
        if workflow_executor.exists():
            print(f"✓ Found workflow_executor.py")
            
        return True
    else:
        print(f"⚠️  Warning: Open WebUI not found at: {open_webui_dir}")
        print(f"   Expected structure: cerebra-ui/backend/open_webui/")
        print(f"   Tests may fail if they try to import from open_webui")
        return False

# Run path setup when conftest.py is loaded
setup_import_paths()


# =============================================================================
# Fixtures for AI Agent Workflow tests
# =============================================================================

@pytest.fixture
def mock_workflows_class():
    """Mock Workflows class"""
    mock = MagicMock()
    mock.create_workflow = MagicMock()
    mock.get_workflow_by_id = MagicMock()
    mock.get_workflows_by_user = MagicMock()
    mock.update_workflow = MagicMock()
    mock.delete_workflow = MagicMock()
    return mock


@pytest.fixture
def mock_executions_class():
    """Mock WorkflowExecutions class"""
    mock = MagicMock()
    mock.create_execution = MagicMock()
    mock.update_execution = MagicMock()
    mock.get_execution_by_id = MagicMock()
    mock.get_last_execution_with_session = MagicMock()
    return mock


@pytest.fixture
def db_session():
    """Mock database session fixture"""
    return Mock()


@pytest.fixture
def sample_workflow():
    """Create a sample workflow for testing"""
    mock_workflow = Mock()
    mock_workflow.id = "workflow_123"
    mock_workflow.user_id = "test_user_123"
    mock_workflow.name = "Test Workflow"
    mock_workflow.description = "Test description"
    mock_workflow.type = "deep_research"
    mock_workflow.config = {
        "api_url": "http://langraph:8080",
        "api_key": "test_key",
        "assistant_id": "test_assistant"
    }
    
    return mock_workflow


@pytest.fixture
def deep_research_workflow():
    """Create Deep Research workflow"""
    mock_workflow = Mock()
    mock_workflow.id = "deep_research_123"
    mock_workflow.user_id = "test_user_123"
    mock_workflow.name = "Deep Research Test"
    mock_workflow.type = "deep_research"
    mock_workflow.config = {
        "api_url": "http://langraph:8080",
        "api_key": "test_key",
        "assistant_id": "test_assistant"
    }
    
    return mock_workflow


@pytest.fixture
def sample_execution(sample_workflow):
    """Create a sample execution"""
    mock_execution = Mock()
    mock_execution.id = "execution_123"
    mock_execution.workflow_id = sample_workflow.id
    mock_execution.user_id = sample_workflow.user_id
    mock_execution.input_data = {"query": "test"}
    mock_execution.status = "pending"
    mock_execution.output_data = None
    mock_execution.session_id = None
    
    return mock_execution


@pytest.fixture
def mock_langgraph_response():
    """Mock LangGraph API response"""
    return {
        "thread_id": "thread_xyz_001",
        "output": {
            "messages": [
                {
                    "type": "text",
                    "content": "Machine learning is a subset of artificial intelligence..."
                }
            ]
        }
    }