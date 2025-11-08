import pytest
from backend.open_webui.routers.betterauth_adapter import _password_policy_issues, PASSWORD_POLICY


class TestPasswordPolicy:
    """Unit tests for password policy validation"""

    def test_valid_password_no_issues(self):
        """Test that a valid password returns no issues"""
        password = "SecurePass123!"
        issues = _password_policy_issues(password)
        assert issues == []

    def test_password_too_short(self):
        """Test password shorter than minimum length"""
        password = "Short1!"
        issues = _password_policy_issues(password)
        assert any("10 characters" in issue for issue in issues)

    def test_password_missing_uppercase(self):
        """Test password without uppercase letter"""
        password = "securepass123!"
        issues = _password_policy_issues(password)
        assert any("uppercase" in issue.lower() for issue in issues)

    def test_password_missing_lowercase(self):
        """Test password without lowercase letter"""
        password = "SECUREPASS123!"
        issues = _password_policy_issues(password)
        assert any("lowercase" in issue.lower() for issue in issues)

    def test_password_missing_digit(self):
        """Test password without a digit"""
        password = "SecurePassword!"
        issues = _password_policy_issues(password)
        assert any("number" in issue.lower() for issue in issues)

    def test_password_missing_special_char(self):
        """Test password without special character"""
        password = "SecurePass123"
        issues = _password_policy_issues(password)
        assert any("special" in issue.lower() for issue in issues)

    def test_password_with_spaces(self):
        """Test password containing spaces"""
        password = "Secure Pass123!"
        issues = _password_policy_issues(password)
        assert any("spaces" in issue.lower() for issue in issues)

    def test_password_multiple_issues(self):
        """Test password with multiple validation failures"""
        password = "short"
        issues = _password_policy_issues(password)
        assert len(issues) >= 3  # Should fail multiple checks

    def test_password_minimum_length_boundary(self):
        """Test password at exact minimum length"""
        password = "SecPass12!"  # Exactly 10 characters
        issues = _password_policy_issues(password)
        assert not any("10 characters" in issue for issue in issues)

    def test_password_various_special_chars(self):
        """Test password with various special characters"""
        special_chars = ["!", "@", "#", "$", "%", "^", "&", "*"]
        for char in special_chars:
            password = f"SecurePass123{char}"
            issues = _password_policy_issues(password)
            assert issues == [], f"Failed for special char: {char}"

    def test_password_policy_constants(self):
        """Test that PASSWORD_POLICY constants are set correctly"""
        assert PASSWORD_POLICY["min_length"] == 10
        assert PASSWORD_POLICY["require_uppercase"] is True
        assert PASSWORD_POLICY["require_lowercase"] is True
        assert PASSWORD_POLICY["require_digit"] is True
        assert PASSWORD_POLICY["require_special"] is True
        assert PASSWORD_POLICY["forbid_spaces"] is True

    def test_empty_password(self):
        """Test empty password string"""
        password = ""
        issues = _password_policy_issues(password)
        assert len(issues) > 0

    def test_very_long_valid_password(self):
        """Test very long password that meets all requirements"""
        password = "SecurePassword123!" * 10  # Very long but valid
        issues = _password_policy_issues(password)
        assert issues == []

    @pytest.mark.parametrize("password,expected_issue_count", [
        ("a", 4),  # Too short, no upper, no digit, no special
        ("aA", 3),  # Too short, no digit, no special
        ("aA1", 2),  # Too short, no special
        ("aA1!", 1),  # Too short only
        ("aaaAAAA111!", 0),  # Valid
    ])
    def test_password_issue_progression(self, password, expected_issue_count):
        """Test password validation with various issue counts"""
        issues = _password_policy_issues(password)
        assert len(issues) == expected_issue_count