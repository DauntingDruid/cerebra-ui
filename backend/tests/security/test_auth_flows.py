import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException


class TestAuthenticationFlows:
    """Integration tests for complete authentication flows"""

    @pytest.mark.asyncio
    async def test_complete_signin_flow_verified_user(
        self,
        mock_request,
        mock_response,
        valid_signin_form,
        mock_db_session,
        set_betterauth_url,
        set_turnstile_secret
    ):
        """Test complete signin flow for verified user"""
        from open_webui.routers.betterauth_adapter import signin
        
        # Setup mocks
        mock_user = Mock()
        mock_user.id = "user-123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.role = "user"
        mock_user.profile_image_url = "/user.png"
        
        # Mock the JSON payload with turnstile token
        mock_request.json = AsyncMock(return_value={
            "email": "test@example.com",
            "password": "SecurePass123!",
            "turnstile_token": "valid-turnstile-token"
        })
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            with patch('open_webui.routers.betterauth_adapter.verify_turnstile_token', new_callable=AsyncMock):
                with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_ba:
                    with patch('open_webui.routers.betterauth_adapter.create_token') as mock_token:
                        with patch('open_webui.routers.betterauth_adapter.get_permissions') as mock_perms:
                            with patch('open_webui.routers.betterauth_adapter.WEBUI_AUTH', True):
                                mock_users.get_user_by_email.return_value = mock_user
                                mock_ba.return_value = {
                                    "user": {
                                        "email": "test@example.com",
                                        "name": "Test User",
                                        "emailVerified": True
                                    }
                                }
                                mock_token.return_value = "jwt-token-123"
                                mock_perms.return_value = {}
                                
                                result = await signin(mock_request, mock_response, valid_signin_form)
                                
                                assert result["token"] is not None
                                assert result["email"] == "test@example.com"
                                assert result["email_verified"] is True
                                assert result["id"] == "user-123"

    @pytest.mark.asyncio
    async def test_signin_flow_unverified_user(
        self,
        mock_request,
        mock_response,
        valid_signin_form,
        mock_db_session,
        set_betterauth_url,
        set_turnstile_secret
    ):
        """Test signin flow for unverified user returns no token"""
        from open_webui.routers.betterauth_adapter import signin
        
        # Mock DB returning emailVerified = False
        mock_db_session.execute = Mock(return_value=Mock(fetchone=Mock(return_value=(False,))))
        
        mock_request.json = AsyncMock(return_value={
            "email": "test@example.com",
            "password": "SecurePass123!",
            "turnstile_token": "valid-token"
        })
        
        with patch('open_webui.routers.betterauth_adapter.verify_turnstile_token', new_callable=AsyncMock):
            with patch('open_webui.routers.betterauth_adapter.WEBUI_AUTH', True):
                result = await signin(mock_request, mock_response, valid_signin_form)
                
                assert result["token"] is None
                assert result["email_verified"] is False
                assert result["id"] is None

    @pytest.mark.asyncio
    async def test_signin_invalid_credentials(
        self,
        mock_request,
        mock_response,
        valid_signin_form,
        mock_db_session,
        set_betterauth_url,
        set_turnstile_secret
    ):
        """Test signin with invalid credentials"""
        from open_webui.routers.betterauth_adapter import signin
        
        mock_request.json = AsyncMock(return_value={
            "email": "test@example.com",
            "password": "WrongPassword",
            "turnstile_token": "valid-token"
        })
        
        with patch('open_webui.routers.betterauth_adapter.verify_turnstile_token', new_callable=AsyncMock):
            with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_ba:
                with patch('open_webui.routers.betterauth_adapter.WEBUI_AUTH', True):
                    mock_ba.side_effect = HTTPException(status_code=401, detail="Invalid credentials")
                    
                    with pytest.raises(HTTPException) as exc_info:
                        await signin(mock_request, mock_response, valid_signin_form)
                    
                    assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_signin_missing_turnstile(
        self,
        mock_request,
        mock_response,
        valid_signin_form
    ):
        """Test signin without Turnstile token"""
        from open_webui.routers.betterauth_adapter import signin
        
        mock_request.json = AsyncMock(return_value={
            "email": "test@example.com",
            "password": "SecurePass123!"
            # No turnstile_token
        })
        
        with pytest.raises(HTTPException) as exc_info:
            await signin(mock_request, mock_response, valid_signin_form)
        
        assert exc_info.value.status_code == 400
        assert "turnstile" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_signin_new_user_creation(
        self,
        mock_request,
        mock_response,
        valid_signin_form,
        mock_db_session,
        set_betterauth_url,
        set_turnstile_secret
    ):
        """Test signin creates local user if doesn't exist"""
        from open_webui.routers.betterauth_adapter import signin
        
        new_user = Mock()
        new_user.id = "new-user-123"
        new_user.email = "test@example.com"
        new_user.name = "Test User"
        new_user.role = "user"
        new_user.profile_image_url = "/user.png"
        
        mock_request.json = AsyncMock(return_value={
            "email": "test@example.com",
            "password": "SecurePass123!",
            "turnstile_token": "valid-token"
        })
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            with patch('open_webui.routers.betterauth_adapter.Auths') as mock_auths:
                with patch('open_webui.routers.betterauth_adapter.verify_turnstile_token', new_callable=AsyncMock):
                    with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_ba:
                        with patch('open_webui.routers.betterauth_adapter.create_token'):
                            with patch('open_webui.routers.betterauth_adapter.get_permissions'):
                                with patch('open_webui.routers.betterauth_adapter.get_password_hash'):
                                    with patch('open_webui.routers.betterauth_adapter.WEBUI_AUTH', True):
                                        # User doesn't exist locally
                                        mock_users.get_user_by_email.return_value = None
                                        mock_users.get_num_users.return_value = 1
                                        mock_auths.insert_new_auth.return_value = new_user
                                        
                                        mock_ba.return_value = {
                                            "user": {
                                                "email": "test@example.com",
                                                "name": "Test User",
                                                "emailVerified": True,
                                                "profile_image_url": "/user.png"
                                            }
                                        }
                                        
                                        result = await signin(mock_request, mock_response, valid_signin_form)
                                        
                                        # Verify user was created
                                        mock_auths.insert_new_auth.assert_called_once()
                                        assert result["id"] == "new-user-123"

    @pytest.mark.asyncio
    async def test_complete_password_reset_flow(
        self,
        set_betterauth_url
    ):
        """Test complete password reset flow"""
        from open_webui.routers.betterauth_adapter import forgot_password, reset_password
        
        # Step 1: Request password reset
        with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True}
            
            result = await forgot_password({"email": "test@example.com"})
            assert result.body  # Should return JSONResponse
        
        # Step 2: Reset password with token
        with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True}
            
            result = await reset_password({
                "token": "reset-token-123",
                "password": "NewSecurePass456!"
            })
            assert result.body

    @pytest.mark.asyncio
    async def test_complete_email_verification_flow(
        self,
        set_betterauth_url
    ):
        """Test complete email verification flow"""
        from open_webui.routers.betterauth_adapter import send_verification, verify_email
        
        # Step 1: Send verification email
        with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"success": True}
            
            result = await send_verification({"email": "test@example.com"})
            assert result.body
        
        # Step 2: Verify email with token
        with patch('open_webui.routers.betterauth_adapter._get_text', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "Email verified successfully"
            
            result = await verify_email({
                "token": "verify-token-123",
                "email": "test@example.com"
            })
            assert result.body

    @pytest.mark.asyncio
    async def test_trusted_header_authentication_flow(
        self,
        mock_request,
        mock_response,
        valid_signin_form
    ):
        """Test authentication via trusted headers"""
        from open_webui.routers.betterauth_adapter import signin
        
        mock_request.headers = {
            "X-Trusted-Email": "trusted@example.com"
        }
        
        # Mock json to return turnstile token (required by signin)
        mock_request.json = AsyncMock(return_value={
            "email": "trusted@example.com",
            "password": "anything",
            "turnstile_token": "valid-token"
        })
        
        existing_user = Mock()
        existing_user.id = "trusted-user"
        existing_user.email = "trusted@example.com"
        existing_user.name = "Trusted User"
        existing_user.role = "user"
        existing_user.profile_image_url = "/user.png"
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            with patch('open_webui.routers.betterauth_adapter.Auths') as mock_auths:
                with patch('open_webui.routers.betterauth_adapter.WEBUI_AUTH_TRUSTED_EMAIL_HEADER', 'X-Trusted-Email'):
                    with patch('open_webui.routers.betterauth_adapter.create_token'):
                        with patch('open_webui.routers.betterauth_adapter.get_permissions'):
                            with patch('open_webui.routers.betterauth_adapter.verify_turnstile_token', new_callable=AsyncMock):
                                mock_users.get_user_by_email.return_value = existing_user
                                mock_auths.authenticate_user_by_trusted_header.return_value = existing_user
                                
                                result = await signin(mock_request, mock_response, valid_signin_form)
                                
                                assert result["email"] == "trusted@example.com"
                                assert result["email_verified"] is True