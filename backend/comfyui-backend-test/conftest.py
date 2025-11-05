"""
Test fixtures and configurations for CerebraUI Backend Tests
Automatically configures paths to import from Open WebUI
"""
import pytest
import asyncio
import tempfile
import shutil
import sys
from pathlib import Path
from typing import Dict, Any, Generator
from unittest.mock import Mock, AsyncMock, MagicMock
import json

# =============================================================================
# 🔧 Auto-configure import paths to Open WebUI
# =============================================================================

def setup_import_paths():
    """
    Automatically find and configure paths to Open WebUI code
    Supports structure: cerebra-ui/backend/comfyui-backend-test/ and cerebra-ui/backend/open_webui/
    """
    # Get the test directory (where conftest.py is located)
    test_dir = Path(__file__).parent.resolve()
    
    # Backend directory should be parent of test directory
    backend_dir = test_dir.parent
    
    # Add backend to Python path so we can import open_webui modules
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
        print(f"✓ Added to path: {backend_dir}")
    
    # Verify we can find open_webui
    open_webui_dir = backend_dir / "open_webui"
    if open_webui_dir.exists():
        print(f"✓ Found Open WebUI at: {open_webui_dir}")
        
        # Check for key modules
        prompt_analyzer = open_webui_dir / "utils" / "images" / "prompt_analyzer.py"
        if prompt_analyzer.exists():
            print(f"✓ Found prompt_analyzer.py")
        
        fal_flux = open_webui_dir / "utils" / "images" / "fal_flux.py"
        if fal_flux.exists():
            print(f"✓ Found fal_flux.py")
            
        return True
    else:
        print(f"⚠️  Warning: Open WebUI not found at: {open_webui_dir}")
        print(f"   Expected structure: cerebra-ui/backend/open_webui/")
        print(f"   Tests may fail if they try to import from open_webui")
        return False

# Run path setup when conftest.py is loaded
setup_import_paths()


# =============================================================================
# Session-level fixtures (created once per test session)
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """Test configuration settings"""
    return {
        "FAL_KEY": "test-fal-key-12345",
        "OPENAI_API_KEY": "test-openai-key-12345",
        "FAL_MODEL": "fal-ai/flux-pro/v1.1",
        "ENABLE_FAL_SMART_MODE": True,
        "DEFAULT_IMAGE_SIZE": "landscape_4_3",
        "INFERENCE_STEPS": 28,
        "GUIDANCE_SCALE": 3.5,
        "IMAGE_STRENGTH": 0.85,
        "TIMEOUT_SECONDS": 300,
    }


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory) -> Path:
    """Create a temporary directory for test data"""
    data_dir = tmp_path_factory.mktemp("test_data")
    return data_dir


# =============================================================================
# Function-level fixtures (created for each test function)
# =============================================================================

@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace for each test"""
    workspace = Path(tempfile.mkdtemp())
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing without API calls"""
    client = AsyncMock()
    
    # Mock successful response
    mock_response = Mock()
    mock_response.choices = [
        Mock(
            message=Mock(
                content=json.dumps({
                    "mode": "text2img",
                    "mode_confidence": 0.95,
                    "image_size": "landscape_4_3",
                    "size_confidence": 0.85,
                    "reasoning": "Test response"
                })
            )
        )
    ]
    
    client.chat.completions.create = AsyncMock(return_value=mock_response)
    return client


@pytest.fixture
def mock_fal_client():
    """Mock Fal client for testing image generation"""
    client = Mock()
    
    # Mock text2img response
    client.text2img = AsyncMock(
        return_value={
            "url": "https://fal.media/test-image.png",
            "session_id": "test-session-123",
            "mode": "text2img",
            "fal_seed": 12345,
            "width": 1024,
            "height": 768,
            "content_type": "image/png",
            "file_size": 524288,
            "meta_json": {
                "suggested_mode": "text2img",
                "mode_confidence": 0.95
            }
        }
    )
    
    # Mock img2img response
    client.img2img = AsyncMock(
        return_value={
            "url": "https://fal.media/test-image-modified.png",
            "session_id": "test-session-456",
            "mode": "img2img",
            "parent_session_id": "test-session-123",
            "fal_seed": 67890,
            "width": 1024,
            "height": 768,
            "content_type": "image/png",
            "file_size": 524288,
            "meta_json": {
                "suggested_mode": "img2img",
                "mode_confidence": 0.90
            }
        }
    )
    
    return client


@pytest.fixture
def mock_database():
    """Mock database for testing without actual DB operations"""
    db = Mock()
    
    # Mock session queries
    db.query = Mock(return_value=Mock(
        filter=Mock(return_value=Mock(
            order_by=Mock(return_value=Mock(
                first=Mock(return_value=None)
            ))
        ))
    ))
    
    # Mock session creation
    db.add = Mock()
    db.commit = Mock()
    db.refresh = Mock()
    
    return db


