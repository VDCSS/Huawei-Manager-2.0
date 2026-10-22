"""Testes da aba Dashboard — HomeHandlers (tabs/home/handlers.py).

Migrados de tests/test_dashboard_mixin.py (F2-home do plano
plano-abas-independentes). O DashboardMixin legado foi removido junto
com handlers/dashboard.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.home.handlers import HomeHandlers
from huawei_manager.tabs.home.state import HomeState


def _make(**overrides) -> tuple[HomeHandlers, HomeState, TabContext]:
    """(handlers, state, ctx) — devices é getter; widgets são mocks."""
    devs = overrides.pop("devices", [])
    fields: dict = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *a: fn(*a),
        spawn_cpu=lambda fn, *a: fn(*a),
        watcher=MagicMock(),
        is_mock=lambda: False,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: None,
        set_watcher_results=MagicMock(),
        session=MagicMock(),
        run=MagicMock(),
        set_status=MagicMock(),
        touch_session=MagicMock(),
        cmd_validator=None,
        dry_run=None,
        get_last_config_command=MagicMock(return_value=None),
        set_last_config_command=MagicMock(),
        drv=lambda: MagicMock(),
        devices=lambda: devs,
        show_page=MagicMock(),
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    state = HomeState()
    state.conn_status = MagicMock()
    state.conn_host = MagicMock()
    state.device_online = MagicMock()
    state.device_offline = MagicMock()
    state.device_unknown = MagicMock()
    state.audit_text = MagicMock()
    return HomeHandlers(ctx, state), state, ctx


def _device(status: str = "online") -> MagicMock:
    d = MagicMock()
    d.status = status
    return d


class TestRefreshDashboard:
    def test_online_when_alive(self):
        h, st, ctx = _make()
        ctx.sb.is_alive.return_value = True
        h.refresh_dashboard()
        st.conn_status.setText.assert_called_with("Online")

    def test_offline_when_dead(self):
        h, st, ctx = _make()
        ctx.sb.is_alive.return_value = False
        h.refresh_dashboard()
        st.conn_status.setText.assert_called_with("Desconectado")

    def test_alive_exception_sets_offline(self):
        h, st, ctx = _make()
        ctx.sb.is_alive.side_effect = Exception("fail")
        h.refresh_dashboard()
        st.conn_status.setText.assert_called_with("Desconectado")

    def test_counts_online_devices(self):
        h, st, ctx = _make(
            devices=[_device("online"), _device("online"), _device("offline")])
        ctx.sb.is_alive.return_value = False
        h.refresh_dashboard()
        st.device_online.setText.assert_called_with("Online: 2")

    def test_counts_offline_devices(self):
        h, st, ctx = _make(devices=[_device("offline"), _device("unknown")])
        ctx.sb.is_alive.return_value = False
        h.refresh_dashboard()
        st.device_offline.setText.assert_called_with("Offline: 1")

    def test_counts_unknown_devices(self):
        h, st, ctx = _make(devices=[_device("unknown"), _device("")])
        ctx.sb.is_alive.return_value = False
        h.refresh_dashboard()
        st.device_unknown.setText.assert_called_with("Desconhecido: 2")

    def test_refreshes_audit_text(self):
        h, st, ctx = _make()
        ctx.sb.is_alive.return_value = False
        h.refresh_dashboard()
        st.audit_text.setPlainText.assert_called_once()

    def test_empty_devices_sets_all_zero(self):
        h, st, ctx = _make(devices=[])
        ctx.sb.is_alive.return_value = False
        h.refresh_dashboard()
        st.device_online.setText.assert_called_with("Online: 0")
        st.device_offline.setText.assert_called_with("Offline: 0")
        st.device_unknown.setText.assert_called_with("Desconhecido: 0")

    def test_handles_audit_error(self):
        h, st, ctx = _make()
        ctx.sb.is_alive.return_value = False
        with patch("huawei_manager._config.audit") as mock_audit:
            mock_audit.format_tail.side_effect = Exception("read fail")
            h.refresh_dashboard()
        st.audit_text.setPlainText.assert_called_once_with(
            "  (erro ao ler auditoria)"
        )
        st.audit_text.setReadOnly.assert_any_call(True)
