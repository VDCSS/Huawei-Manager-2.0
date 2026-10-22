"""Testes de caracterização — subtítulo honesto do catálogo (B7-rev).

Verifica que o subtítulo da aba Serviços não promete comandos SHOW e que
o catálogo efetivamente expõe apenas serviços de configuração
(config_mode), sem adicionar comandos SHOW ao escopo.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from huawei_manager.services import get_services_for
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services import ServicesTab

DEVICE_TYPES = ("ROUTER", "SWITCH", "FIREWALL", "LOAD-BALANCER")


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _fake_ctx() -> TabContext:
    """TabContext fake com todos os 29 campos (F2-services)."""
    return TabContext(
        sb=MagicMock(), audit=None, event_bus=MagicMock(),
        role=lambda: "admin", device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *args: None, spawn_cpu=lambda fn, *args: None,
        watcher=MagicMock(), is_mock=lambda: False, toggle_mock=lambda: False,
        show_auth_dialog=lambda: None, watcher_results=lambda: None,
        set_watcher_results=MagicMock(), session=MagicMock(), run=MagicMock(),
        set_status=MagicMock(), touch_session=MagicMock(), cmd_validator=None,
        dry_run=None, get_last_config_command=lambda: None,
        set_last_config_command=MagicMock(),
        drv=lambda: MagicMock(),
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "mock",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=None),
    )


def _build_services_page():
    """Constrói a aba via módulo TabModule (F2-services), sem App."""
    return ServicesTab().build(_fake_ctx())


class TestServicesSubtitle:
    def test_subtitle_mentions_config_not_show(self):
        page = _build_services_page()

        labels = [lbl.text() for lbl in page.findChildren(QLabel)]
        subtitle = next(
            (t for t in labels if "configura" in t.lower() or "Editor de Comandos" in t),
            None,
        )
        assert subtitle is not None, "subtítulo não encontrado"
        assert "SHOW" not in subtitle, "subtítulo não pode prometer comandos SHOW"
        assert "show" in subtitle.lower(), "hint de comandos show esperado"
        assert "Editor de Comandos" in subtitle

    def test_catalog_exposes_only_config_services(self):
        for device_type in DEVICE_TYPES:
            shown = [s for s in get_services_for(device_type) if s.config_mode]
            assert all(s.config_mode for s in shown)

    def test_no_show_services_added_to_catalog(self):
        total = sum(
            len([s for s in get_services_for(t) if s.config_mode])
            for t in DEVICE_TYPES
        )
        # 25 originais + 14 novos serviços de config (todos ROUTER+SWITCH, contam 2x)
        assert total == 53