"""Testes da aba Roteamento — RouteHandlers (tabs/route/handlers.py).

Migrados de tests/test_fetch_mixin.py (F2-route do plano
plano-abas-independentes). _fetch_arp/_fetch_info permanecem legados.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.exceptions import SdnError
from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.route.handlers import RouteHandlers
from huawei_manager.tabs.route.state import RouteState


def _make(**overrides) -> tuple[RouteHandlers, RouteState, TabContext]:
    """(handlers, state, ctx) — drv é getter no ctx (lambda sobre o mock)."""
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
        ensure_device_ready=MagicMock(return_value=None),
        refresh_devices=MagicMock(),
        show_device_dialog=MagicMock(),
        delete_device=MagicMock(),
        on_device_selected=MagicMock(),
        clear_device_target=MagicMock(),
    )
    fields.update(overrides)
    ctx = TabContext(**fields)
    state = RouteState()
    state.out = MagicMock()
    return RouteHandlers(ctx, state), state, ctx


def _output_texts(out) -> str:
    """Concatena tudo que foi 'escrito' no out (setPlainText + append)."""
    parts = []
    for c in out.setPlainText.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    for c in out.append.call_args_list:
        parts.append(str(c.args[0]) if c.args else "")
    return "\n".join(parts)


class TestFetchRoute:
    def test_routing_uses_driver(self):
        drv_mock = MagicMock()
        entry = MagicMock()
        entry.destination = "0.0.0.0"
        entry.mask = "0"
        entry.protocol = "static"
        entry.preference = 60
        entry.cost = 0
        entry.next_hop = "10.0.0.1"
        entry.interface = "GE0/0/1"
        drv_mock.get_routing_table.return_value = [entry]
        h, st, ctx = _make(drv=drv_mock)
        h.fetch_route(fkey="routing")
        drv_mock.get_routing_table.assert_called_once()
        texts = _output_texts(st.out)
        assert "0.0.0.0/0" in texts
        assert "Destino/Mask" in texts
        assert ctx.event_bus.put.call_count == 1

    def test_other_filter_uses_send_command(self):
        h, st, ctx = _make()
        ctx.sb.send_command.return_value = "route data"
        h.fetch_route(fkey="bgp")
        ctx.sb.send_command.assert_called_once()
        assert "route data" in _output_texts(st.out)
        assert ctx.event_bus.put.call_count == 1

    def test_routing_sdn_error_invalidates(self):
        drv_mock = MagicMock()
        drv_mock.get_routing_table.side_effect = SdnError("fail")
        h, st, ctx = _make(drv=drv_mock)
        h.fetch_route(fkey="routing")
        ctx.sb.invalidate_connection.assert_called_once()
        assert "Falha SSH" in _output_texts(st.out)

    def test_requires_fkey(self):
        h, st, ctx = _make()
        with pytest.raises(RuntimeError):
            h.fetch_route("")
