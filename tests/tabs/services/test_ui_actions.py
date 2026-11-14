"""Regressão: os botões da aba Serviços realmente executam (clique real).

Os testes de ``test_composite_forms.py`` chamam os *handlers* diretamente —
isso não exercita a fiação do ``QPushButton``. O bug do ``clicked(bool)``
sobrescrevendo o ``svc`` do ``lambda`` passou verde por lá.

Aqui os botões são **clicados de verdade** (``btn.click()``), que é o que o
usuário faz: Pré-visualizar, Consultar, Configurar (apply) e Reverter
(rollback), para ACL e Rota Estática.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel, QMessageBox, QPlainTextEdit, QPushButton

from huawei_manager.services import get_service_by_id
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services.page import ServicesTab

#: pytest-qt guarda apenas referências fracas dos widgets — mantemos uma
#: referência forte para a página viva durante o teste.
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
    """Southbound fake: responde por comando (versão VRP / running-config)."""
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


def _build(qtbot, ctx: TabContext, svc_id: str):
    tab = ServicesTab()
    widget = tab.build(ctx)
    qtbot.addWidget(widget)
    _KEEP_ALIVE.append(widget)
    tab.refresh_service_list()
    for idx, svc in enumerate(tab.state.services):
        if svc.id == svc_id:
            tab.state.listbox.setCurrentRow(idx)
            break
    else:  # pragma: no cover - serviço ausente = falha de catálogo
        raise AssertionError(f"serviço '{svc_id}' não está na lista")
    # A troca de serviço remove os widgets antigos com ``deleteLater()`` —
    # sem processar os eventos, os botões do serviço anterior (o primeiro da
    # lista, por padrão) ainda existiriam e o ``findChildren`` acharia os
    # errados.
    qtbot.wait(20)
    return tab, widget


def _button(widget, needle: str) -> QPushButton:
    for btn in widget.findChildren(QPushButton):
        if needle in btn.text():
            return btn
    raise AssertionError(f"botão '{needle}' não encontrado")


def _out(tab) -> str:
    return tab.state.output.toPlainText() if tab.state.output else ""


def _fill_acl(form) -> None:
    form.set_value("identificacao", "acl_type", "avancada")
    form.set_value("identificacao", "id_mode", "numero")
    form.set_value("identificacao", "acl_number", "3000")
    form.set_value("rules", "rule_id", "5", 0)
    form.set_value("rules", "action", "permit", 0)
    form.set_value("rules", "protocol", "ip", 0)
    form.set_value("rules", "source", "any", 0)


def _fill_route(form) -> None:
    form.set_value("routes", "destination", "10.9.0.0", 0)
    form.set_value("routes", "mask", "255.255.0.0", 0)
    form.set_value("routes", "next_hop", "10.0.12.2", 0)


def _fill_acl_traffic_policy(form) -> None:
    """Preenche a ACL e a cadeia traffic policy (classifier→behavior→policy)."""
    form.set_value("identificacao", "acl_type", "avancada")
    form.set_value("identificacao", "id_mode", "numero")
    form.set_value("identificacao", "acl_number", "3000")
    form.set_value("rules", "rule_id", "5", 0)
    form.set_value("rules", "action", "deny", 0)
    form.set_value("rules", "protocol", "ip", 0)
    form.set_value("rules", "source", "192.168.10.50", 0)
    form.set_value("rules", "source_wildcard", "0", 0)
    form.set_value("traffic_policy", "classifier_name", "C_BLOQUEIO")
    form.set_value("traffic_policy", "behavior_name", "B_ACAO")
    form.set_value("traffic_policy", "policy_name", "P_FILTRO_INTERFACE")
    form.set_value("traffic_policy", "behavior_action", "permit")
    form.add_row("applications")
    form.set_value("applications", "where", "traffic policy", 0)
    form.set_value("applications", "interface", "GigabitEthernet0/0/1", 0)
    form.set_value("applications", "direction", "inbound", 0)


class TestServiceButtonsClick:
    """Cada botão da aba deve executar a sua ação ao ser clicado."""

    def test_preview_button_renders_the_block(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fill_acl(tab.state.form_state)

        _button(widget, "Pré-visualizar").click()

        text = _out(tab)
        assert "acl number 3000" in text
        assert "Nada foi aplicado" in text
        ctx.sb.send_config_block.assert_not_called()

    def test_consult_button_queries_the_device(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")

        _button(widget, "Consultar").click()

        text = _out(tab)
        assert "display acl all" in text
        ctx.sb.send_command.assert_any_call("display acl all")

    def test_apply_button_sends_the_block(self, qtbot):
        running = "acl number 3000\n rule 5 permit ip source any\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fill_acl(tab.state.form_state)

        _button(widget, "Configurando").click()

        assert ctx.sb.send_config_block.called
        lines = ctx.sb.send_config_block.call_args.args[0]
        assert lines[0] == "acl number 3000"
        assert tab.state.last_config_command is not None

    def test_rollback_button_reverts_the_service_snapshot(self, qtbot):
        running = "acl number 3000\n rule 5 permit ip source any\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fill_acl(tab.state.form_state)
        _button(widget, "Configurando").click()

        _button(widget, "Reverter").click()

        text = _out(tab)
        assert "Nenhuma configuração anterior" not in text
        assert "snapshot" in text.lower()

    def test_rollback_without_apply_explains_absence(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")

        _button(widget, "Reverter").click()

        assert "Nenhuma configuração anterior" in _out(tab)

    def test_route_buttons_work(self, qtbot):
        running = "ip route-static 10.9.0.0 255.255.0.0 10.0.12.2\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-static-route")
        _fill_route(tab.state.form_state)

        _button(widget, "Pré-visualizar").click()
        assert "ip route-static 10.9.0.0 255.255.0.0 10.0.12.2" in _out(tab)

        _button(widget, "Configurando").click()
        assert ctx.sb.send_config_block.called
        assert tab.state.last_config_command is not None

    def test_traffic_policy_preview_shows_the_chain(self, qtbot):
        """A cadeia traffic policy aparece completa na pré-visualização."""
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fill_acl_traffic_policy(tab.state.form_state)

        _button(widget, "Pré-visualizar").click()

        text = _out(tab)
        assert "acl number 3000" in text
        assert "traffic classifier C_BLOQUEIO" in text
        assert "if-match acl 3000" in text
        assert "traffic behavior B_ACAO" in text
        assert "traffic policy P_FILTRO_INTERFACE" in text
        assert "classifier C_BLOQUEIO behavior B_ACAO" in text
        assert "traffic-policy P_FILTRO_INTERFACE inbound" in text
        ctx.sb.send_config_block.assert_not_called()

    def test_apply_does_not_touch_the_global_rollback_slot(self, qtbot):
        """Separação: Serviços não escreve o snapshot global do App."""
        running = "acl number 3000\n rule 5 permit ip source any\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fill_acl(tab.state.form_state)

        _button(widget, "Configurando").click()

        ctx.set_last_config_command.assert_not_called()
        assert tab.state.last_config_command is not None

    def test_rollback_ignores_the_global_slot(self, qtbot):
        """O rollback de Serviços usa o snapshot da própria aba."""
        ctx = _fake_ctx(get_last_config_command=MagicMock(return_value=MagicMock()))
        tab, widget = _build(qtbot, ctx, "svc-acl")

        _button(widget, "Reverter").click()

        assert "Nenhuma configuração anterior" in _out(tab)


class TestLivePreview:
    """Pré-visualização viva: o operador vê o bloco enquanto preenche."""

    def _preview(self, widget) -> QPlainTextEdit:
        for box in widget.findChildren(QPlainTextEdit):
            return box
        raise AssertionError("pré-visualização não encontrada")

    def test_preview_shows_the_block_while_typing(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")

        _fill_acl(tab.state.form_state)

        text = self._preview(widget).toPlainText()
        assert "acl number 3000" in text
        assert "rule 5 permit ip source any" in text

    def test_preview_shows_the_traffic_policy_chain(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")

        _fill_acl_traffic_policy(tab.state.form_state)

        text = self._preview(widget).toPlainText()
        assert "traffic classifier C_BLOQUEIO" in text
        assert "if-match acl 3000" in text
        assert "traffic policy P_FILTRO_INTERFACE" in text
        assert "traffic-policy P_FILTRO_INTERFACE inbound" in text

    def test_preview_reports_validation_error(self, qtbot):
        ctx = _fake_ctx()
        tab, widget = _build(qtbot, ctx, "svc-acl")

        # ACL sem número → erro de validação visível na pré-visualização.
        tab.state.form_state.set_value("identificacao", "acl_type", "avancada")

        assert "⚠" in self._preview(widget).toPlainText()


class TestTrafficPolicyHint:
    """A seção deixa claro que só os nomes são pedidos."""

    def test_hint_is_rendered_in_the_form(self, qtbot):
        ctx = _fake_ctx()
        _tab, widget = _build(qtbot, ctx, "svc-acl")

        labels = [lbl.text() for lbl in widget.findChildren(QLabel)]
        assert any("Preencha apenas os nomes" in t for t in labels), labels

    def test_name_labels_are_visible(self, qtbot):
        ctx = _fake_ctx()
        _tab, widget = _build(qtbot, ctx, "svc-acl")

        labels = [lbl.text() for lbl in widget.findChildren(QLabel)]
        assert any("Classificador" in t and "nome" in t for t in labels)
        assert any("Behavior" in t and "nome" in t for t in labels)
        assert any("Policy" in t and "nome" in t for t in labels)


class TestInterfacePrecheck:
    """Interface inexistente no device bloqueia a aplicação."""

    @pytest.fixture(autouse=True)
    def _auto_confirm(self, monkeypatch):
        """A aplicação traffic-policy pede confirmação (diálogo modal)."""
        monkeypatch.setattr(
            QMessageBox,
            "question",
            staticmethod(
                lambda *a, **kw: QMessageBox.StandardButton.Yes
            ),
        )

    def test_apply_is_blocked_when_interface_does_not_exist(self, qtbot):
        running = "interface GigabitEthernet0/0/0\n#\n"
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fill_acl_traffic_policy(tab.state.form_state)

        _button(widget, "Configurando").click()

        text = _out(tab)
        assert "inexistente" in text
        assert "GigabitEthernet0/0/1" in text
        ctx.sb.send_config_block.assert_not_called()

    def test_apply_proceeds_when_interface_exists(self, qtbot):
        running = (
            "interface GigabitEthernet0/0/1\n#\n"
            "acl number 3000\n rule 5 deny ip source 192.168.10.50 0.0.0.0\n"
        )
        ctx = _fake_ctx(sb=_sb_mock(running_config=running))
        tab, widget = _build(qtbot, ctx, "svc-acl")
        _fill_acl_traffic_policy(tab.state.form_state)

        _button(widget, "Configurando").click()

        assert ctx.sb.send_config_block.called
        lines = ctx.sb.send_config_block.call_args.args[0]
        assert "interface GigabitEthernet0/0/1" in lines
