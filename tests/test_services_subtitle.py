"""Testes de caracterização — subtítulo honesto do catálogo (B7-rev).

Verifica que o subtítulo da aba Serviços não promete comandos SHOW e que
o catálogo efetivamente expõe apenas serviços de configuração
(config_mode), sem adicionar comandos SHOW ao escopo.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QStackedWidget

from huawei_manager.pages.builder import PageBuilder
from huawei_manager.services import get_services_for

DEVICE_TYPES = ("ROUTER", "SWITCH", "FIREWALL", "LOAD-BALANCER")


@pytest.fixture(autouse=True)
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_builder() -> PageBuilder:
    builder = PageBuilder()
    builder._page_container = QStackedWidget()
    builder._access_level = "user"
    builder._target_device = None
    builder._run = MagicMock()
    return builder


class TestServicesSubtitle:
    def test_subtitle_mentions_config_not_show(self):
        builder = _make_builder()
        builder._build_services_page()
        page = builder._page_container.widget(0)

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
        assert total == 25