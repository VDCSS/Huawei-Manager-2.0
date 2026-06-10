from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_session():
    sess = MagicMock()
    sess.is_connected = True
    sess._host = "10.0.0.1"
    sess._port = 22
    sess._user = "admin"
    sess._session_id = "sess-001"
    sess.run_cli_rpc.return_value = "display version\nVRP (R) Software"
    sess.get_config.return_value = "display current-configuration\nsysname R1"
    sess._cmd.return_value = "display interface brief\nGigabitEthernet0/0/0 up"
    sess.edit_config.return_value = (True, "OK Config applied")
    return sess


@pytest.fixture
def tmp_audit_path(tmp_path):
    return tmp_path / "test_audit.jsonl"


@pytest.fixture
def audit_logger(tmp_audit_path):
    from huawei_manager.audit_log import AuditLogger
    return AuditLogger(str(tmp_audit_path))


@pytest.fixture
def mock_netmiko_connection():
    conn = MagicMock()
    conn.send_command.return_value = "command output\nline2"
    conn.send_command_timing.return_value = "timing output"
    conn.send_config_set.return_value = "config output"
    conn.is_alive.return_value = True
    return conn
