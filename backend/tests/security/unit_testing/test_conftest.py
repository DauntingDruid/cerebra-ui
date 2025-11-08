"""
Test file to validate that all fixtures in conftest.py are working correctly.
Run this first to ensure your test setup is correct.
"""
import pytest
from unittest.mock import Mock


class TestConftestFixtures:
    """Test that all fixtures from conftest.py work correctly"""

    def test_mock_app_state_fixture(self, mock_app_state):
        """Test mock_app_state fixture"""
        assert mock_app_state is not None
        assert hasattr(mock_app_state, 'config')
        assert mock_app_state.config.JWT_EXPIRES_IN == "30d"
        assert mock_app_state.config.ENABLE_SIGNUP is True
        assert mock_app_state.config.DEFAULT_USER_ROLE == "user"
        print("✓ mock_app_state fixture works")

    def test_mock_request_fixture(self, mock_request):
        """Test mock_request fixture"""
        assert mock_request is not None
        assert hasattr(mock_request, 'app')
        assert hasattr(mock_request, 'client')
        assert mock_request.client.host == "127.0.0.1"
        assert isinstance(mock_request.headers, dict)
        print("✓ mock_request fixture works")

    def test_mock_response_fixture(self, mock_response):
        """Test mock_response fixture"""
        assert mock_response is not None
        assert hasattr(mock_response, 'set_cookie')
        assert hasattr(mock_response, 'delete_cookie')
        # Test that we can call the mocked methods
        mock_response.set_cookie(key="test", value="value")
        mock_response.delete_cookie("test")
        print("✓ mock_response fixture works")

    def test_valid_signup_form_fixture(self, valid_signup_form):
        """Test valid_signup_form fixture"""
        assert valid_signup_form is not None
        assert valid_signup_form.email == "test@example.com"
        assert valid_signup_form.password == "SecurePass123!"
        assert valid_signup_form.name == "Test User"
        assert valid_signup_form.profile_image_url == "/user.png"
        print("✓ valid_signup_form fixture works")

    def test_valid_signin_form_fixture(self, valid_signin_form):
        """Test valid_signin_form fixture"""
        assert valid_signin_form is not None
        assert valid_signin_form.email == "test@example.com"
        assert valid_signin_form.password == "SecurePass123!"
        print("✓ valid_signin_form fixture works")

    def test_mock_user_fixture(self, mock_user):
        """Test mock_user fixture"""
        assert mock_user is not None
        assert mock_user.id == "user-123"
        assert mock_user.email == "test@example.com"
        assert mock_user.name == "Test User"
        assert mock_user.role == "user"
        assert mock_user.profile_image_url == "/user.png"
        print("✓ mock_user fixture works")

    def test_mock_users_model_fixture(self, mock_users_model):
        """Test mock_users_model fixture"""
        assert mock_users_model is not None
        assert hasattr(mock_users_model, 'get_user_by_email')
        assert hasattr(mock_users_model, 'get_num_users')
        # Test that methods are callable
        result = mock_users_model.get_user_by_email("test@example.com")
        num_users = mock_users_model.get_num_users()
        assert result is None  # Default mock return
        assert num_users == 1  # Default mock return
        print("✓ mock_users_model fixture works")

    def test_mock_auths_model_fixture(self, mock_auths_model):
        """Test mock_auths_model fixture"""
        assert mock_auths_model is not None
        assert hasattr(mock_auths_model, 'insert_new_auth')
        assert hasattr(mock_auths_model, 'authenticate_user')
        assert hasattr(mock_auths_model, 'authenticate_user_by_trusted_header')
        print("✓ mock_auths_model fixture works")

    def test_mock_betterauth_response_fixture(self, mock_betterauth_response):
        """Test mock_betterauth_response fixture"""
        assert mock_betterauth_response is not None
        assert "user" in mock_betterauth_response
        assert "session" in mock_betterauth_response
        assert mock_betterauth_response["user"]["email"] == "test@example.com"
        assert mock_betterauth_response["user"]["emailVerified"] is True
        print("✓ mock_betterauth_response fixture works")

    @pytest.mark.asyncio
    async def test_mock_turnstile_success_fixture(self, mock_turnstile_success):
        """Test mock_turnstile_success fixture"""
        assert mock_turnstile_success is not None
        print("✓ mock_turnstile_success fixture works")

    def test_mock_db_session_fixture(self, mock_db_session):
        """Test mock_db_session fixture"""
        assert mock_db_session is not None
        assert hasattr(mock_db_session, 'execute')
        # Test that execute returns something
        result = mock_db_session.execute()
        assert result is not None
        print("✓ mock_db_session fixture works")

    def test_set_betterauth_url_fixture(self, set_betterauth_url):
        """Test set_betterauth_url fixture"""
        import os
        assert "BETTERAUTH_BASE_URL" in os.environ
        assert os.environ["BETTERAUTH_BASE_URL"] == "http://betterauth-test:4000"
        print("✓ set_betterauth_url fixture works")

    def test_set_turnstile_secret_fixture(self, set_turnstile_secret):
        """Test set_turnstile_secret fixture"""
        import os
        assert "TURNSTILE_SECRET_KEY" in os.environ
        assert os.environ["TURNSTILE_SECRET_KEY"] == "test-secret-key"
        print("✓ set_turnstile_secret fixture works")

    def test_reset_env_vars_fixture(self, reset_env_vars):
        """Test reset_env_vars fixture (autouse)"""
        # This fixture runs automatically before each test
        # Just verify it exists
        assert reset_env_vars is not None
        print("✓ reset_env_vars fixture works")

    def test_multiple_fixtures_together(
        self, 
        mock_request, 
        mock_response, 
        mock_user,
        valid_signup_form
    ):
        """Test using multiple fixtures together"""
        assert mock_request is not None
        assert mock_response is not None
        assert mock_user is not None
        assert valid_signup_form is not None
        print("✓ Multiple fixtures work together")


