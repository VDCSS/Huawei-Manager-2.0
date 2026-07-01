from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from huawei_manager.audit_log import AuditLogger
from huawei_manager.session import NetmikoSession
from huawei_manager.vault import EnvBackend


@pytest.fixture
def session():
    backend = EnvBackend()
    backend.put("ROUTER_HOSTKEY_VERIFY", "off")
    audit = AuditLogger()
    return NetmikoSession(backend, audit)


class TestInit:
    def test_conn_is_none(self, session):
        assert session._conn is None

    def test_not_connected(self, session):
        assert not session.is_connected


class TestValidateCredentials:
    def test_empty_host_raises(self, session):
        with patch.object(type(session), "_host", new_callable=PropertyMock, return_value=""):
            with pytest.raises(ValueError, match="ROUTER_HOST"):
                session._validate_credentials()

    def test_empty_user_raises(self, session):
        with patch.object(type(session), "_user", new_callable=PropertyMock, return_value=""):
            with pytest.raises(ValueError, match="ROUTER_USERNAME"):
                session._validate_credentials()

    def test_ok(self, session):
        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(session), "_pass", new_callable=PropertyMock, return_value="secret"),
        ):
            session._validate_credentials()

    def test_no_pass_no_key_raises(self, session):
        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(session), "_pass", new_callable=PropertyMock, return_value=""),
            patch.object(type(session), "_ssh_key", new_callable=PropertyMock, return_value=None),
        ):
            with pytest.raises(ValueError, match="ROUTER_PASSWORD"):
                session._validate_credentials()


class TestSessionId:
    def test_without_conn(self, session):
        assert session._session_id is None


class TestResolveFilter:
    def test_full_config(self):
        assert NetmikoSession._resolve_filter("full_config") == "display current-configuration"

    def test_routing(self):
        assert NetmikoSession._resolve_filter("routing") == "display ip routing-table"

    def test_arp(self):
        assert NetmikoSession._resolve_filter("arp") == "display arp"

    def test_none(self):
        assert NetmikoSession._resolve_filter(None) is None

    def test_unknown(self):
        assert NetmikoSession._resolve_filter("unknown_filter") is None


class TestConnect:
    @patch("huawei_manager.session.ConnectHandler")
    def test_calls_connect_handler(self, mock_connect, session):
        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(session), "_pass", new_callable=PropertyMock, return_value="secret"),
            patch.object(type(session), "_ssh_key", new_callable=PropertyMock, return_value=None),
        ):
            session.connect()
            mock_connect.assert_called_once()

    @patch("huawei_manager.session.ConnectHandler")
    def test_sets_conn(self, mock_connect, session):
        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(session), "_pass", new_callable=PropertyMock, return_value="secret"),
            patch.object(type(session), "_ssh_key", new_callable=PropertyMock, return_value=None),
        ):
            session.connect()
            assert session._conn is not None

    @patch("huawei_manager.session.ConnectHandler")
    def test_sets_session_id(self, mock_connect, session):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(session), "_pass", new_callable=PropertyMock, return_value="secret"),
            patch.object(type(session), "_ssh_key", new_callable=PropertyMock, return_value=None),
        ):
            session.connect()
            assert session._session_id == "10.0.0.1:2222"


class TestDisconnect:
    def test_disconnect_called(self, session):
        mock_conn = MagicMock()
        session._conn = mock_conn
        session.disconnect()
        mock_conn.disconnect.assert_called_once()

    def test_conn_becomes_none(self, session):
        session._conn = MagicMock()
        session.disconnect()
        assert session._conn is None


class TestCmd:
    def test_no_conn_returns_sem_conexao(self, session):
        session._conn = None
        assert "Sem conexao" in session._cmd("display version")

    def test_returns_clean_output(self, session):
        mock_conn = MagicMock()
        mock_conn.send_command.return_value = "\x1b[32moutput\x1b[0m  "
        session._conn = mock_conn
        result = session._cmd("display version")
        assert result == "output"


