"""Testes de unidade e interface da aba Config Básica (F2)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QWidget

from huawei_manager.basic_config.models import BasicConfigPlan
from huawei_manager.basic_config.vrp_version import VrpVersion
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.basic_config.handlers import BasicConfigHandlers
from huawei_manager.tabs.basic_config.page import BasicConfigTab
from huawei_manager.tabs.basic_config.state import BasicConfigState


def _make_ctx(**overrides) -> TabContext:
    """TabContext fake com os 34 campos obrigatórios do contrato."""
    fields = dict(
        sb=MagicMock(),
        audit=MagicMock(),
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: MagicMock(name="RTR-01", host="10.0.0.1"),
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *args: fn(*args) if callable(fn) else None,
        spawn_cpu=lambda fn, *args: fn(*args) if callable(fn) else None,
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
        dry_run=MagicMock(),
        get_last_config_command=MagicMock(return_value=None),
        set_last_config_command=MagicMock(),
        drv=lambda: MagicMock(),
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "cli",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=MagicMock()),
        refresh_devices=MagicMock(),
        show_device_dialog=MagicMock(),
        delete_device=MagicMock(),
        on_device_selected=MagicMock(),
        clear_device_target=MagicMock(),
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    ctx.session._host = "10.0.0.1"
    ctx.session._user = "admin"
    return ctx


class TestBasicConfigTabUI:
    def test_build_and_dispose_lifecycle(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx()
        widget = tab.build(ctx)
        assert isinstance(widget, QWidget)
        qtbot.addWidget(widget)

        assert tab.state.hostname_chk is not None
        assert tab.state.iface_l3_chk is not None
        assert tab.state.l2_chk is not None
        assert tab.state.ssh_chk is not None
        assert tab.state.admin_chk is not None
        assert tab.state.btn_apply is not None

        tab.dispose()
        assert tab._ctx is None
        assert tab._handlers is None

    def test_password_fields_are_masked(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx()
        widget = tab.build(ctx)
        qtbot.addWidget(widget)

        from PySide6.QtWidgets import QLineEdit

        assert tab.state.ssh_pass.echoMode() == QLineEdit.EchoMode.Password
        assert tab.state.ssh_pass_confirm.echoMode() == QLineEdit.EchoMode.Password
        assert tab.state.admin_pass.echoMode() == QLineEdit.EchoMode.Password
        assert tab.state.admin_pass_confirm.echoMode() == QLineEdit.EchoMode.Password


class TestBasicConfigHandlers:
    def test_empty_plan_raises_validation_error(self):
        state = BasicConfigState()
        ctx = _make_ctx()
        h = BasicConfigHandlers(ctx, state)
        with pytest.raises(SdnValidationError, match="Nenhuma seção"):
            h.build_plan_from_ui()

    def test_hostname_plan_generation(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx()
        w = tab.build(ctx)
        qtbot.addWidget(w)

        tab.state.hostname_chk.setChecked(True)
        tab.state.hostname_input.setText("Core-Router-01")

        h = tab._h()
        plan = h.build_plan_from_ui()
        assert plan.hostname is not None
        assert plan.hostname.hostname == "Core-Router-01"
        assert plan.build_lines() == ["sysname Core-Router-01"]

    def test_interface_l3_validation(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx()
        w = tab.build(ctx)
        qtbot.addWidget(w)

        tab.state.iface_l3_chk.setChecked(True)
        tab.state.iface_l3_name.setText("GigabitEthernet0/0/1")
        tab.state.iface_l3_ip.setText("192.168.10.1")
        tab.state.iface_l3_mask.setText("255.255.255.0")
        tab.state.iface_l3_desc.setText("Link-WAN")

        h = tab._h()
        plan = h.build_plan_from_ui()
        assert plan.interface_l3 is not None
        lines = plan.build_lines()
        assert "interface GigabitEthernet0/0/1" in lines
        assert "ip address 192.168.10.1 255.255.255.0" in lines
        assert "description Link-WAN" in lines

    def test_ssh_password_mismatch_raises_error(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx()
        w = tab.build(ctx)
        qtbot.addWidget(w)

        tab.state.ssh_chk.setChecked(True)
        tab.state.ssh_user.setText("admin_ssh")
        tab.state.ssh_pass.setText("SenhaForte123@")
        tab.state.ssh_pass_confirm.setText("Diferente123@")

        h = tab._h()
        with pytest.raises(SdnValidationError, match="não confere"):
            h.build_plan_from_ui()

    def test_apply_requires_admin_role(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx(require_access=lambda role: False)
        w = tab.build(ctx)
        qtbot.addWidget(w)

        h = tab._h()
        h.apply_plan()
        ctx.sb.send_config_block.assert_not_called()
        assert "Permissão negada" in tab.state.output.toPlainText()

    def test_apply_mock_mode_does_not_mutate(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx(svc_mode=lambda: "mock")
        w = tab.build(ctx)
        qtbot.addWidget(w)

        tab.state.hostname_chk.setChecked(True)
        tab.state.hostname_input.setText("Router-Mock")

        h = tab._h()
        h.apply_plan()
        ctx.sb.send_config_block.assert_not_called()
        assert "Modo MOCK ativo" in tab.state.output.toPlainText()

    def test_apply_success_calls_send_config_block(self, qtbot):
        tab = BasicConfigTab()
        ctx = _make_ctx()
        # send_command retorna valores diferentes por comando:
        # - display version -> versão VRP
        # - display current-configuration -> inclui o sysname configurado
        # - outros -> vazio
        def _send_command_side_effect(cmd, *args, **kwargs):
            if "version" in cmd:
                return "VRP (R) Version 8.200, ..."
            if "current-configuration" in cmd:
                return "sysname Router-Real\ninterface GigabitEthernet0/0/0\n"
            return ""
        ctx.sb.send_command.side_effect = _send_command_side_effect
        ctx.sb.send_config_block.return_value = (True, "OK Configuração aplicada")
        w = tab.build(ctx)
        qtbot.addWidget(w)

        tab.state.hostname_chk.setChecked(True)
        tab.state.hostname_input.setText("Router-Real")

        h = tab._h()
        h.apply_plan()
        ctx.sb.send_config_block.assert_called_once()
        call_kwargs = ctx.sb.send_config_block.call_args.kwargs
        assert call_kwargs["vrp_version"] == VrpVersion.VRP8
        assert "OK Configuração aplicada" in tab.state.output.toPlainText()
        ctx.set_last_config_command.assert_called_once()

    def test_apply_save_optional_checkbox_unchecked(self, qtbot):
        """Save é opcional: checkbox não marcado → send=False."""
        tab = BasicConfigTab()
        ctx = _make_ctx()
        def _send_command_side_effect(cmd, *args, **kwargs):
            if "version" in cmd:
                return "VRP (R) Version 8.200, ..."
            if "current-configuration" in cmd:
                return "sysname Router-Real\ninterface GigabitEthernet0/0/0\n"
            return ""
        ctx.sb.send_command.side_effect = _send_command_side_effect
        ctx.sb.send_config_block.return_value = (True, "OK")
        w = tab.build(ctx)
        qtbot.addWidget(w)

        tab.state.hostname_chk.setChecked(True)
        tab.state.hostname_input.setText("Router-Real")
        # Checkbox de save NÃO marcado (padrão)
        tab.state.save_chk.setChecked(False)

        h = tab._h()
        h.apply_plan()
        call_kwargs = ctx.sb.send_config_block.call_args.kwargs
        assert call_kwargs["save"] is False, (
            f"Esperado save=False com checkbox desmarcado, obtido: {call_kwargs['save']}"
        )

    def test_apply_save_optional_checkbox_checked(self, qtbot):
        """Save é opcional: checkbox marcado → send=True."""
        tab = BasicConfigTab()
        ctx = _make_ctx()
        def _send_command_side_effect(cmd, *args, **kwargs):
            if "version" in cmd:
                return "VRP (R) Version 8.200, ..."
            if "current-configuration" in cmd:
                return "sysname Router-Real\ninterface GigabitEthernet0/0/0\n"
            return ""
        ctx.sb.send_command.side_effect = _send_command_side_effect
        ctx.sb.send_config_block.return_value = (True, "OK")
        w = tab.build(ctx)
        qtbot.addWidget(w)

        tab.state.hostname_chk.setChecked(True)
        tab.state.hostname_input.setText("Router-Real")
        tab.state.save_chk.setChecked(True)

        h = tab._h()
        h.apply_plan()
        call_kwargs = ctx.sb.send_config_block.call_args.kwargs
        assert call_kwargs["save"] is True, (
            f"Esperado save=True com checkbox marcado, obtido: {call_kwargs['save']}"
        )
