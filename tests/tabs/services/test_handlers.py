"""Testes da aba Serviços — ServicesHandlers (tabs/services/handlers.py).

Migrados de tests/test_services_mixin.py e tests/test_services_validation.py
(F2-services do plano plano-abas-independentes). O ServicesMixin legado foi
removido junto com handlers/services.py — validação de template/allowlist
e caminhos mock/cli com confirmação destrutiva e auditoria de bloqueio.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from huawei_manager.services import ServiceDef
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services.handlers import (
    ServicesHandlers,
    _build_service_allow_patterns,
    _template_to_pattern,
)
from huawei_manager.tabs.services.state import ServicesState


def _make(**overrides) -> tuple[ServicesHandlers, ServicesState, TabContext]:
    """(handlers, state, ctx) — 34 campos; overrides por chave."""
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
    ctx = TabContext(**fields)
    state = ServicesState()
    state.output = MagicMock()
    state.device_lbl = MagicMock()
    return ServicesHandlers(ctx, state), state, ctx


def _output_texts(out) -> str:
    """Concatena tudo que foi 'escrito' no out (setPlainText + append)."""
    parts = []
    for c in out.setPlainText.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    for c in out.append.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    return "\n".join(parts)


def _make_svc(**overrides) -> ServiceDef:
    defaults = dict(
        id="svc-001",
        name="Test Service",
        description="test command <param1>",
        category="test",
        device_types=["ROUTER"],
        cli_commands=["test command <param1>"],
        config_mode=False,
    )
    defaults.update(overrides)
    return ServiceDef(**defaults)


def _capture_spawn(fn, *a) -> None:
    fn(*a)


class TestRunService:
    def test_sets_label_without_device(self):
        h, st, ctx = _make()
        svc = _make_svc()
        h.run_service(svc)
        st.device_lbl.setText.assert_called_once()
        label = st.device_lbl.setText.call_args[0][0]
        assert "Test Service" in label

    def test_sets_label_with_device(self):
        device = MagicMock()
        device.name = "MyDevice"
        device.host = "10.0.0.1"
        h, st, ctx = _make(device=lambda: device)
        svc = _make_svc()
        h.run_service(svc)
        label = st.device_lbl.setText.call_args[0][0]
        assert "MyDevice" in label

    def test_spawns_io(self):
        h, st, ctx = _make()
        svc = _make_svc()
        h.run_service(svc)
        ctx.spawn_io.assert_called_once()

    def test_param_rejects_injection(self):
        h, st, ctx = _make()
        st.param_entries["param1"] = MagicMock(
            text=MagicMock(return_value="evil; rm -rf /"))
        svc = _make_svc(config_mode=True)
        h.run_service(svc)
        written = _output_texts(st.output)
        assert "caracteres invalidos" in written

    def test_param_substitutes_value(self):
        entry = MagicMock()
        entry.text.return_value = "hello world"
        h, st, ctx = _make()
        st.param_entries["param1"] = entry
        svc = _make_svc(config_mode=True)
        h.run_service(svc)
        ctx.spawn_io.assert_called_once()

    def test_mock_mode_writes_result(self):
        h, st, ctx = _make(spawn_io=_capture_spawn)
        svc = _make_svc()
        h.run_service(svc)
        assert _output_texts(st.output) != ""

    def test_cli_no_ssh_writes_error(self):
        device = MagicMock()
        h, st, ctx = _make(
            svc_mode=lambda: "cli",
            device=lambda: device,
            ensure_device_ready=MagicMock(return_value=device),
            spawn_io=_capture_spawn,
        )
        ctx.sb.is_alive.return_value = False
        svc = _make_svc()
        h.run_service(svc)
        assert "Sem sessao SSH" in _output_texts(st.output)

    def test_unknown_mode_writes_message(self):
        h, st, ctx = _make(
            svc_mode=lambda: "unknown",
            spawn_io=_capture_spawn,
        )
        ctx.sb.is_alive.return_value = True
        svc = _make_svc()
        h.run_service(svc)
        assert "desconhecido" in _output_texts(st.output)

    @pytest.mark.parametrize("dangerous_char",
                             [";", "&", "|", "`", "$", "(", ")", "{", "}"])
    def test_param_rejects_all_dangerous_chars(self, dangerous_char):
        h, st, ctx = _make()
        st.param_entries["param1"] = MagicMock(
            text=MagicMock(return_value=f"value{dangerous_char}injection"))
        svc = _make_svc(config_mode=True)
        h.run_service(svc)
        assert "caracteres invalidos" in _output_texts(st.output)


class TestDestructiveConfirmation:

    def test_cancel_writes_and_does_not_spawn(self):
        h, st, ctx = _make()
        svc = _make_svc(config_mode=True,
                        cli_commands=["reset saved-configuration"])
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.No
            h.run_service(svc)
        msgbox.question.assert_called_once()
        ctx.spawn_io.assert_not_called()
        assert "cancelada" in _output_texts(st.output)

    def test_confirm_spawns(self):
        h, st, ctx = _make()
        svc = _make_svc(config_mode=True, cli_commands=["shutdown"])
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.Yes
            h.run_service(svc)
        msgbox.question.assert_called_once()
        ctx.spawn_io.assert_called_once()

    def test_confirm_does_not_bypass_hard_deny(self):
        h, st, ctx = _make()
        svc = _make_svc(config_mode=True,
                        cli_commands=["reset saved-configuration"])
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            msgbox.question.return_value = msgbox.StandardButton.Yes
            h.run_service(svc)
        msgbox.question.assert_called_once()
        ctx.spawn_io.assert_not_called()
        assert "bloqueado" in _output_texts(st.output)

    def test_non_destructive_no_dialog(self):
        h, st, ctx = _make()
        svc = _make_svc(config_mode=True)
        with patch("PySide6.QtWidgets.QMessageBox") as msgbox:
            h.run_service(svc)
        msgbox.question.assert_not_called()


class TestAuditDenied:

    def test_logs_operation_when_rejected(self):
        logger = MagicMock()
        h, st, ctx = _make(audit=logger)
        svc = _make_svc(cli_commands=["delete flash:/file.cfg"])
        h.run_service(svc)
        logger.log_operation.assert_called_once()
        kwargs = logger.log_operation.call_args.kwargs
        assert kwargs.get("status") == "blocked"
        assert kwargs.get("service") == "Test Service"

    def test_skips_audit_when_no_logger(self):
        h, st, ctx = _make()
        svc = _make_svc(cli_commands=["delete flash:/file.cfg"])
        h.run_service(svc)
        ctx.spawn_io.assert_not_called()
        assert "bloqueado" in _output_texts(st.output)


# ── Validação (migrado de test_services_validation.py) ───────────────

def _match(pattern: re.Pattern[str], cmd: str) -> bool:
    return bool(pattern.search(cmd))


class TestTemplateToPattern:
    def test_placeholder_accepts_multiword_value(self):
        pat = _template_to_pattern("test command <param1>")
        assert _match(pat, "test command hello")
        assert _match(pat, "test command hello world")

    def test_placeholder_requires_value(self):
        pat = _template_to_pattern("test command <param1>")
        assert not _match(pat, "test command")

    def test_literal_is_escaped(self):
        pat = _template_to_pattern("display version")
        assert _match(pat, "display version")
        assert not _match(pat, "display version is real")
        assert not _match(pat, "displayx version")

    def test_alternation_split(self):
        pats = _build_service_allow_patterns(
            _make_svc(description="shutdown | undo shutdown",
                      cli_commands=["shutdown", "undo shutdown"])
        )
        assert any(_match(p, "shutdown") for p in pats)
        assert any(_match(p, "undo shutdown") for p in pats)


class TestValidateService:
    def _handler(self) -> ServicesHandlers:
        return ServicesHandlers(MagicMock(), MagicMock())

    def test_command_from_template_is_allowed(self):
        h = self._handler()
        svc = _make_svc()
        assert h.validate_service(svc, ["test command hello"]) == []

    def test_command_outside_template_is_rejected(self):
        h = self._handler()
        svc = _make_svc()
        rejected = h.validate_service(svc, ["show run hidden"])
        assert len(rejected) == 1
        assert rejected[0][0] == "show run hidden"
        assert "fora do template" in rejected[0][1]

    def test_destructive_command_is_rejected(self):
        h = self._handler()
        svc = _make_svc(config_mode=True,
                        cli_commands=["reset saved-configuration"])
        rejected = h.validate_service(svc, ["reset saved-configuration"])
        assert len(rejected) == 1
        assert "destrutivo" in rejected[0][1]

    def test_delete_word_is_rejected(self):
        h = self._handler()
        svc = _make_svc(config_mode=True)
        rejected = h.validate_service(svc, ["test command delete flash"])
        assert len(rejected) == 1
        assert "destrutivo" in rejected[0][1]

    def test_alternation_allows_any_branch(self):
        h = self._handler()
        svc = _make_svc(description="shutdown | undo shutdown",
                        cli_commands=["shutdown", "undo shutdown"])
        assert h.validate_service(svc, ["shutdown"]) == []
        assert h.validate_service(svc, ["undo shutdown"]) == []

    def test_empty_command_list_returns_empty(self):
        h = self._handler()
        svc = _make_svc()
        assert h.validate_service(svc, []) == []
