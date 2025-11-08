import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import HTTPException
import aiohttp


class TestBetterAuthIntegration:
    """Integration tests for BetterAuth service communication"""

    @pytest.mark.asyncio
    async def test_post_json_success(self, set_betterauth_url):
        """Test successful POST request to BetterAuth"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        expected_response = {"success": True, "data": "test"}
        
        # Create a mock response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=expected_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await _post_json("/test-endpoint", {"key": "value"})
            
            assert result == expected_response

    @pytest.mark.asyncio
    async def test_post_json_http_error(self, set_betterauth_url):
        """Test POST request handling HTTP errors"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        # Create a mock response with error
        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.json = AsyncMock(return_value={"error": "Bad request"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            with pytest.raises(HTTPException) as exc_info:
                await _post_json("/test-endpoint", {})
            
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_post_json_network_timeout(self, set_betterauth_url):
        """Test POST request with network timeout"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        # Create a mock session that raises timeout
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("Timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            with pytest.raises(aiohttp.ClientError):
                await _post_json("/test-endpoint", {})

    @pytest.mark.asyncio
    async def test_post_json_malformed_response(self, set_betterauth_url):
        """Test POST request with malformed JSON response"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        # Create a mock response with malformed JSON
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(side_effect=Exception("Invalid JSON"))
        mock_resp.text = AsyncMock(return_value="Plain text response")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await _post_json("/test-endpoint", {})
            
            assert "message" in result
            assert result["message"] == "Plain text response"

    @pytest.mark.asyncio
    async def test_get_text_success(self, set_betterauth_url):
        """Test successful GET request returning text"""
        from open_webui.routers.betterauth_adapter import _get_text
        
        expected_text = "Verification successful"
        
        # Create a mock response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value=expected_text)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await _get_text("/verify", {"token": "123"})
            
            assert result == expected_text

    @pytest.mark.asyncio
    async def test_get_text_http_error(self, set_betterauth_url):
        """Test GET request handling HTTP errors"""
        from open_webui.routers.betterauth_adapter import _get_text
        
        # Create a mock response with error
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.text = AsyncMock(return_value='{"error": "Not found"}')
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            with pytest.raises(HTTPException) as exc_info:
                await _get_text("/verify", {"token": "invalid"})
            
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_betterauth_url_not_configured(self):
        """Test behavior when BetterAuth URL is not configured"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        with patch('open_webui.routers.betterauth_adapter.BETTERAUTH_BASE_URL', None):
            with pytest.raises(HTTPException) as exc_info:
                await _post_json("/test", {})
            
            assert exc_info.value.status_code == 500
            assert "not configured" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_turnstile_verification_success(self, set_turnstile_secret):
        """Test successful Turnstile token verification"""
        from open_webui.routers.betterauth_adapter import verify_turnstile_token
        
        # Create mock response - json() is a regular method in httpx, not async
        mock_response = Mock()
        mock_response.json = Mock(return_value={"success": True})
        
        # Create mock client
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            # Should not raise exception
            await verify_turnstile_token("valid-token", "127.0.0.1")

    @pytest.mark.asyncio
    async def test_turnstile_verification_failure(self, set_turnstile_secret):
        """Test failed Turnstile token verification"""
        from open_webui.routers.betterauth_adapter import verify_turnstile_token
        
        # Create mock response - json() is a regular method in httpx, not async
        mock_response = Mock()
        mock_response.json = Mock(return_value={
            "success": False,
            "error-codes": ["invalid-input-response"]
        })
        
        # Create mock client
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await verify_turnstile_token("invalid-token", "127.0.0.1")
            
            assert exc_info.value.status_code == 400
            assert "turnstile" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_turnstile_not_configured(self):
        """Test Turnstile verification when not configured"""
        from open_webui.routers.betterauth_adapter import verify_turnstile_token
        
        with patch('open_webui.routers.betterauth_adapter.TURNSTILE_SECRET', ''):
            with pytest.raises(HTTPException) as exc_info:
                await verify_turnstile_token("token", "127.0.0.1")
            
            assert exc_info.value.status_code == 500
            assert "not configured" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_betterauth_signup_integration(self, set_betterauth_url):
        """Test integration with BetterAuth signup endpoint"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        user_data = {
            "name": "Test User",
            "email": "test@example.com",
            "password": "SecurePass123!",
            "profile_image_url": "/user.png"
        }
        
        expected_response = {
            "user": {
                "id": "ba-123",
                "email": user_data["email"],
                "emailVerified": False
            }
        }
        
        # Create a mock response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=expected_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await _post_json("/api/auth/signup", user_data)
            
            assert "user" in result
            assert result["user"]["email"] == user_data["email"]

    @pytest.mark.asyncio
    async def test_betterauth_login_integration(self, set_betterauth_url):
        """Test integration with BetterAuth login endpoint"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        credentials = {
            "email": "test@example.com",
            "password": "SecurePass123!"
        }
        
        expected_response = {
            "user": {
                "id": "ba-123",
                "email": credentials["email"],
                "emailVerified": True
            },
            "session": {
                "token": "session-token"
            }
        }
        
        # Create a mock response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=expected_response)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await _post_json("/api/auth/login", credentials)
            
            assert "user" in result
            assert "session" in result

    @pytest.mark.asyncio
    async def test_request_timeout_configuration(self, set_betterauth_url):
        """Test that requests have appropriate timeout configuration"""
        from open_webui.routers.betterauth_adapter import _post_json
        
        # Create a mock response
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)
        
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session) as mock_session_cls:
            with patch('aiohttp.ClientTimeout') as mock_timeout:
                await _post_json("/test", {})
                
                # Verify timeout was configured
                mock_timeout.assert_called_with(total=15)

    def test_error_message_extraction(self):
        """Test extraction of error messages from various response formats"""
        from open_webui.routers.betterauth_adapter import _string_error
        
        # Test dict with detail
        assert _string_error({"detail": "Error message"}) == "Error message"
        
        # Test dict with error
        assert _string_error({"error": "Another error"}) == "Another error"
        
        # Test dict with message
        assert _string_error({"message": "Message text"}) == "Message text"
        
        # Test list
        result = _string_error(["error1", "error2"])
        assert isinstance(result, str)
        
        # Test None
        assert _string_error(None) == "Request failed"
        
        # Test plain string
        assert _string_error("Simple error") == "Simple error"