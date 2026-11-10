"""Testes da aba Topologia — TopologyTab (tabs/topology/page.py).

F2-topology do plano plano-abas-independentes: build verbatim do
``_build_topology_page`` legado (widgets no estado do módulo, callbacks
orquestradores via TabContext) + dispose zerando as refs.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.topology import TopologyTab
from huawei_manager.topology import TopologyCanvas


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _fake_ctx(**overrides) -> TabContext:
    """TabContext fake com todos os 34 campos; overrides por teste."""
    drv = overrides.pop("drv", MagicMock())
    fields: dict = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=MagicMock(),
        spawn_cpu=MagicMock(),
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
        drv=lambda: drv,
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "mock",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=None),
        refresh_devices=MagicMock(),
        show_device_dialog=MagicMock(),
        delete_device=MagicMock(),
        on_device_selected=MagicMock(),
        clear_device_target=MagicMock(),
    )
    fields.update(overrides)
    return TabContext(**fields)


class TestBuild:
    def test_build_returns_topology_page(self):
        tab = TopologyTab()
        page = tab.build(_fake_ctx())
        assert page.objectName() == "page_topology"
        assert isinstance(tab.state.topo_canvas, TopologyCanvas)
        assert tab.state.device_status_lbl is not None
        assert tab.state.device_status_lbl.text() == "Inventário: 0 devices"
        assert tab.state.device_info_lbl is not None
        assert tab.state.admin_btn is not None

    def test_admin_btn_label_for_admin(self):
        tab = TopologyTab()
        page = tab.build(_fake_ctx())  # role default "admin"; page mantém
        assert tab.state.admin_btn is not None       # a árvore Qt viva
        assert "Sair (Admin)" in tab.state.admin_btn.text()
        assert page is not None

    def test_admin_btn_label_for_user(self):
        tab = TopologyTab()
        page = tab.build(_fake_ctx(role=lambda: "user"))
        assert tab.state.admin_btn is not None
        assert "Acesso" in tab.state.admin_btn.text()
        assert page is not None

    def test_build_spawns_initial_refresh(self):
        ctx = _fake_ctx()
        TopologyTab().build(ctx)
        ctx.spawn_io.assert_called_once_with(ctx.refresh_devices)

    def test_attach_is_idempotent(self):
        tab = TopologyTab()
        ctx1, ctx2 = _fake_ctx(), _fake_ctx()
        tab.attach(ctx1)
        tab.attach(ctx2)
        assert tab._ctx is ctx1


class TestDispose:
    def test_dispose_zera_refs(self):
        tab = TopologyTab()
        tab.build(_fake_ctx())
        tab.dispose()
        assert tab.state.topo_canvas is None
        assert tab.state.device_info_lbl is None
        assert tab.state.device_status_lbl is None
        assert tab.state.admin_btn is None
        assert tab._ctx is None
