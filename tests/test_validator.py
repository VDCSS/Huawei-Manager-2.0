"""Tests for CommandValidator — allow-list and deny-list validation."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def validator():
    from huawei_manager.sdn_controller.validator import CommandValidator

    return CommandValidator()


# ── Allow list ───────────────────────────────────────────────────────────────


class TestAllowList:
    """Commands matching allow-list must pass validation."""

    def test_display_version_allowed(self, validator):
        result = validator.validate("display version", role="user")
        assert result.allowed is True

    def test_display_ip_routing_table_allowed(self, validator):
        result = validator.validate("display ip routing-table", role="user")
        assert result.allowed is True

    def test_display_current_configuration_allowed(self, validator):
        result = validator.validate(
            "display current-configuration", role="user"
        )
        assert result.allowed is True


# ── Deny list ────────────────────────────────────────────────────────────────


class TestDenyList:
    """Commands matching deny-list must be blocked."""

    def test_format_flash_denied(self, validator):
        result = validator.validate("format flash", role="user")
        assert result.allowed is False
        assert result.reason is not None

    def test_reset_saved_configuration_denied(self, validator):
        result = validator.validate(
            "reset saved-configuration", role="user"
        )
        assert result.allowed is False

    def test_undo_startup_denied(self, validator):
        result = validator.validate("undo startup", role="user")
        assert result.allowed is False

    def test_delete_pattern_denied(self, validator):
        result = validator.validate(
            "delete backup-config.cfg", role="user"
        )
        assert result.allowed is False

    def test_reset_pattern_denied(self, validator):
        result = validator.validate("reset ip board", role="user")
        assert result.allowed is False

    def test_deny_returns_reason(self, validator):
        result = validator.validate("format flash", role="user")
        assert result.allowed is False
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


# ── Unknown commands ─────────────────────────────────────────────────────────


class TestUnknownCommands:
    """Commands not in allow or deny list must be blocked."""

    def test_unknown_command_blocked(self, validator):
        result = validator.validate(
            "some-random-command", role="user"
        )
        assert result.allowed is False
        assert "unknown" in (result.reason or "").lower()


# ── 2FA bypass ───────────────────────────────────────────────────────────────


class TestBypass2FA:
    """Admin bypasses 2FA for denied commands."""

    def test_admin_bypasses_format_flash(self, validator):
        """Admin can execute format flash (bypass 2FA)."""
        result = validator.validate("format flash", role="admin")
        assert result.allowed is True
        assert result.bypass_2fa is True

    def test_admin_bypasses_reset_saved_config(self, validator):
        result = validator.validate(
            "reset saved-configuration", role="admin"
        )
        assert result.allowed is True
        assert result.bypass_2fa is True

    def test_tecnico_bypasses_format_flash(self, validator):
        """Tecnico role also bypasses 2FA."""
        result = validator.validate("format flash", role="tecnico")
        assert result.allowed is True
        assert result.bypass_2fa is True

    def test_user_cannot_bypass_format_flash(self, validator):
        """User role cannot bypass 2FA for denied commands."""
        result = validator.validate("format flash", role="user")
        assert result.allowed is False

    def test_admin_cannot_bypass_unknown(self, validator):
        """Admin cannot bypass unknown commands."""
        result = validator.validate(
            "some-random-command", role="admin"
        )
        assert result.allowed is False


# ── ValidationResult dataclass ───────────────────────────────────────────────


class TestValidationResult:
    """ValidationResult dataclass fields."""

    def test_default_allowed(self):
        from huawei_manager.sdn_controller.validator import ValidationResult

        r = ValidationResult(allowed=True)
        assert r.allowed is True
        assert r.reason is None
        assert r.bypass_2fa is False

    def test_denied_with_reason(self):
        from huawei_manager.sdn_controller.validator import ValidationResult

        r = ValidationResult(
            allowed=False, reason="Denied by policy", bypass_2fa=False,
        )
        assert r.allowed is False
        assert r.reason == "Denied by policy"
        assert r.bypass_2fa is False

    def test_bypass_with_reason(self):
        from huawei_manager.sdn_controller.validator import ValidationResult

        r = ValidationResult(
            allowed=True, reason="Admin bypass", bypass_2fa=True,
        )
        assert r.allowed is True
        assert r.bypass_2fa is True


# ── Integration with validate_and_audit ──────────────────────────────────────


class TestValidateAndAudit:
    """validate_and_audit logs denied commands."""

    def test_allowed_command_no_audit(self, validator):
        result = validator.validate_and_audit(
            "display version", role="user",
        )
        assert result.allowed is True

    def test_denied_command_audited(self, validator):
        mock_audit = MagicMock()
        result = validator.validate_and_audit(
            "format flash", role="user", audit_logger=mock_audit,
            user="operator", host="192.168.1.1",
        )
        assert result.allowed is False
        mock_audit.log_operation.assert_called_once_with(
            "command_denied", "operator", "192.168.1.1",
            status="blocked",
            details="Command denied by policy: format flash",
        )

    def test_admin_bypass_not_audited(self, validator):
        mock_audit = MagicMock()
        result = validator.validate_and_audit(
            "format flash", role="admin", audit_logger=mock_audit,
            user="admin01", host="192.168.1.1",
        )
        assert result.allowed is True
        mock_audit.log_operation.assert_called_once_with(
            "command_bypass", "admin01", "192.168.1.1",
            status="allowed",
            details="Admin bypass for: format flash",
        )


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and special patterns."""

    def test_empty_command(self, validator):
        result = validator.validate("", role="user")
        assert result.allowed is False

    def test_whitespace_command(self, validator):
        result = validator.validate("   ", role="user")
        assert result.allowed is False

    def test_case_insensitive_deny(self, validator):
        """Deny patterns should match case-insensitively."""
        result = validator.validate("FORMAT FLASH", role="user")
        assert result.allowed is False

    def test_partial_match_not_denied(self, validator):
        """delete inside a word should not match deny pattern."""
        result = validator.validate("display delete", role="user")
        assert result.allowed is True

    def test_reset_in_show_not_denied(self, validator):
        """reset inside a show command should not match."""
        result = validator.validate("display reset-reason", role="user")
        assert result.allowed is True