@pytest.fixture
def sample_prompts() -> Dict[str, Dict[str, Any]]:
    """Sample prompts for testing"""
    return {
        # Text2img prompts
        "create_english": {
            "prompt": "create a beautiful sunset over mountains",
            "expected_mode": "text2img",
            "expected_size": "landscape_4_3",
            "has_parent": False
        },
        "create_chinese": {
            "prompt": "生成一个可爱的小猫图片",
            "expected_mode": "text2img",
            "expected_size": "landscape_4_3",
            "has_parent": False
        },
        "create_square": {
            "prompt": "create a square logo with a cat",
            "expected_mode": "text2img",
            "expected_size": "square_hd",
            "has_parent": False
        },
        "create_portrait": {
            "prompt": "生成一个竖屏的人像照片",
            "expected_mode": "text2img",
            "expected_size": "portrait_4_3",
            "has_parent": False
        },
        "create_wallpaper": {
            "prompt": "design a widescreen desktop wallpaper",
            "expected_mode": "text2img",
            "expected_size": "landscape_16_9",
            "has_parent": False
        },
        
        # Img2img prompts
        "modify_color": {
            "prompt": "make it blue",
            "expected_mode": "img2img",
            "expected_size": "landscape_4_3",
            "has_parent": True
        },
        "modify_chinese": {
            "prompt": "把它改成红色",
            "expected_mode": "img2img",
            "expected_size": "landscape_4_3",
            "has_parent": True
        },
        "add_element": {
            "prompt": "add a bird to the image",
            "expected_mode": "img2img",
            "expected_size": "landscape_4_3",
            "has_parent": True
        },
        "remove_element": {
            "prompt": "remove the background",
            "expected_mode": "img2img",
            "expected_size": "landscape_4_3",
            "has_parent": True
        },
        
        # Edge cases
        "ambiguous": {
            "prompt": "blue sky",
            "expected_mode": "text2img",
            "expected_size": "landscape_4_3",
            "has_parent": False
        },
        "create_with_parent": {
            "prompt": "create a completely different cat picture",
            "expected_mode": "text2img",
            "expected_size": "landscape_4_3",
            "has_parent": True
        }
    }


@pytest.fixture
def sample_image_sessions():
    """Sample image session data for testing"""
    return [
        {
            "id": "session-001",
            "chat_id": "chat-123",
            "user_id": "user-456",
            "file_id": "file-789",
            "parent_session_id": None,
            "prompt": "create a sunset",
            "optimized_prompt": "A beautiful sunset over mountains",
            "mode": "text2img",
            "fal_seed": 12345,
            "meta_json": {
                "suggested_mode": "text2img",
                "mode_confidence": 0.95,
                "image_size": "landscape_4_3"
            },
            "created_at": 1609459200,
            "updated_at": 1609459200
        },
        {
            "id": "session-002",
            "chat_id": "chat-123",
            "user_id": "user-456",
            "file_id": "file-790",
            "parent_session_id": "session-001",
            "prompt": "make it blue",
            "optimized_prompt": "A beautiful blue sunset over mountains",
            "mode": "img2img",
            "fal_seed": 67890,
            "meta_json": {
                "suggested_mode": "img2img",
                "mode_confidence": 0.90,
                "image_size": "landscape_4_3"
            },
            "created_at": 1609462800,
            "updated_at": 1609462800
        }
    ]


@pytest.fixture
def performance_metrics():
    """Expected performance metrics for benchmarking"""
    return {
        "prompt_analysis": {
            "max_latency_ms": 100,
            "avg_latency_ms": 50,
            "p95_latency_ms": 80,
            "p99_latency_ms": 95
        },
        "database_query": {
            "max_latency_ms": 50,
            "avg_latency_ms": 20,
            "p95_latency_ms": 35,
            "p99_latency_ms": 45
        },
        "image_generation": {
            "text2img_max_seconds": 150,
            "text2img_avg_seconds": 90,
            "img2img_max_seconds": 180,
            "img2img_avg_seconds": 120
        },
        "api_endpoint": {
            "max_response_seconds": 200,
            "avg_response_seconds": 100,
            "timeout_seconds": 300
        }
    }


# =============================================================================
# Utility fixtures
# =============================================================================

@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for authentication testing"""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidXNlci00NTYiLCJleHAiOjk5OTk5OTk5OTl9.test"


@pytest.fixture
def mock_request():
    """Mock FastAPI request object"""
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    request.app.state.config = Mock()
    request.user = Mock(id="user-456")
    return request


@pytest.fixture
def mock_chat():
    """Mock chat object"""
    return {
        "id": "chat-123",
        "user_id": "user-456",
        "title": "Test Chat",
        "messages": []
    }


@pytest.fixture
async def async_mock_response():
    """Mock async response for testing"""
    response = AsyncMock()
    response.json = AsyncMock(return_value={"status": "success"})
    response.status_code = 200
    return response


# =============================================================================
# Parametrize helpers
# =============================================================================

def pytest_generate_tests(metafunc):
    """Generate parameterized tests dynamically"""
    if "prompt_test_case" in metafunc.fixturenames:
        prompts = {
            "text2img": ["create a cat", "生成一个狗", "draw a house"],
            "img2img": ["make it blue", "把它改成红色", "add a tree"],
            "edge_cases": ["blue", "", "a" * 1000]
        }
        
        test_cases = []
        for category, prompt_list in prompts.items():
            for prompt in prompt_list:
                test_cases.append((category, prompt))
        
        metafunc.parametrize("prompt_test_case", test_cases)


# =============================================================================
# Markers and tags
# =============================================================================

def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "benchmark: mark test as a benchmark"
    )
    config.addinivalue_line(
        "markers", "requires_openai: mark test as requiring OpenAI API"
    )
    config.addinivalue_line(
        "markers", "requires_fal: mark test as requiring Fal API"
    )