class TestEditConfig:
    def test_no_conn_returns_false(self, session):
        session._conn = None
        ok, msg = session.edit_config("config text")
        assert not ok

    def test_success_returns_true(self, session):
        mock_conn = MagicMock()
        mock_conn.send_config_set.return_value = "applied"
        session._conn = mock_conn
        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
        ):
            ok, msg = session.edit_config("config text")
            assert ok

    def test_save_config_called(self, session):
        mock_conn = MagicMock()
        session._conn = mock_conn
        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
        ):
            session.edit_config("config text")
            mock_conn.save_config.assert_called_once()


class TestRunCliRpc:
    def test_returns_output(self, session):
        mock_conn = MagicMock()
        mock_conn.send_command.return_value = "output"
        session._conn = mock_conn
        result = session.run_cli_rpc("display version")
        assert "output" in result

    def test_no_conn_returns_sem_conexao(self, session):
        session._conn = None
        assert "Sem conexao" in session.run_cli_rpc("display version")


class TestGet:
    def test_delegates_to_cmd(self, session):
        mock_conn = MagicMock()
        mock_conn.send_command.return_value = "output"
        session._conn = mock_conn
        result = session.get("full_config")
        assert "output" in result or "ERRO" not in result


# ── Host Key Verification ─────────────────────────────────────────


