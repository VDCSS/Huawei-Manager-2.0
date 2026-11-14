"""TDD de redação de segredos VRP (F0)."""
from __future__ import annotations

from huawei_manager.security_redaction import (
    redact_config_text,
    redact_secrets,
    redact_vrp_config,
)
from huawei_manager.utils import sanitize_command


class TestVrpRedaction:
    def test_local_user_irreversible_cipher(self):
        text = "local-user admin password irreversible-cipher S3nh@ForteCom12"
        out = redact_vrp_config(text)
        assert "S3nh@ForteCom12" not in out
        assert "local-user admin password [REDACTED]" == out

    def test_local_user_cipher(self):
        out = redact_config_text("local-user op password cipher abc12345")
        assert "abc12345" not in out
        assert "[REDACTED]" in out

    def test_set_authentication_password(self):
        out = redact_config_text("set authentication password cipher abc12345")
        assert "abc12345" not in out
        assert "[REDACTED]" in out

    def test_short_password_cipher(self):
        out = redact_config_text("password cipher abc12345")
        assert "abc12345" not in out
        assert "[REDACTED]" in out

    def test_sanitize_command_covers_vrp_forms(self):
        out = sanitize_command(
            "local-user admin password irreversible-cipher S3nh@ForteCom12"
        )
        assert "S3nh@ForteCom12" not in out

    def test_sanitize_command_preserves_legacy_equals(self):
        assert "password=***" in sanitize_command("configure password=secret123")

    def test_secret_exact_value_removed_from_output(self):
        secret = "S3nh@ForteCom12"
        out = redact_secrets(f"device echoed: {secret}", [secret])
        assert secret not in out
        assert "[REDACTED]" in out

    def test_secret_exact_value_longest_first(self):
        out = redact_secrets("abc abcd", ["abc", "abcd"])
        assert "abcd" not in out
        assert "abc" not in out

    def test_no_false_positive_on_display(self):
        text = "display current-configuration | include local-user"
        assert redact_config_text(text) == text
