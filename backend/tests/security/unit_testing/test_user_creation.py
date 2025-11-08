import pytest
from unittest.mock import Mock, patch, AsyncMock
from open_webui.routers.betterauth_adapter import ERROR_MESSAGES
from fastapi import HTTPException
from open_webui.routers.betterauth_adapter import (
    _upsert_user_bootstrap,
    _get_user_by_email,
    signup
)


class TestUserCreation:
    """Unit tests for user creation logic"""

    def test_upsert_user_bootstrap_existing_user(self):
        """Test upserting when user already exists"""
        existing_user = Mock()
        existing_user.email = "existing@example.com"
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            mock_users.get_user_by_email.return_value = existing_user
            
            result = _upsert_user_bootstrap("existing@example.com", "Existing User")
            
            assert result == existing_user
            mock_users.get_user_by_email.assert_called_once_with("existing@example.com")

    def test_upsert_user_bootstrap_new_user_first_admin(self):
        """Test upserting first user should return None (handled by signup)"""
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            mock_users.get_user_by_email.return_value = None
            mock_users.get_num_users.return_value = 0

            result = _upsert_user_bootstrap("admin@example.com", "Admin User")
            
            assert result is None

    def test_upsert_user_bootstrap_new_user_regular(self):
        """Test upserting regular user returns None"""
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            mock_users.get_user_by_email.return_value = None
            mock_users.get_num_users.return_value = 5

            result = _upsert_user_bootstrap("user@example.com", "Regular User")
            
            assert result is None

    def test_get_user_by_email_exists(self):
        """Test getting user by email when user exists"""
        mock_user = Mock()
        mock_user.email = "test@example.com"
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            mock_users.get_user_by_email.return_value = mock_user

            result = _get_user_by_email("test@example.com")
            
            assert result == mock_user
            mock_users.get_user_by_email.assert_called_once_with("test@example.com")

    def test_get_user_by_email_not_exists(self):
        """Test getting user by email when user doesn't exist"""
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            mock_users.get_user_by_email.return_value = None

            result = _get_user_by_email("nonexistent@example.com")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_signup_success_first_user(
        self, 
        mock_request, 
        mock_response, 
        valid_signup_form,
        set_betterauth_url
    ):
        """Test successful signup for first user (becomes admin)"""
        mock_user = Mock()
        mock_user.email = "admin@example.com"
        mock_user.role = "admin"
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            with patch('open_webui.routers.betterauth_adapter.Auths') as mock_auths:
                with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_post:
                    with patch('open_webui.routers.betterauth_adapter.get_password_hash') as mock_hash:
                        mock_users.get_user_by_email.return_value = None
                        mock_users.get_num_users.return_value = 0
                        mock_auths.insert_new_auth.return_value = mock_user
                        mock_post.return_value = {"success": True}
                        mock_hash.return_value = "hashed_password"
                        
                        result = await signup(mock_request, mock_response, valid_signup_form)
                        
                        assert result["status"] is True
                        assert "verify your email" in result["message"].lower()
                        assert result["email"] == valid_signup_form.email.lower()

    @pytest.mark.asyncio
    async def test_signup_success_regular_user(
        self, 
        mock_request, 
        mock_response, 
        valid_signup_form,
        set_betterauth_url
    ):
        """Test successful signup for regular user"""
        mock_user = Mock()
        mock_user.email = "user@example.com"
        mock_user.role = "user"
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            with patch('open_webui.routers.betterauth_adapter.Auths') as mock_auths:
                with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_post:
                    with patch('open_webui.routers.betterauth_adapter.get_password_hash') as mock_hash:
                        mock_users.get_user_by_email.return_value = None
                        mock_users.get_num_users.return_value = 5
                        mock_auths.insert_new_auth.return_value = mock_user
                        mock_post.return_value = {"success": True}
                        mock_hash.return_value = "hashed_password"
                        
                        result = await signup(mock_request, mock_response, valid_signup_form)
                        
                        assert result["status"] is True
                        mock_auths.insert_new_auth.assert_called_once()
                        call_args = mock_auths.insert_new_auth.call_args[0]
                        # Verify role is default (user) not admin
                        assert call_args[4] == "user"

    @pytest.mark.asyncio
    async def test_signup_existing_email(
        self, 
        mock_request, 
        mock_response, 
        valid_signup_form
    ):
        """Test signup with existing email"""
        existing_user = Mock()
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            mock_users.get_user_by_email.return_value = existing_user

            with pytest.raises(HTTPException) as exc_info:
                await signup(mock_request, mock_response, valid_signup_form)
            
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == ERROR_MESSAGES.EMAIL_TAKEN

    @pytest.mark.asyncio
    async def test_signup_weak_password(
        self, 
        mock_request, 
        mock_response
    ):
        """Test signup with weak password"""
        from open_webui.models.auths import SignupForm
        
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            mock_users.get_user_by_email.return_value = None
            mock_users.get_num_users.return_value = 1
            
            weak_form = SignupForm(
                email="test@example.com",
                password="weak",
                name="Test User"
            )

            with pytest.raises(HTTPException) as exc_info:
                await signup(mock_request, mock_response, weak_form)
            
            assert exc_info.value.status_code == 400
            assert "Password must have" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_signup_disabled(self, mock_request, mock_response, valid_signup_form):
        """Test signup when signup is disabled"""
        mock_request.app.state.config.ENABLE_SIGNUP = False
        
        with patch('open_webui.routers.betterauth_adapter.WEBUI_AUTH', True):
            with pytest.raises(HTTPException) as exc_info:
                await signup(mock_request, mock_response, valid_signup_form)
            
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_signup_betterauth_failure(
        self,
        mock_request,
        mock_response,
        valid_signup_form,
        set_betterauth_url
    ):
        """Test signup when BetterAuth service fails"""
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_post:
                mock_users.get_user_by_email.return_value = None
                mock_users.get_num_users.return_value = 1
                mock_post.side_effect = HTTPException(status_code=500, detail="BetterAuth error")
                
                with pytest.raises(HTTPException) as exc_info:
                    await signup(mock_request, mock_response, valid_signup_form)
                
                assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_signup_local_db_failure(
        self,
        mock_request,
        mock_response,
        valid_signup_form,
        set_betterauth_url
    ):
        """Test signup when local database insert fails"""
        with patch('open_webui.routers.betterauth_adapter.Users') as mock_users:
            with patch('open_webui.routers.betterauth_adapter.Auths') as mock_auths:
                with patch('open_webui.routers.betterauth_adapter._post_json', new_callable=AsyncMock) as mock_post:
                    with patch('open_webui.routers.betterauth_adapter.get_password_hash') as mock_hash:
                        mock_users.get_user_by_email.return_value = None
                        mock_users.get_num_users.return_value = 1
                        mock_auths.insert_new_auth.return_value = None  # Simulate failure
                        mock_post.return_value = {"success": True}
                        mock_hash.return_value = "hashed_password"
                        
                        with pytest.raises(HTTPException) as exc_info:
                            await signup(mock_request, mock_response, valid_signup_form)
                        
                        assert exc_info.value.status_code == 500
                        assert exc_info.value.detail == ERROR_MESSAGES.CREATE_USER_ERROR