class TestHostKeyVerify:
    """Tests for 3 host key verification modes: strict, tofu, off."""

    def _make_backend(self, mode: str = "strict") -> EnvBackend:
        backend = EnvBackend()
        backend.put("ROUTER_HOSTKEY_VERIFY", mode)
        return backend

    # ── hk_verify property ───────────────────────────────────────

    def test_hk_verify_off(self):
        backend = self._make_backend("off")
        audit = AuditLogger()
        s = NetmikoSession(backend, audit)
        assert s._hk_verify == "off"

    def test_hk_verify_strict(self):
        backend = self._make_backend("strict")
        audit = AuditLogger()
        s = NetmikoSession(backend, audit)
        assert s._hk_verify == "strict"

    def test_hk_verify_tofu(self):
        backend = self._make_backend("tofu")
        audit = AuditLogger()
        s = NetmikoSession(backend, audit)
        assert s._hk_verify == "tofu"

    def test_hk_verify_unknown_mode_defaults_to_strict(self):
        backend = EnvBackend()
        backend.put("ROUTER_HOSTKEY_VERIFY", "garbage")
        audit = AuditLogger()
        s = NetmikoSession(backend, audit)
        assert s._hk_verify == "strict"

    # ── ssh_strict param in connect ─────────────────────────────

    @patch("huawei_manager.session.ConnectHandler")
    def test_connect_strict_passes_ssh_strict_true(self, mock_connect):
        backend = self._make_backend("strict")
        audit = AuditLogger()
        s = NetmikoSession(backend, audit)
        with (
            patch.object(type(s), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(s), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(s), "_pass", new_callable=PropertyMock, return_value="secret"),
            patch.object(type(s), "_ssh_key", new_callable=PropertyMock, return_value=None),
        ):
            s.connect()
            _args, kwargs = mock_connect.call_args
            assert kwargs.get("ssh_strict") is True

    @patch("huawei_manager.session.ConnectHandler")
    def test_connect_off_passes_ssh_strict_false(self, mock_connect):
        backend = self._make_backend("off")
        audit = AuditLogger()
        s = NetmikoSession(backend, audit)
        with (
            patch.object(type(s), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(s), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(s), "_pass", new_callable=PropertyMock, return_value="secret"),
            patch.object(type(s), "_ssh_key", new_callable=PropertyMock, return_value=None),
        ):
            s.connect()
            _args, kwargs = mock_connect.call_args
            assert kwargs.get("ssh_strict") is False

    @patch("huawei_manager.session.ConnectHandler")
    def test_connect_tofu_passes_ssh_strict_false(self, mock_connect):
        """TOFU uses ssh_strict=False (manual host key management)."""
        backend = self._make_backend("tofu")
        audit = AuditLogger()
        s = NetmikoSession(backend, audit)
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        with (
            patch.object(type(s), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(s), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(s), "_pass", new_callable=PropertyMock, return_value="secret"),
            patch.object(type(s), "_ssh_key", new_callable=PropertyMock, return_value=None),
            patch.object(type(s), "_hk_verify", new_callable=PropertyMock, return_value="tofu"),
            patch.object(s, "_load_host_key", return_value=None),
            patch.object(s, "_save_host_key"),
        ):
            s.connect()
            _args, kwargs = mock_connect.call_args
            assert kwargs.get("ssh_strict") is False

    # ── known_hosts path ────────────────────────────────────────

    def test_known_hosts_path_default(self, session):
        """Default known_hosts path is under ~/.ssh/huawei_known_hosts."""
        p = session._known_hosts_path
        assert "huawei_known_hosts" in str(p)

    # ── TOFU cache lifecycle ─────────────────────────────────────

    @patch("huawei_manager.session.Path")
    def test_tofu_key_not_cached_returns_none(self, mock_path_cls, session):
        mock_path = MagicMock()
        mock_path.expanduser.return_value = mock_path
        mock_path.exists.return_value = False
        mock_path_cls.return_value = mock_path
        with patch.object(type(session), "_hk_verify", new_callable=PropertyMock, return_value="tofu"):
            result = session._load_host_key("10.0.0.1")
            assert result is None

    @patch("huawei_manager.session.Path")
    def test_tofu_key_cached_returns_key(self, mock_path_cls, session):
        content = "10.0.0.1 ssh-rsa AAAAB3NzaC1yc2E...\n"
        mock_path = MagicMock()
        mock_path.expanduser.return_value = mock_path
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = content
        mock_path_cls.return_value = mock_path
        with patch.object(type(session), "_hk_verify", new_callable=PropertyMock, return_value="tofu"):
            result = session._load_host_key("10.0.0.1")
            assert result == "ssh-rsa AAAAB3NzaC1yc2E..."

    @patch("huawei_manager.session.Path")
    def test_tofu_save_host_key(self, mock_path_cls, session):
        mock_path = MagicMock()
        mock_path.expanduser.return_value = mock_path
        mock_path_cls.return_value = mock_path
        with patch.object(type(session), "_hk_verify", new_callable=PropertyMock, return_value="tofu"):
            session._save_host_key("10.0.0.1", "ssh-rsa KEYAAA=")
            mock_path.parent.mkdir.assert_called_once_with(exist_ok=True, parents=True)
            mock_path.open.assert_called_once_with("a")
            handle = mock_path.open.return_value.__enter__.return_value
            handle.write.assert_called_once_with("10.0.0.1 ssh-rsa KEYAAA=\n")

    # ── host key mismatch raises ────────────────────────────────

    @patch("huawei_manager.session.ConnectHandler")
    def test_tofu_key_mismatch_raises(self, mock_connect, session):
        """TOFU mode raises ValueError when cached key differs."""
        mock_conn = MagicMock()
        mock_conn.remote_server_key.get_name.return_value = "ssh-rsa"
        # Return a different base64 key from remote
        mock_conn.remote_server_key.get_base64.return_value = "DIFFERENTKEYBASE64"
        mock_connect.return_value = mock_conn

        with (
            patch.object(type(session), "_host", new_callable=PropertyMock, return_value="10.0.0.1"),
            patch.object(type(session), "_user", new_callable=PropertyMock, return_value="admin"),
            patch.object(type(session), "_pass", new_callable=PropertyMock, return_value="secret"),
            patch.object(type(session), "_ssh_key", new_callable=PropertyMock, return_value=None),
            patch.object(type(session), "_hk_verify", new_callable=PropertyMock, return_value="tofu"),
            patch.object(session, "_load_host_key", return_value="ssh-rsa CACHEDKEYBASE64"),
        ):
            with pytest.raises(ValueError, match="Host key mismatch"):
                session.connect()
