"""Testes da aba Configuração Atual — ConfigHandlers (F2-config).

Split de tests/test_fetch_mixin.py: o caminho de _fetch_config migrou
para a classe injetada ConfigHandlers(ctx, state); route/arp/info
permanecem no FetchMixin legado.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import EventType
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.config.handlers import ConfigHandlers
from huawei_manager.tabs.config.state import ConfigState


def _make_ctx(**overrides) -> TabContext:
    """TabContext fake com todos os 29 campos; overrides por teste."""
    fields = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *args: None,
        spawn_cpu=lambda fn, *args: None,
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
        svc_mode=lambda: "mock",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=None),
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    ctx.session._host = "10.0.0.1"
    ctx.session._user = "admin"
    return ctx


def _make(**overrides) -> tuple[ConfigHandlers, ConfigState, TabContext]:
    """(handlers, state, ctx) — state.out é MagicMock de saída."""
    ctx = _make_ctx(**overrides)
    state = ConfigState()
    state.out = MagicMock()
    return ConfigHandlers(ctx, state), state, ctx


def _output_texts(out: MagicMock) -> str:
    """Concatena textos passados a setPlainText/append (padrão _ui.write)."""
    texts = []
    for c in out.setPlainText.call_args_list:
        texts.append(str(c.args[0]) if c.args else "")
    for c in out.append.call_args_list:
        texts.append(str(c.args[0]) if c.args else "")
    return "\n".join(texts)


class TestFetchConfig:
    def test_writes_output(self):
        h, state, ctx = _make()
        ctx.sb.send_command.return_value = "interface GigabitEthernet0/0/1"
        h.fetch_config()
        assert "interface GigabitEthernet0/0/1" in _output_texts(state.out)

    def test_touches_session(self):
        h, _state, ctx = _make()
        ctx.sb.send_command.return_value = "config"
        h.fetch_config()
        ctx.touch_session.assert_called_once()

    def test_posts_event(self):
        h, _state, ctx = _make()
        ctx.sb.send_command.return_value = "config"
        h.fetch_config()
        ctx.event_bus.put.assert_called_once()
        ev = ctx.event_bus.put.call_args.args[0]
        assert ev.type == EventType.COMMAND_EXECUTED
        assert ev.source == "fetch"

    def test_invalidates_on_error(self):
        h, state, ctx = _make()
        ctx.sb.send_command.side_effect = SdnError("fail")
        h.fetch_config()
        ctx.sb.invalidate_connection.assert_called_once()
        assert "Falha SSH" in _output_texts(state.out)
