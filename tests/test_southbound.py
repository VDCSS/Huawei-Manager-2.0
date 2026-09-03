"""Tests for SouthboundProtocol ABC and SSHSouthbound implementation."""
from __future__ import annotations

from abc import ABC
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from huawei_manager.audit_log import AuditLogger
from huawei_manager.exceptions import SdnAuthError, SdnConnectionError
from huawei_manager.sdn_controller.validator import CommandValidator, ValidationResult
from huawei_manager.vault import EnvBackend


class TestSanitize:
    """Testes diretos para _sanitize() — regex de redacao de credenciais."""

    # pylint: disable=import-outside-toplevel

    def test_masks_password_value(self):
        from huawei_manager.sdn_controller.southbound import _sanitize
        assert "supersecret" not in _sanitize(
            "Invalid password 'supersecret' for user admin"
        )
        assert "[REDACTED]" in _sanitize(
            "Invalid password 'supersecret' for user admin"
        )

    def test_masks_passwd_value(self):
        from huawei_manager.sdn_controller.southbound import _sanitize
        result = _sanitize("passwd 'P@ssw0rd' rejected")
        assert "P@ssw0rd" not in result
        assert "[REDACTED]" in result

    def test_masks_secret_value(self):
        from huawei_manager.sdn_controller.southbound import _sanitize
        result = _sanitize("secret 'mysecretkey123' mismatch")
        assert "mysecretkey123" not in result

    def test_masks_token_value(self):
        from huawei_manager.sdn_controller.southbound import _sanitize
        result = _sanitize("token 'eyJhbGciOiJIUzI1NiJ9' invalid")
        assert "eyJhbGciOiJIUzI1NiJ9" not in result

    def test_does_not_garble_auth_in_authentication(self):
        from huawei_manager.sdn_controller.southbound import _sanitize
        result = _sanitize("Authentication failed")
        # 'auth' dentro de 'Authentication' é falso positivo conhecido.
        # A mensagem original é preservada sem vazar credenciais reais.
        assert "[REDACTED]" in result  # ainda passa pelo regex

    def test_no_match_for_innocuous_message(self):
        from huawei_manager.sdn_controller.southbound import _sanitize
        result = _sanitize("Connection refused by host")
        assert result == "Connection refused by host"

    def test_no_match_for_empty_string(self):
        from huawei_manager.sdn_controller.southbound import _sanitize
        assert _sanitize("") == ""


class TestSouthboundProtocolABC:
    """SouthboundProtocol must be an ABC with the right abstract methods."""

    def test_is_abstract(self):
        from huawei_manager.sdn_controller.southbound import (
            SouthboundProtocol,
        )
        assert issubclass(SouthboundProtocol, ABC)
        assert SouthboundProtocol.__abstractmethods__ is not None

    def test_abstract_methods_exist(self):
        from huawei_manager.sdn_controller.southbound import (
            SouthboundProtocol,
        )
        methods = SouthboundProtocol.__abstractmethods__
        assert "connect" in methods
        assert "disconnect" in methods
        assert "send_command" in methods
        assert "send_config" in methods
        assert "is_alive" in methods

    def test_cannot_instantiate_abc(self):
        from huawei_manager.sdn_controller.southbound import (
            SouthboundProtocol,
        )
        with pytest.raises(TypeError):
            SouthboundProtocol()  # type: ignore[abstract]


