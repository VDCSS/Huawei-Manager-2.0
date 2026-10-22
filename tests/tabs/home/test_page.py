"""Testes da página do Dashboard — HomeTab (tabs/home/page.py).

Cobrem build/dispose/refresh (F2-home do plano plano-abas-independentes);
os stretch/altura do audit_text ficaram em tests/test_pages_resize.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.home import HomeTab


def _fake_ctx(**overrides) -> TabContext:
    """TabContext fake completo (26 campos); overrides por teste."""
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
        devices=lambda: [],
        show_page=MagicMock(),
    )
    fields.update(overrides)
    return TabContext(**fields)


class TestHomePage:
    def test_build_populates_state(self):
        tab = HomeTab()
        page = tab.build(_fake_ctx())  # ref local: QWidget sem pai
        assert page is not None
        assert page.objectName() == "page_home"
        assert tab.state.conn_status is not None
        assert tab.state.conn_host is not None
        assert tab.state.audit_text is not None
        assert set(tab.state.shortcut_btns) == {
            "config", "route", "backup", "cmd"}

    def test_dispose_clears_widget_refs(self):
        tab = HomeTab()
        page = tab.build(_fake_ctx())
        tab.dispose()
        assert tab.state.conn_status is None
        assert tab.state.conn_host is None
        assert tab.state.device_online is None
        assert tab.state.device_offline is None
        assert tab.state.device_unknown is None
        assert tab.state.audit_text is None
        assert tab.state.shortcut_btns == {}
        assert page is not None

    def test_refresh_without_attach_is_noop(self):
        HomeTab().refresh()  # sem contexto: return silencioso, sem exceção
