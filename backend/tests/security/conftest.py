import os
import importlib
import types
import copy

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import Request, Response
# from fastapi.testclient import TestClient  # not used here; keep if you need it later

from open_webui.models.users import Users
from open_webui.models.auths import Auths, SigninForm, SignupForm

# Import the adapter module once so we can patch attributes on the actual object
BA = importlib.import_module("open_webui.routers.betterauth_adapter")


@pytest.fixture
def mock_app_state():
    """Mock application state with config"""
    mock_state = Mock()
    mock_state.config = Mock()
    mock_state.config.JWT_EXPIRES_IN = "30d"
    mock_state.config.ENABLE_SIGNUP = True
    mock_state.config.ENABLE_LOGIN_FORM = True
    mock_state.config.DEFAULT_USER_ROLE = "user"
    mock_state.config.USER_PERMISSIONS = {}
    return mock_state


@pytest.fixture
def mock_request(mock_app_state):
    """Mock FastAPI request object"""
    request = Mock(spec=Request)
    request.app.state = mock_app_state
    request.client = Mock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


@pytest.fixture
def mock_response():
    """Mock FastAPI response object"""
    response = Mock(spec=Response)
    response.set_cookie = Mock()
    response.delete_cookie = Mock()
    return response


@pytest.fixture
def valid_signup_form():
    """Valid signup form data"""
    return SignupForm(
        email="test@example.com",
        password="SecurePass123!",
        name="Test User",
        profile_image_url="/user.png",
    )


@pytest.fixture
def valid_signin_form():
    """Valid signin form data"""
    return SigninForm(
        email="test@example.com",
        password="SecurePass123!",
    )


@pytest.fixture
def mock_user():
    """Mock user object"""
    user = Mock()
    user.id = "user-123"
    user.email = "test@example.com"
    user.name = "Test User"
    user.role = "user"
    user.profile_image_url = "/user.png"
    return user


@pytest.fixture
def mock_users_model():
    """Mock Users model methods"""
    with patch("open_webui.models.users.Users") as mock:
        mock.get_user_by_email = Mock(return_value=None)
        mock.get_num_users = Mock(return_value=1)
        yield mock


@pytest.fixture
def mock_auths_model():
    """Mock Auths model methods"""
    with patch("open_webui.models.auths.Auths") as mock:
        mock.insert_new_auth = Mock()
        mock.authenticate_user = Mock()
        mock.authenticate_user_by_trusted_header = Mock()
        yield mock


@pytest.fixture
def mock_betterauth_response():
    """Mock BetterAuth service response"""
    return {
        "user": {
            "id": "ba-user-123",
            "email": "test@example.com",
            "name": "Test User",
            "emailVerified": True,
            "profile_image_url": "/user.png",
        },
        "session": {
            "token": "ba-session-token",
            "expiresAt": "2025-12-31T23:59:59Z",
        },
    }


@pytest.fixture
def mock_turnstile_success():
    """Mock successful Turnstile verification"""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = {"success": True}
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )
        yield mock_client


@pytest.fixture
def mock_db_session(monkeypatch):
    """
    Patch betterauth_adapter.get_db to yield a fake connection and
    return that connection so tests can assert attributes like .execute.
    """
    class FakeResult:
        def __init__(self, val): self._val = val
        def fetchone(self): return (self._val,)

    class FakeConn:
        def __init__(self): self.executed = []
        def execute(self, *args, **kwargs):
            self.executed.append((args, kwargs))
            # simulate SELECT ... returning emailVerified=True at index 0
            return FakeResult(True)

    fake_conn = FakeConn()

    def _fake_get_db():
        # router calls: next(get_db())
        yield fake_conn

    monkeypatch.setattr(BA, "get_db", _fake_get_db, raising=True)
    return fake_conn


@pytest.fixture(autouse=True)
def reset_env_vars():
    """
    Reset environment variables before each test and yield a truthy sentinel
    so tests can assert the fixture executed.
    """
    original_env = copy.deepcopy(os.environ)

    # Clear specific keys your security routes depend on
    for k in ("BETTERAUTH_BASE_URL", "TURNSTILE_SECRET_KEY"):
        os.environ.pop(k, None)

    try:
        yield True  # <-- make the test receive a non-None value
    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
def set_betterauth_url():
    """Set BetterAuth URL environment variable"""
    os.environ["BETTERAUTH_BASE_URL"] = "http://betterauth-test:4000"
    yield
    os.environ.pop("BETTERAUTH_BASE_URL", None)


@pytest.fixture
def set_turnstile_secret():
    """Set Turnstile secret environment variable"""
    os.environ["TURNSTILE_SECRET_KEY"] = "test-secret-key"
    yield
    os.environ.pop("TURNSTILE_SECRET_KEY", None)

@pytest.fixture(autouse=True)
def stub_password_hash(monkeypatch):
    # Always return a short deterministic hash in unit tests
    monkeypatch.setattr(BA, "get_password_hash", lambda pw: "hashed", raising=True)
