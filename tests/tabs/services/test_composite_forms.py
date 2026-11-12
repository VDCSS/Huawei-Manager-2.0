"""TDD dos formulários compostos na aba Serviços (UI + handlers).

Cobre o serviço único de ACL (``svc-acl``) e o de rota estática
(``svc-static-route``): construção do formulário, pré-visualização,
aplicação com a mesma lógica de envio/confirmação da aba Config Básica
(commit automático conforme a VRP + save opcional), verificação pós-aplicação
e rollback.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit

from huawei_manager.basic_config.vrp_version import VrpVersion
from huawei_manager.exceptions import SdnError
from huawei_manager.services import get_service_by_id
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services.handlers import ServicesHandlers
from huawei_manager.tabs.services.page import ServicesTab
from huawei_manager.tabs.services.state import ServicesState


def _fake_ctx(**overrides) -> TabContext:
    drv = overrides.pop("drv", MagicMock())
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
        drv=lambda: drv,
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "mock",
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


def _device():
    """Callable que devolve o device fake (o TabContext espera uma função)."""
    dev = MagicMock()
    dev.name = "RTR-01"
    dev.host = "10.0.0.1"
    dev.port = 22
    dev.type = "ROUTER"
    dev.status = "online"
    return lambda: dev


#: O pytest-qt guarda apenas uma *weak reference* dos widgets registrados —
#: a página da aba morreria assim que o helper devolvesse. Mantemos uma
#: referência forte para o widget vivo durante o teste.
_KEEP_ALIVE: list = []


def _build_tab(qtbot, ctx: TabContext) -> ServicesTab:
    tab = ServicesTab()
    widget = tab.build(ctx)
    qtbot.addWidget(widget)
    _KEEP_ALIVE.append(widget)
    tab.refresh_service_list()
    return tab


def _select_service(tab: ServicesTab, svc_id: str) -> None:
    for idx, svc in enumerate(tab.state.services):
        if svc.id == svc_id:
            tab.state.listbox.setCurrentRow(idx)
            tab._on_service_select(idx)
            return
    raise AssertionError(f"serviço '{svc_id}' não está na lista")


def _set_field(form, section: str, key: str, value: str, row: int = 0) -> None:
    """Define o valor de um campo do formulário (simula digitação)."""
    form.set_value(section, key, value, row)


def _fill_acl(form, **over) -> None:
    """Preenche o formulário de ACL com um cenário válido."""
    form.set_value("identificacao", "acl_type", over.get("acl_type", "avancada"))
    form.set_value("identificacao", "id_mode", over.get("id_mode", "numero"))
    form.set_value("identificacao", "acl_number", over.get("acl_number", "3000"))
    form.set_value("identificacao", "acl_name", over.get("acl_name", ""))
    form.set_value("rules", "rule_id", over.get("rule_id", "5"), 0)
    form.set_value("rules", "action", over.get("action", "permit"), 0)
    form.set_value("rules", "protocol", over.get("protocol", "ip"), 0)
    form.set_value("rules", "source", over.get("source", "10.0.0.0"), 0)
    form.set_value(
        "rules", "source_wildcard", over.get("source_wildcard", "0.0.0.255"), 0)
    form.set_value("rules", "destination", over.get("destination", ""), 0)
    form.set_value(
        "rules", "destination_wildcard", over.get("destination_wildcard", ""), 0)
    form.set_value(
        "rules", "destination_port", over.get("destination_port", ""), 0)


def _fill_route(form, **over) -> None:
    """Preenche o formulário de rota estática com um cenário válido."""
    form.set_value("routes", "destination", over.get("destination", "0.0.0.0"), 0)
    form.set_value("routes", "mask", over.get("mask", "0.0.0.0"), 0)
    form.set_value("routes", "interface", over.get("interface", ""), 0)
    form.set_value("routes", "next_hop", over.get("next_hop", "10.0.12.2"), 0)
    form.set_value("routes", "preference", over.get("preference", ""), 0)
    form.set_value("routes", "description", over.get("description", ""), 0)


class TestCompositeFormUi:
    def test_acl_service_is_single_entry_in_the_list(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        acl_ids = [s.id for s in tab.state.services if s.category == "config-acl"]
        assert acl_ids == ["svc-acl"], (
            f"deve haver UMA entrada de ACL na lista, obtido: {acl_ids}"
        )

    def test_legacy_acl_services_are_not_listed(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        ids = {s.id for s in tab.state.services}
        assert "router-config-acl-rule-basic" not in ids
        assert "router-config-traffic-filter" not in ids

    def test_static_route_service_is_listed(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        ids = {s.id for s in tab.state.services}
        assert "svc-static-route" in ids

    def test_selecting_acl_builds_the_form(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None, "formulário de ACL não foi construído"
        values = form.values()
        assert set(values) == {"identificacao", "rules", "applications"}

    def test_acl_form_starts_with_one_rule_row(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None
        assert len(form.values()["rules"]) == 1  # type: ignore[arg-type]

    def test_acl_form_has_no_application_row_by_default(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None
        assert form.values()["applications"] == []

    def test_save_checkbox_exists_and_is_unchecked(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        chk = tab.state.save_chk
        assert isinstance(chk, QCheckBox)
        assert chk.isChecked() is False, "save deve estar desmarcado por padrão"

    def test_acl_name_field_is_hidden_until_name_mode(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None
        # por padrão id_mode = "numero" → o campo de nome não aparece
        name_visible = [
            box.widget.isVisibleTo(form)
            for box in form._boxes  # noqa: SLF001 - verificação interna
            if box.field.key == "acl_name"
        ]
        assert name_visible == [False]

    def test_route_form_has_one_row(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-static-route")
        form = tab.state.form_state
        assert form is not None
        assert len(form.values()["routes"]) == 1  # type: ignore[arg-type]

    def test_switching_service_clears_previous_form(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        _select_service(tab, "svc-static-route")
        form = tab.state.form_state
        assert form is not None
        assert set(form.values()) == {"routes"}


def _acl_handlers(qtbot, **ctx_over):
    ctx = _fake_ctx(device=_device(), **ctx_over)
    tab = _build_tab(qtbot, ctx)
    _select_service(tab, "svc-acl")
    return tab._handlers, tab.state, ctx


def _out(state) -> str:
    """Texto atual do painel de saída."""
    return state.output.toPlainText() if state.output is not None else ""


def _sb_mock(
    running_config: str = "",
    version: str = "VRP (R) Version 8.180",
) -> MagicMock:
    """Mock do southbound com respostas **coerentes por comando**.

    ``display version`` devolve a versão VRP; ``display current-configuration``
    devolve o running-config (usado na verificação pós-aplicação).
    """
    sb = MagicMock()
    sb.is_alive.return_value = True

    def _send_command(cmd, *a, **kw):
        if "version" in cmd:
            return version
        if "current-configuration" in cmd:
            return running_config
        return ""

    sb.send_command.side_effect = _send_command
    sb.send_config_block.return_value = (True, "OK")
    sb.save_running_config.return_value = (True, "OK salvo")
    return sb


#: Running-config mínimo que satisfaz as âncoras do formulário de ACL padrão.
_ACL_RUNNING = (
    "sysname RTR\n"
    "acl number 3000\n"
    " rule 5 permit ip source 10.0.0.0 0.0.0.255\n"
)


class TestCompositeHandlers:
    def test_preview_form_writes_the_block_without_applying(self, qtbot):
        h, state, ctx = _acl_handlers(qtbot)
        form = state.form_state
        assert form is not None
        _fill_acl(form)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.preview_form(svc)
        text = _out(state)
        assert "acl number 3000" in text
        assert "Nada foi aplicado" in text
        ctx.sb.send_config_block.assert_not_called()

    def test_invalid_form_is_reported_and_nothing_is_applied(self, qtbot):
        h, state, ctx = _acl_handlers(qtbot)
        form = state.form_state
        assert form is not None
        # ACL avançada exige número 3000-3999
        _fill_acl(form, acl_number="1000")
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        text = _out(state)
        assert "inválido" in text.lower() or "faixa" in text.lower()
        ctx.sb.send_config_block.assert_not_called()

    def test_apply_uses_vrp_version_and_save_from_checkbox(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        ctx_sb.send_command.return_value = (
            "Huawei Versatile Routing Platform Software\nVRP (R) Version 8.180\n"
        )
        ctx_sb.send_config_block.return_value = (True, "OK")
        h, state, ctx = _acl_handlers(qtbot, sb=ctx_sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        assert ctx_sb.send_config_block.called
        kwargs = ctx_sb.send_config_block.call_args.kwargs
        assert kwargs["vrp_version"] == VrpVersion.VRP8
        assert kwargs["save"] is False, "save desmarcado por padrão"

    def test_apply_persists_only_after_verification(self, qtbot):
        """Com 'Salvar' marcado: aplica → verifica → só então persiste."""
        sb = _sb_mock(running_config=_ACL_RUNNING)
        h, state, ctx = _acl_handlers(qtbot, sb=sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        assert state.save_chk is not None
        state.save_chk.setChecked(True)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        kwargs = sb.send_config_block.call_args.kwargs
        assert kwargs["save"] is False, (
            "a persistência é separada da aplicação (aplica → verifica → salva)"
        )
        sb.save_running_config.assert_called_once()
        assert sb.save_running_config.call_args.args[0] == VrpVersion.VRP8

    def test_apply_does_not_persist_when_verification_fails(self, qtbot):
        """Verificação falha → nada é salvo na startup-config."""
        sb = _sb_mock(running_config="sysname RTR\n")
        h, state, ctx = _acl_handlers(qtbot, sb=sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        assert state.save_chk is not None
        state.save_chk.setChecked(True)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        assert "não encontrada" in _out(state)
        sb.save_running_config.assert_not_called()

    def test_apply_detects_vrp5(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        ctx_sb.send_command.return_value = "VRP (R) Version 5.170\n"
        ctx_sb.send_config_block.return_value = (True, "OK")
        h, state, ctx = _acl_handlers(qtbot, sb=ctx_sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        kwargs = ctx_sb.send_config_block.call_args.kwargs
        assert kwargs["vrp_version"] == VrpVersion.VRP5

    def test_apply_block_contains_the_rendered_lines(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        ctx_sb.send_command.return_value = "VRP (R) Version 8.180\n"
        ctx_sb.send_config_block.return_value = (True, "OK")
        h, state, ctx = _acl_handlers(qtbot, sb=ctx_sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        lines = ctx_sb.send_config_block.call_args.args[0]
        assert lines[0] == "acl number 3000"
        assert "rule 5 permit ip source 10.0.0.0 0.0.0.255" in lines

    def test_verify_failure_is_reported(self, qtbot):
        """A verificação real: âncora ausente → falha reportada."""
        sb = _sb_mock(running_config="sysname RTR\n")
        h, state, ctx = _acl_handlers(qtbot, sb=sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        text = _out(state)
        assert "não encontrada" in text
        # o comando de configuração fica registrado para rollback posterior
        assert ctx.set_last_config_command.called

    def test_verify_read_error_is_reported(self, qtbot):
        """Falha de leitura na verificação → erro reportado (não "Falha SSH")."""
        sb = _sb_mock()
        calls = {"n": 0}

        def _send_command(cmd, *a, **kw):
            calls["n"] += 1
            if "version" in cmd:
                return "VRP (R) Version 8.180"
            if calls["n"] <= 2:
                # (1) display version  (2) snapshot pré-mudança
                return _ACL_RUNNING
            raise SdnError("link down")

        sb.send_command.side_effect = _send_command
        h, state, ctx = _acl_handlers(qtbot, sb=sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        text = _out(state)
        assert "falha ao ler o running-config" in text.lower()

    def test_admin_role_is_required(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        h, state, ctx = _acl_handlers(
            qtbot, sb=ctx_sb, svc_mode=lambda: "cli",
            require_access=lambda level: False,
        )
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        ctx_sb.send_config_block.assert_not_called()
        text = _out(state)
        assert "Permissão negada" in text

    def test_mock_mode_does_not_touch_the_device(self, qtbot):
        ctx_sb = MagicMock()
        h, state, ctx = _acl_handlers(qtbot, sb=ctx_sb, svc_mode=lambda: "mock")
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        ctx_sb.send_config_block.assert_not_called()
        text = _out(state)
        assert "acl number 3000" in text


class TestCompositeConsult:
    def test_consult_sends_the_read_only_command(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        ctx_sb.send_command.return_value = "ACL 3000\n  rule 5 permit ip ..."
        h, state, ctx = _acl_handlers(qtbot, sb=ctx_sb, svc_mode=lambda: "cli")
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.consult_form(svc)
        ctx_sb.send_command.assert_called_once_with("display acl all")
        assert "display acl all" in _out(state)

    def test_consult_does_not_apply_anything(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        h, state, ctx = _acl_handlers(qtbot, sb=ctx_sb, svc_mode=lambda: "cli")
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.consult_form(svc)
        ctx_sb.send_config_block.assert_not_called()


class TestCompositeConditionalFields:
    def test_form_does_not_offer_the_both_mode(self, qtbot):
        """'acl number N name X' é recusado pelo device → modo 'ambos' removido."""
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None
        combos = [
            box.combo
            for box in form._boxes  # noqa: SLF001 - verificação interna
            if box.field.key == "id_mode" and box.combo is not None
        ]
        assert combos, "campo id_mode não encontrado"
        combo = combos[0]
        items = [combo.itemText(i) for i in range(combo.count())]
        assert "ambos" not in items
        assert items == ["numero", "nome"]

    def test_hidden_fields_are_not_sent(self, qtbot):
        """Campo oculto não vai para os valores (nada de valor residual)."""
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None
        # preenche o nome (oculto no modo "numero") e o número
        form.set_value("identificacao", "acl_name", "MGT")
        ident = form.values()["identificacao"]
        assert "acl_name" not in ident
        # ao trocar para o modo "nome", o número sai e o nome entra
        form.set_value("identificacao", "id_mode", "nome")
        ident = form.values()["identificacao"]
        assert "acl_number" not in ident
        assert ident["acl_name"] == "MGT"


class TestConditionalFields:
    def test_each_application_row_resolves_its_own_fields(self, qtbot):
        """A visibilidade condicional é resolvida por linha (interface vs vty)."""
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None
        form.add_row("applications")
        form.add_row("applications")
        form.set_value("applications", "where", "interface", 0)
        form.set_value("applications", "where", "vty", 1)

        def visible(section, key, row):
            rows = form.values()[section]
            boxes = form._rows[section][row]  # noqa: SLF001
            return boxes[key].widget.isVisibleTo(form)

        assert visible("applications", "interface", 0) is True
        assert visible("applications", "vty_range", 0) is False
        assert visible("applications", "vty_range", 1) is True
        assert visible("applications", "interface", 1) is False

    def test_acl_number_field_hidden_in_name_mode(self, qtbot):
        ctx = _fake_ctx(device=_device())
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-acl")
        form = tab.state.form_state
        assert form is not None
        boxes = form._single["identificacao"]  # noqa: SLF001
        assert boxes["acl_number"].widget.isVisibleTo(form) is True
        form.set_value("identificacao", "id_mode", "nome")
        assert boxes["acl_number"].widget.isVisibleTo(form) is False
        assert boxes["acl_name"].widget.isVisibleTo(form) is True


class TestCompositePolicy:
    """Política de segurança do caminho composto (allowlist/deny/confirmação)."""

    def test_deny_list_blocks_the_whole_block(self, qtbot):
        """Linha na deny-list (ex.: 'reset' na descrição) bloqueia tudo."""
        sb = _sb_mock(running_config=_ACL_RUNNING)
        h, state, ctx = _acl_handlers(qtbot, sb=sb, svc_mode=lambda: "cli")
        form = state.form_state
        assert form is not None
        _fill_acl(form, source="any", source_wildcard="")
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        # a descrição da rota pode conter 'reset' — aqui forçamos via ACL
        # NÃO é possível; usamos a rota estática.
        ctx2 = _fake_ctx(device=_device(), sb=sb, svc_mode=lambda: "cli")
        tab = _build_tab(qtbot, ctx2)
        _select_service(tab, "svc-static-route")
        _fill_route(tab.state.form_state, description="reset everything")
        svc_route = get_service_by_id("svc-static-route")
        assert svc_route is not None
        sb.send_config_block.reset_mock()
        tab._handlers.run_service(svc_route)
        sb.send_config_block.assert_not_called()
        assert "bloqueado" in _out(tab.state).lower()

    def test_sensitive_application_requires_confirmation(self, qtbot, monkeypatch):
        """Aplicação de ACL em VTY exige confirmação explícita."""
        from PySide6.QtWidgets import QMessageBox

        asked: list[str] = []

        def _question(parent, title, text, *a, **kw):
            asked.append(text)
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", staticmethod(_question))
        sb = _sb_mock(running_config=_ACL_RUNNING)
        h, state, ctx = _acl_handlers(qtbot, sb=sb, svc_mode=lambda: "cli")
        form = state.form_state
        assert form is not None
        _fill_acl(form)
        form.add_row("applications")
        form.set_value("applications", "where", "vty", 0)
        form.set_value("applications", "vty_range", "0 4", 0)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        assert asked, "a confirmação de política não foi solicitada"
        sb.send_config_block.assert_not_called()
        assert "cancelada" in _out(state).lower()

    def test_audit_records_the_persistence_state(self, qtbot):
        """A auditoria grava 'saved' verdadeiro apenas quando houve save."""
        audit = MagicMock()
        sb = _sb_mock(running_config=_ACL_RUNNING)
        h, state, ctx = _acl_handlers(
            qtbot, sb=sb, svc_mode=lambda: "cli", audit=audit)
        _fill_acl(state.form_state)
        assert state.save_chk is not None
        state.save_chk.setChecked(True)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        audit.log_operation.assert_called()
        assert audit.log_operation.call_args.kwargs["saved"] is True

    def test_config_changed_event_is_emitted(self, qtbot):
        """O core só atualiza 'last_config_change' com CONFIG_CHANGED."""
        from huawei_manager.sdn_controller.event_queue import EventType

        sb = _sb_mock(running_config=_ACL_RUNNING)
        h, state, ctx = _acl_handlers(qtbot, sb=sb, svc_mode=lambda: "cli")
        _fill_acl(state.form_state)
        svc = get_service_by_id("svc-acl")
        assert svc is not None
        h.run_service(svc)
        events = [
            call.args[0]
            for call in ctx.event_bus.put.call_args_list
        ]
        assert any(ev.type is EventType.CONFIG_CHANGED for ev in events)


class TestStaticRouteComposite:
    def test_route_apply_sends_the_rendered_route(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        ctx_sb.send_command.return_value = "VRP (R) Version 8.180\n"
        ctx_sb.send_config_block.return_value = (True, "OK")
        ctx = _fake_ctx(device=_device(), sb=ctx_sb, svc_mode=lambda: "cli")
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-static-route")
        _fill_route(tab.state.form_state)
        svc = get_service_by_id("svc-static-route")
        assert svc is not None
        tab._handlers.run_service(svc)
        lines = ctx_sb.send_config_block.call_args.args[0]
        assert lines == ["ip route-static 0.0.0.0 0.0.0.0 10.0.12.2"]

    def test_route_without_next_hop_or_interface_is_rejected(self, qtbot):
        ctx_sb = MagicMock()
        ctx_sb.is_alive.return_value = True
        ctx = _fake_ctx(device=_device(), sb=ctx_sb, svc_mode=lambda: "cli")
        tab = _build_tab(qtbot, ctx)
        _select_service(tab, "svc-static-route")
        form = tab.state.form_state
        assert form is not None
        _fill_route(form, next_hop="", interface="")
        svc = get_service_by_id("svc-static-route")
        assert svc is not None
        tab._handlers.run_service(svc)
        ctx_sb.send_config_block.assert_not_called()
