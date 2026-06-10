import os
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from huawei_manager.audit_log import AuditLogger
from huawei_manager.session import NetmikoSession
from huawei_manager.vault import EnvBackend


@pytest.fixture
def session():
    backend = EnvBackend()
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