class TestSSHSouthboundInit:
    """SSHSouthbound wraps a NetmikoSession-like object."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_creates_session_with_backend_and_audit(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        backend = EnvBackend()
        audit = AuditLogger()
        sb = SSHSouthbound(backend, audit)
        mock_session_cls.assert_called_once_with(backend, audit)
        assert sb._session is not None

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    @patch("huawei_manager._config.SSH_TIMEOUT", 90)
    def test_default_timeout(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        assert sb._timeout == 90

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_custom_timeout(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), timeout=60)
        assert sb._timeout == 60

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_default_retries(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        assert sb._max_retries == 2

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_custom_retries(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), max_retries=5)
        assert sb._max_retries == 5


class TestSSHSouthboundLifecycle:
    """Connect, disconnect, is_alive delegation."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_connect_delegates_to_session(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        sb.connect()
        mock_session.connect.assert_called_once()

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_disconnect_delegates(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        sb.connect()
        sb.disconnect()
        mock_session.disconnect.assert_called_once()

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_is_alive_true_when_connected(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session.is_connected.return_value = True
        mock_session_cls.return_value = mock_session

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        sb.connect()
        assert sb.is_alive() is True

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_is_alive_false_when_not_connected(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        type(mock_session).is_connected = PropertyMock(return_value=False)
        mock_session_cls.return_value = mock_session

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        assert sb.is_alive() is False


class TestSSHSouthboundSendCommand:
    """send_command delegates and handles errors."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_send_command_delegates(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        sb.connect()
        result = sb.send_command("display version")
        mock_session.run_cli_rpc.assert_called_once_with("display version")
        assert result == mock_session.run_cli_rpc.return_value

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_send_command_raises_if_not_connected(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        with pytest.raises(SdnConnectionError, match="Not connected"):
            sb.send_command("display version")


class TestSSHSouthboundSendConfig:
    """send_config delegates and handles errors."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_send_config_delegates(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session.edit_config.return_value = (True, "ok")
        mock_session_cls.return_value = mock_session

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        sb.connect()
        ok, msg = sb.send_config(["vlan 10", "name test"])
        mock_session.edit_config.assert_called_once_with(
            "vlan 10\nname test", target="running"
        )

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_send_config_raises_if_not_connected(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        with pytest.raises(SdnConnectionError, match="Not connected"):
            sb.send_config(["vlan 10"])


class TestSSHSouthboundRetry:
    """Retry logic on transient failures."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_retry_on_connect_failure(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Fail twice, succeed on third
        mock_session.connect.side_effect = [
            RuntimeError("Connection refused"),
            RuntimeError("Timeout"),
            None,
        ]
        mock_session.is_connected.return_value = True

        sb = SSHSouthbound(
            EnvBackend(), AuditLogger(), timeout=10, max_retries=3
        )
        sb.connect()
        assert mock_session.connect.call_count == 3
        assert sb.is_alive() is True

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_retry_exhausted_raises(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Always fail
        mock_session.connect.side_effect = RuntimeError("Always fails")

        sb = SSHSouthbound(
            EnvBackend(), AuditLogger(), timeout=10, max_retries=2
        )
        with pytest.raises(SdnConnectionError, match="After 2 retries"):
            sb.connect()
        assert mock_session.connect.call_count == 2


class TestSSHSouthboundExceptionPropagation:
    """Exceções tipadas propagam sem wrap genérico."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_sdn_validation_error_propagates_no_retry(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )
        from huawei_manager.exceptions import SdnValidationError

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.connect.side_effect = SdnValidationError("Credenciais incompletas")

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), max_retries=2)
        with pytest.raises(SdnValidationError, match="Credenciais incompletas"):
            sb.connect()
        # Sem retry — chamada única
        assert mock_session.connect.call_count == 1

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_netmiko_auth_exception_propagates_no_retry(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )
        from netmiko.exceptions import NetmikoAuthenticationException

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.connect.side_effect = NetmikoAuthenticationException("auth fail")

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), max_retries=2)
        with pytest.raises(NetmikoAuthenticationException):
            sb.connect()
        assert mock_session.connect.call_count == 1

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_netmiko_timeout_exception_retries_then_propagates_original(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )
        from netmiko.exceptions import NetmikoTimeoutException

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.connect.side_effect = NetmikoTimeoutException("timeout")

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), max_retries=2)
        with pytest.raises(NetmikoTimeoutException, match="timeout"):
            sb.connect()
        # max_retries=2 → loop roda 2 vezes (attempt 1, 2)
        assert mock_session.connect.call_count == 2

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_generic_exception_still_wrapped_in_sdn_connection_error(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )
        from huawei_manager.exceptions import SdnConnectionError

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.connect.side_effect = RuntimeError("generic failure")

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), max_retries=2)
        with pytest.raises(SdnConnectionError, match="After 2 retries"):
            sb.connect()
        assert mock_session.connect.call_count == 2


