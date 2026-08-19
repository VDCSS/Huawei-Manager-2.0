"""Testes de caracterização — painéis laterais flexíveis (A2).

Verifica que as páginas Command Editor e Serviços não clipam o painel
direito quando a janela é reduzida até 800px (mínimo da app), e que os
painéis laterais usam min/max width em vez de largura fixa.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QScrollArea, QStackedWidget

from huawei_manager.pages.builder import PageBuilder
from huawei_manager.widgets.neon_button import ActionButton


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
    builder._get_editor_cmd = MagicMock(return_value="display version")
    builder._exec_cmd = MagicMock()
    builder._exec_config = MagicMock()
    return builder


def _show_page(builder: PageBuilder, index: int = 0) -> None:
    builder._page_container.resize(800, 600)
    builder._page_container.setCurrentIndex(index)
    builder._page_container.show()
    QApplication.processEvents()


class TestCmdPageResize:
    def test_buttons_visible_at_800px(self):
        builder = _make_builder()
        builder._build_cmd_page()
        page = builder._page_container.widget(0)
        _show_page(builder)

        buttons = [
            b for b in page.findChildren(ActionButton)
            if b.text().strip() in ("▶ Executar", "⚙ Enviar Config")
        ]
        assert len(buttons) == 2
        for btn in buttons:
            assert btn.isVisible()
            assert btn.geometry().right() <= page.width()
            assert btn.geometry().width() > 0

    def test_left_panel_flexible_bounds(self):
        builder = _make_builder()
        builder._build_cmd_page()
        page = builder._page_container.widget(0)
        _show_page(builder)

        scroll = page.findChild(QScrollArea)
        left = scroll.parentWidget()
        assert left.minimumWidth() == 200
        assert left.maximumWidth() == 320


class TestServicesPageResize:
    def test_detail_panel_visible_at_800px(self):
        builder = _make_builder()
        builder._build_services_page()
        page = builder._page_container.widget(0)
        _show_page(builder)

        detail = builder._svc_detail_frame
        assert detail.isVisible()
        assert detail.geometry().right() <= page.width()
        assert detail.geometry().width() > 0

    def test_left_panel_flexible_bounds(self):
        builder = _make_builder()
        builder._build_services_page()
        page = builder._page_container.widget(0)
        _show_page(builder)

        left = builder._svc_listbox.parentWidget()
        assert left.minimumWidth() == 240
        assert left.maximumWidth() == 340


class TestManutencaoPageGrid:
    def _make_manut_builder(self) -> PageBuilder:
        builder = _make_builder()
        builder._access_level = "tecnico"
        builder._mock_mode = True
        builder._watcher_results = []
        builder._watcher = MagicMock()
        builder._watcher.is_active = False
        builder._loading = MagicMock()
        builder._display_watcher_results = MagicMock()
        builder._run_dev_cmd = MagicMock()
        builder._run_agents = MagicMock()
        builder._toggle_watcher = MagicMock()
        builder._toggle_probe_mode = MagicMock()
        builder._run_setup = MagicMock()
        builder._cancel_and_clear = MagicMock()
        return builder

    def test_install_reset_buttons_visible_at_1220px(self):
        builder = self._make_manut_builder()
        builder._build_manutencao_page()
        page = builder._page_container.widget(0)
        builder._page_container.resize(1220, 700)
        _show_page(builder)

        buttons = [
            b for b in page.findChildren(ActionButton)
            if b.text().strip() in ("⚙  Install", "🔄  Reset")
        ]
        assert len(buttons) == 2
        for btn in buttons:
            assert btn.isVisible()
            assert btn.geometry().right() <= page.width()
            assert btn.geometry().width() > 0

    def test_no_button_exceeds_page_viewport(self):
        builder = self._make_manut_builder()
        builder._build_manutencao_page()
        page = builder._page_container.widget(0)
        builder._page_container.resize(1220, 700)
        _show_page(builder)

        for btn in page.findChildren(ActionButton):
            assert btn.isVisible()
            assert btn.geometry().right() <= page.width() + 1
            assert btn.geometry().bottom() <= page.height() + 1


class TestTopologyBarResize:
    def _make_topo_builder(self) -> PageBuilder:
        builder = _make_builder()
        builder._access_level = "tecnico"
        builder._show_auth_dialog = MagicMock()
        builder._show_device_dialog = MagicMock()
        builder._spawn_io = MagicMock()
        builder._refresh_devices = MagicMock()
        builder._clear_device_target = MagicMock()
        builder._on_device_selected = MagicMock()
        builder._delete_device = MagicMock()
        return builder

    def test_control_buttons_visible_at_800px(self):
        builder = self._make_topo_builder()
        builder._build_topology_page()
        page = builder._page_container.widget(0)
        builder._page_container.resize(800, 600)
        _show_page(builder)

        labels = ("Tecnico", "Cadastrar Dispositivo", "Atualizar", "Voltar")
        buttons = [
            b for b in page.findChildren(ActionButton)
            if any(lbl in b.text() for lbl in labels)
        ]
        assert len(buttons) == 4
        for btn in buttons:
            assert btn.isVisible()
            assert btn.geometry().right() <= page.width() + 1
            assert btn.geometry().width() > 0

    def test_device_info_label_min_width_and_not_collapsed(self):
        builder = self._make_topo_builder()
        builder._build_topology_page()
        page = builder._page_container.widget(0)
        builder._page_container.resize(800, 600)
        _show_page(builder)

        assert builder._device_info_lbl.minimumWidth() == 220
        assert builder._device_info_lbl.isVisible()
        assert builder._device_info_lbl.geometry().width() > 0
        assert builder._device_info_lbl.geometry().right() <= page.width() + 1