import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import PySide6  # noqa: F401
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False

if not HAS_PYSIDE6:
    collect_ignore = [
        "test_app.py", "test_app_threading.py", "test_auth_mixin.py",
        "test_concurrency_patterns.py",
        "test_device_dialog.py", "test_gui_helper.py",
        "test_rbac_matrix.py",
        "test_ssh_mixin.py", "test_tabs_registry.py", "test_topology.py",
        "test_topology_context_menu.py", "test_vnfs_mixin.py",
        "test_watcher.py", "test_widgets.py",
        "tabs/arp/test_handlers.py",
        "tabs/backup/test_handlers.py",
        "tabs/cmd/test_cmd_page.py", "tabs/cmd/test_editor_enter.py",
        "tabs/cmd/test_handlers.py",
        "tabs/config/test_handlers.py",
        "tabs/home/test_handlers.py",
        "tabs/home/test_page.py",
        "tabs/info/test_handlers.py",
        "tabs/route/test_handlers.py",
        "tabs/services/test_handlers.py",
        "tabs/services/test_napalm.py",
        "tabs/services/test_page.py",
        "tabs/topology/test_page.py",
        "tabs/manutencao/test_handlers.py", "tabs/manutencao/test_page.py",
    ]
else:
    collect_ignore = []


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path):
    """Mantém QSettings fora do registro/config real do usuário nos testes.

    Sem isso, um teste que constrói ``HuaweiRouterApp`` lê o tema persistido
    da máquina e chama ``constants.set_theme()``, contaminando testes
    seguintes que assumem a paleta dark (ex.: NEON_RED == "#ff4d4d"). O
    diretório é novo a cada teste para que escritas de um teste (ex.:
    ``_toggle_theme``) não vazem para o próximo.
    """
    if not HAS_PYSIDE6:
        yield
        return
    from PySide6.QtCore import QSettings

    # A aplicação usa QSettings com formato INI explícito (ver
    # huawei_manager.app._preferences), então basta redirecionar o diretório.
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path / "qsettings"),
    )
    yield


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