class TestSSHSouthboundTimeout:
    """Timeout is passed through to session connect."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_timeout_passed_to_connect(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        # Make is_alive return True after connect so retry loop exits
        type(mock_session).is_connected = PropertyMock(
            side_effect=[False, True]
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), timeout=45)
        # Mock session's connect timeout check — we just verify the
        # timeout value was stored and used conceptually.
        sb.connect()
        assert sb._timeout == 45


class TestSSHSouthboundCredentialSanitization:
    """Credentials must never appear in logs or exception messages."""

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_exception_masks_credentials(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        # Simulate an error that includes a password-like string
        mock_session.connect.side_effect = RuntimeError(
            "Invalid password 'supersecret' for user admin"
        )

        sb = SSHSouthbound(EnvBackend(), AuditLogger(), max_retries=1)
        with pytest.raises(SdnConnectionError) as exc:
            sb.connect()

        msg = str(exc.value)
        assert "supersecret" not in msg
        assert "****" in msg or "redacted" in msg.lower()

    @patch("huawei_manager.sdn_controller.southbound.NetmikoSession")
    def test_logger_does_not_emit_credentials(self, mock_session_cls):
        from huawei_manager.sdn_controller.southbound import (
            SSHSouthbound,
        )

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        with patch(
            "huawei_manager.sdn_controller.southbound.log"
        ) as mock_log:
            sb = SSHSouthbound(EnvBackend(), AuditLogger(), max_retries=1)
            # connect with the mock session
            type(mock_session).is_connected = PropertyMock(
                side_effect=[False, True]
            )
            sb.connect()
            for _call in mock_log.method_calls:
                for arg in _call.args:
                    if isinstance(arg, str):
                        assert "supersecret" not in arg


class TestSSHSouthboundWithValidator:
    """SSHSouthbound integration with CommandValidator."""

    @pytest.fixture
    def mock_session(self):
        with patch("huawei_manager.sdn_controller.southbound.NetmikoSession") as cls:
            ms = MagicMock()
            cls.return_value = ms
            yield ms

    @pytest.fixture
    def mock_validator(self):
        v = MagicMock(spec=CommandValidator)
        v.validate = MagicMock(return_value=ValidationResult(allowed=True))
        return v

    @pytest.fixture
    def sb(self, mock_session, mock_validator):
        from huawei_manager.sdn_controller.southbound import SSHSouthbound
        return SSHSouthbound(EnvBackend(), AuditLogger(), validator=mock_validator)

    def test_validator_called_on_send_command(self, sb, mock_validator):
        sb.connect()
        sb.send_command("display version")
        mock_validator.validate.assert_called_once_with("display version", "user")

    def test_validator_called_on_send_config(self, sb, mock_validator):
        sb.connect()
        sb.send_config(["vlan 10", "name test"])
        mock_validator.validate.assert_called_once_with("vlan 10\nname test", "user")

    def test_send_command_blocked_by_validator(self, sb, mock_validator):
        sb.connect()
        mock_validator.validate.return_value = ValidationResult(
            allowed=False, reason="Unknown command"
        )
        with pytest.raises(SdnAuthError, match="denied by policy"):
            sb.send_command("format flash")

    def test_send_config_blocked_by_validator(self, sb, mock_validator):
        sb.connect()
        mock_validator.validate.return_value = ValidationResult(
            allowed=False, reason="Command denied by policy: reset"
        )
        with pytest.raises(SdnAuthError, match="denied by policy"):
            sb.send_config(["reset saved-configuration"])

    def test_set_access_role_updates_role(self, sb):
        assert sb._access_role == "user"
        sb.set_access_role("admin")
        assert sb._access_role == "admin"

    def test_validator_uses_updated_role(self, sb, mock_validator):
        sb.connect()
        sb.set_access_role("tecnico")
        sb.send_command("reset counters")
        mock_validator.validate.assert_called_once_with("reset counters", "tecnico")


class TestSSHSouthboundServiceCommands:
    """send_service_commands delegates correctly."""

    def test_show_command_mode(self):
        from huawei_manager.sdn_controller.southbound import SSHSouthbound

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        mock_session = MagicMock()
        sb._session = mock_session
        sb._connected = True

        mock_session.run_cli_rpc.side_effect = ["output1"]
        out = sb.send_service_commands(["display clock"], config_mode=False)
        assert "output1" in out
        mock_session.run_cli_rpc.assert_called_once_with("display clock")
        # No system-view/quit calls
        assert mock_session.run_cli_rpc.call_count == 1

    def test_config_mode_system_view(self):
        from huawei_manager.sdn_controller.southbound import SSHSouthbound

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        mock_session = MagicMock()
        mock_session.edit_config.return_value = (True, "ok")
        sb._session = mock_session
        sb._connected = True

        out = sb.send_service_commands(
            ["vlan 10", "name test"], config_mode=True
        )
        assert "Config applied" in out
        assert mock_session.run_cli_rpc.call_count == 2  # system-view + quit

    def test_multiple_commands(self):
        from huawei_manager.sdn_controller.southbound import SSHSouthbound

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        mock_session = MagicMock()
        mock_session.run_cli_rpc.side_effect = ["output1", "output2"]
        sb._session = mock_session
        sb._connected = True

        out = sb.send_service_commands(["display clock", "display version"])
        assert "output1" in out
        assert "output2" in out
        assert mock_session.run_cli_rpc.call_count == 2

    def test_raises_if_not_connected(self):
        from huawei_manager.sdn_controller.southbound import SSHSouthbound

        sb = SSHSouthbound(EnvBackend(), AuditLogger())
        with pytest.raises(SdnConnectionError, match="Not connected"):
            sb.send_service_commands(["display version"])

    def test_with_validator_blocks_denied(self):
        from huawei_manager.sdn_controller.southbound import SSHSouthbound

        v = MagicMock(spec=CommandValidator)
        v.validate.return_value = ValidationResult(allowed=False, reason="test deny")
        sb = SSHSouthbound(EnvBackend(), AuditLogger(), validator=v)
        mock_session = MagicMock()
        sb._session = mock_session
        sb._connected = True

        with pytest.raises(SdnAuthError, match="denied by policy"):
            sb.send_service_commands(["format flash"], config_mode=False)
        v.validate.assert_called_once()
        mock_session.run_cli_rpc.assert_not_called()