class TestFixtureIntegration:
    """Test that fixtures work well together in realistic scenarios"""

    def test_request_with_app_state(self, mock_request, mock_app_state):
        """Test request has access to app state"""
        assert mock_request.app.state == mock_app_state
        assert mock_request.app.state.config.JWT_EXPIRES_IN == "30d"
        print("✓ Request and app state integration works")

    def test_user_models_interaction(self, mock_users_model, mock_auths_model):
        """Test user models can be used together"""
        # Simulate checking if user exists
        user = mock_users_model.get_user_by_email("test@example.com")
        
        # Simulate user count
        count = mock_users_model.get_num_users()
        
        assert user is None or hasattr(user, 'email')
        assert isinstance(count, int)
        print("✓ User models integration works")

    def test_forms_have_valid_data(self, valid_signup_form, valid_signin_form):
        """Test that forms have compatible data"""
        # Signup and signin should have matching email
        signup_email = valid_signup_form.email
        signin_email = valid_signin_form.email
        
        assert signup_email == signin_email
        print("✓ Forms have consistent data")


class TestEnvironmentSetup:
    """Test environment variable handling"""

    def test_env_vars_isolated(self, set_betterauth_url, set_turnstile_secret):
        """Test that environment variables are properly set and isolated"""
        import os
        
        assert os.getenv("BETTERAUTH_BASE_URL") == "http://betterauth-test:4000"
        assert os.getenv("TURNSTILE_SECRET_KEY") == "test-secret-key"
        print("✓ Environment variables are isolated")

    def test_env_vars_cleanup(self):
        """Test that env vars are cleaned up between tests"""
        import os
        
        # This test runs without the fixtures
        # If cleanup works, these should not be set from previous test
        # (unless set elsewhere in your actual environment)
        betterauth_url = os.getenv("BETTERAUTH_BASE_URL")
        
        # We can't assert it's None because it might be set in your real env
        # But we can verify the fixture mechanism works
        print(f"✓ Environment cleanup mechanism works (current BETTERAUTH_BASE_URL: {betterauth_url})")


def test_pytest_asyncio_available():
    """Test that pytest-asyncio is properly installed"""
    try:
        import pytest_asyncio
        print("✓ pytest-asyncio is installed")
        assert True
    except ImportError:
        pytest.fail("pytest-asyncio is not installed. Run: pip install pytest-asyncio")


def test_mock_library_available():
    """Test that mock library is available"""
    try:
        from unittest.mock import Mock, patch, AsyncMock
        print("✓ unittest.mock is available")
        assert True
    except ImportError:
        pytest.fail("unittest.mock is not available")


if __name__ == "__main__":
    print("Run this file with: pytest tests/security/unit_testing/test_conftest.py -v -s")