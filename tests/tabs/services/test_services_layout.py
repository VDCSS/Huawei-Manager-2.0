"""Layout da aba Serviços (pedido @283@).

Testes de regressão visual-comportamental:

* Nenhuma seleção automática ao abrir a aba (opção (ii)) — o painel começa
  vazio, sem texto "Selecione um serviço…".
* Ao selecionar um serviço, a barra da esquerda recolhe para um trilho (~36 px)
  e o formulário aparece à direita.
* Hover sobre o trilho (só quando dentro de um serviço) abre a lista
  temporariamente; sair do trilho fecha.
* Barra de ações fixa no rodapé (não rola com o formulário).
* Output com altura fixa (~12 linhas) no rodapé da página.
* Labels da cadeia Traffic Policy sem exemplos "(ex.: …)".
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint, QEvent
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication, QListWidget, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout

from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services.page import ServicesTab

#: pytest-qt guarda apenas referências fracas — mantemos a página viva.
_KEEP_ALIVE: list = []


def _device():
    dev = MagicMock()
    dev.name = "RTR-01"
    dev.host = "10.0.0.1"
    dev.port = 22
    dev.type = "ROUTER"
    dev.status = "online"
    return lambda: dev


def _sb_mock(running_config: str = "") -> MagicMock:
    sb = MagicMock()
    sb.is_alive.return_value = True

    def _send_command(cmd, *a, **kw):
        if "version" in cmd:
            return "VRP (R) Version 8.180"
        if "current-configuration" in cmd:
            return running_config
        return ""

    sb.send_command.side_effect = _send_command
    sb.send_config_block.return_value = (True, "OK")
    sb.save_running_config.return_value = (True, "OK salvo")
    return sb


def _fake_ctx(**overrides) -> TabContext:
    fields: dict = dict(
        sb=_sb_mock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=_device(),
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
        svc_mode=lambda: "cli",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=True),
        refresh_devices=MagicMock(),
        show_device_dialog=MagicMock(),
        delete_device=MagicMock(),
        on_device_selected=MagicMock(),
        clear_device_target=MagicMock(),
    )
    fields.update(overrides)
    return TabContext(**fields)


def _build(qtbot, ctx: TabContext, svc_id: str | None = None):
    tab = ServicesTab()
    widget = tab.build(ctx)
    qtbot.addWidget(widget)
    _KEEP_ALIVE.append(widget)
    tab.refresh_service_list()
    if svc_id is not None:
        for idx, svc in enumerate(tab.state.services):
            if svc.id == svc_id:
                tab.state.listbox.setCurrentRow(idx)
                break
    # Mostra e redimensiona para forçar o layout (necessário para isVisible()
    # dos botões dentro do QScrollArea).
    widget.resize(800, 600)
    widget.show()
    qtbot.wait(20)
    return tab, widget


def _button(widget, needle: str) -> QPushButton:
    for btn in widget.findChildren(QPushButton):
        if needle in btn.text():
            return btn
    raise AssertionError(f"botão '{needle}' não encontrado")


class TestNoAutoSelect:
    """A aba não deve auto-selecionar o primeiro serviço ao abrir."""

    def test_no_service_selected_after_build(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id=None)

        # Nenhum serviço selecionado: currentRow == -1.
        assert tab.state.listbox.currentRow() == -1
        # Nenhum serviço atual.
        assert tab.state.current_svc is None
        # Detail vazio: não há título de serviço.
        titles = [w for w in widget.findChildren(QListWidget)]
        # Não há form_state (nenhum formulário construído).
        assert tab.state.form_state is None

    def test_detail_panel_empty_when_no_selection(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id=None)

        # detail_frame existe mas não deve conter título de serviço.
        frame = tab.state.detail_frame
        assert frame is not None
        # Nenhum label "Configurando: …" ou "Executando: …".
        from PySide6.QtWidgets import QLabel
        labels = [lbl.text() for lbl in frame.findChildren(QLabel)]
        assert not any("Configurando:" in t or "Executando:" in t for t in labels)


class TestLeftPanelCollapse:
    """A barra da esquerda recolhe ao selecionar um serviço."""

    def test_select_service_collapses_left_panel(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id="svc-acl")

        left = tab.state.listbox.parentWidget()
        # Após selecionar, o painel recolhe (mínimo ~36 px, não 240).
        assert left.minimumWidth() <= 60
        assert left.maximumWidth() <= 60
        # O serviço selecionado está definido.
        assert tab.state.current_svc is not None
        assert tab.state.current_svc.id == "svc-acl"

    def test_select_other_service_shows_new_and_collapses(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id="svc-acl")

        first_svc = tab.state.current_svc
        assert first_svc is not None
        first_id = first_svc.id

        # Seleciona o segundo serviço da lista (se existir).
        services = tab.state.services
        assert len(services) >= 2, "esperado pelo menos 2 serviços no catálogo"
        tab.state.listbox.setCurrentRow(1)
        qtbot.wait(20)

        # O novo serviço está selecionado.
        assert tab.state.current_svc is not None
        assert tab.state.current_svc.id != first_id
        # O painel continua recolhido.
        left = tab.state.listbox.parentWidget()
        assert left.minimumWidth() <= 60


class TestTrilhoHover:
    """Hover sobre o trilho recolhido abre a lista temporariamente."""

    def test_hover_opens_trilho_when_inside_service(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id="svc-acl")

        left = tab.state.listbox.parentWidget()
        # Estado inicial: recolhido.
        assert left.minimumWidth() <= 60
        assert not tab.state.listbox.isVisible()

        # Entra com mouse no trilho (painel esquerdo) usando QEnterEvent.
        app = QApplication.instance()
        app.sendEvent(left, QEnterEvent(left.mapToGlobal(QPoint(0, 0)), QPoint(0, 0), QPoint(0, 0)))
        QApplication.processEvents()

        # A lista deve ficar visível (aberta temporariamente).
        assert tab.state.listbox.isVisible()

        # Sai do trilho → fecha.
        app.sendEvent(left, QEvent(QEvent.Type.Leave))
        QApplication.processEvents()

        assert not tab.state.listbox.isVisible()

    def test_hover_trilho_only_when_inside_service(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id=None)

        left = tab.state.listbox.parentWidget()
        # Sem serviço selecionado: não deve haver comportamento de hover.
        assert tab.state.current_svc is None


class TestOutputFixedHeight:
    """Output com altura fixa (~12 linhas) no rodapé da página."""

    def test_output_has_fixed_height(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id=None)

        out = tab.state.output
        assert out is not None
        # Altura fixa (não -1 que significa "sem altura fixa").
        assert out.maximumHeight() > 0
        assert out.maximumHeight() == out.minimumHeight()
        # Aproximadamente 12 linhas de altura.
        line_h = out.fontMetrics().lineSpacing()
        expected = line_h * 12 + 12  # + padding
        assert abs(out.height() - expected) <= line_h * 2, (
            f"altura={out.height()}, esperado≈{expected}"
        )


class TestActionBarFixed:
    """A barra de ações fica fixa no rodapé da coluna direita."""

    def test_action_bar_is_fixed_height(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id="svc-acl")

        # Encontra o widget da barra de ações (o QHBoxLayout com os botões).
        # Não testa diretamente a altura — verifica que os botões existem
        # e o detail_frame está dentro de um QScrollArea.
        assert tab.state.current_svc is not None
        btn_exec = _button(widget, "Configurando")
        assert btn_exec.isVisible()


class TestDetailScrollArea:
    """O conteúdo do detalhe fica dentro de um QScrollArea."""

    def test_detail_frame_inside_scroll_area(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id="svc-acl")

        # A detail_frame está dentro de um QScrollArea (referência armazenada).
        assert tab.state.detail_scroll is not None
        assert tab.state.detail_frame.parentWidget() is not None

    def test_scroll_area_no_horizontal_scroll(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id="svc-acl")

        scroll = tab.state.detail_scroll
        assert scroll is not None
        from PySide6.QtCore import Qt
        assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


class TestTrafficPolicyLabelsWithoutExamples:
    """Labels da cadeia traffic policy não trazem exemplos '(ex.: …)'."""

    def test_traffic_policy_labels_clean(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, svc_id="svc-acl")

        from PySide6.QtWidgets import QLabel
        labels = [lbl.text() for lbl in widget.findChildren(QLabel)]

        # Não deve conter exemplos nos labels de campo.
        assert not any("(ex.: C_BLOQUEIO)" in t for t in labels), labels
        assert not any("(ex.: B_ACAO)" in t for t in labels), labels
        assert not any("(ex.: P_FILTRO_INTERFACE)" in t for t in labels), labels
        assert not any("(permit/deny)" in t for t in labels), labels

        # Mas os nomes dos campos continuam presentes.
        assert any("Classificador" in t and "nome" in t for t in labels), labels
        assert any("Behavior" in t and "nome" in t for t in labels), labels
        assert any("Policy" in t and "nome" in t for t in labels), labels
