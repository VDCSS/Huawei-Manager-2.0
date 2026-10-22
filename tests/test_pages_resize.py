"""Testes de caracterização — painéis laterais flexíveis (A2).

Verifica que as páginas Command Editor e Serviços não clipam o painel
direito quando a janela é reduzida até 800px (mínimo da app), e que os
painéis laterais usam min/max width em vez de largura fixa.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QListWidget,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from huawei_manager.pages.builder import PageBuilder
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.manutencao.page import ManutencaoTab
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


def _fake_ctx():
    """TabContext fake completo (23 campos) p/ construir abas nos testes."""
    from huawei_manager.tabs._contract import TabContext

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
    )


def _build_cmd_page(builder: PageBuilder):
    """Constrói a aba Editor de Comandos via módulo (F2-cmd) no container."""
    from huawei_manager.tabs.cmd import CmdTab

    page = CmdTab().build(_fake_ctx())
    builder._page_container.addWidget(page)
    return page


class TestCmdPageResize:
    def test_buttons_visible_at_800px(self):
        builder = _make_builder()
        page = _build_cmd_page(builder)
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
        page = _build_cmd_page(builder)
        _show_page(builder)

        tpl_list = page.findChild(QListWidget)
        assert tpl_list is not None, "QListWidget not found in cmd page"
        left = tpl_list.parentWidget()
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
        _show_page(builder)

        left = builder._svc_listbox.parentWidget()
        assert left.minimumWidth() == 240
        assert left.maximumWidth() == 340


class TestManutencaoPageGrid:
    def _build_manut(self) -> QWidget:
        """Aba real (módulo TabModule) — ctx fake, sem App."""
        ctx = TabContext(
            sb=MagicMock(),
            audit=None,
            event_bus=MagicMock(),
            role=lambda: "tecnico",
            device=lambda: None,
            dispatch=lambda fn: fn() if callable(fn) else None,
            require_access=lambda level: True,
            spawn_io=lambda fn, *args: fn(*args),
            spawn_cpu=lambda fn, *args: fn(*args),
            watcher=MagicMock(is_active=False),
            is_mock=lambda: True,
            toggle_mock=lambda: False,
            show_auth_dialog=lambda: None,
            watcher_results=lambda: [],
            set_watcher_results=MagicMock(),
            session=MagicMock(),
            run=MagicMock(),
            set_status=MagicMock(),
            touch_session=MagicMock(),
            cmd_validator=None,
            dry_run=None,
            get_last_config_command=lambda: None,
            set_last_config_command=MagicMock(),
        )
        return ManutencaoTab().build(ctx)

    def _show(self, page: QWidget) -> None:
        # Paridade com o efeito final do _show_page legado: 800×600.
        page.resize(800, 600)
        page.show()
        QApplication.processEvents()

    def test_install_reset_buttons_visible_at_1220px(self):
        page = self._build_manut()
        self._show(page)

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
        page = self._build_manut()
        self._show(page)

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


class TestBackupEntryResize:
    def test_entry_width_and_expanding_policy(self):
        from huawei_manager.tabs.backup import BackupTab

        builder = _make_builder()
        tab = BackupTab()
        page = tab.build(_fake_ctx())
        builder._page_container.addWidget(page)
        _show_page(builder)

        entry = tab.state.backup_entry
        assert entry.minimumWidth() == 24 * 8
        assert entry.maximumWidth() == 24 * 14
        policy = entry.sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert policy.verticalPolicy() == QSizePolicy.Policy.Fixed
        assert entry.isVisible()
        assert entry.geometry().right() <= page.width() + 1


class TestDashboardStretch:
    def _make_dash_builder(self) -> PageBuilder:
        builder = _make_builder()
        builder._spawn_io = MagicMock()
        builder._refresh_devices = MagicMock()
        builder._show_page = MagicMock()
        return builder

    def _find_card(self, page: QWidget, title: str) -> QFrame:
        for card in page.findChildren(QFrame):
            labels = [lbl.text() for lbl in card.findChildren(QLabel)]
            if any(title in t for t in labels):
                return card
        raise AssertionError(f"card {title!r} not found")

    def test_row1_stretch_3_card4_stretch_2(self):
        builder = self._make_dash_builder()
        builder._build_home_page()
        page = builder._page_container.widget(0)
        _show_page(builder)

        layout = page.layout()
        assert layout is not None

        row1 = self._find_card(page, "CONEXAO").parentWidget()
        card4 = self._find_card(page, "ATALHOS RAPIDOS")
        assert layout.stretch(layout.indexOf(row1)) == 3
        assert layout.stretch(layout.indexOf(card4)) == 2

    def test_audit_text_min_height_60(self):
        builder = self._make_dash_builder()
        builder._build_home_page()
        _show_page(builder)

        assert builder._dash_audit_text.minimumHeight() == 60
        assert builder._dash_audit_text.geometry().height() > 0
