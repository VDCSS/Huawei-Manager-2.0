import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Ambientes sandbox/CI onde $HOME pode não ser gravável:
_home = os.environ.get("HOME")
if not _home or not os.access(_home, os.W_OK):
    _tmp_home = os.path.join(os.sep, "tmp", "huawei_manager_test_home")
    os.makedirs(_tmp_home, exist_ok=True)
    os.environ["HOME"] = _tmp_home


# ── Camada 1 de defesa: nenhum teste toca o DB real ~/.huawei_manager/ ──
# Define HW_DATA_DIR / HUAWEI_MANAGER_DIR para um tmp_path de sessão, de modo
# que get_database_path() (sem argumentos) sempre resolva para o sandbox de
# teste e NUNCA para o banco real do usuário durante pytest.
@pytest.fixture(scope="session", autouse=True)
def _sandbox_db_dir(tmp_path_factory):
    """Redireciona HW_DATA_DIR/HUAWEI_MANAGER_DIR para tmp_path durante pytest.

    Isso impede que qualquer código (ex.: DeviceService.save_inventory via
    _refresh_devices) escreva ou apague registros do banco real
    ~/.huawei_manager/inventory.db enquanto os testes rodam.
    """
    sandbox = tmp_path_factory.mktemp("huawei_manager_db")
    os.environ["HW_DATA_DIR"] = str(sandbox)
    os.environ["HUAWEI_MANAGER_DIR"] = str(sandbox)
    yield
    # Mantém o diretório após os testes para permitir inspeção de falhas.

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
