"""Handler da aba Tabela ARP — busca da tabela ARP via driver.

Extraído de ``handlers/fetch.py`` (``FetchMixin._fetch_arp``, F2-arp do
plano ``plano-abas-independentes.md``): a classe injetada
:class:`ArpHandlers` ``(ctx, state)`` lê só o :class:`TabContext`.
``_fetch_info`` permanece no mixin legado até a aba info migrar (F2).
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.tabs import _ui

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.arp.state import ArpState


class ArpHandlers:
    """Busca da tabela ARP (roda na IO thread via ctx.run)."""

    def __init__(self, ctx: TabContext, state: ArpState) -> None:
        self._ctx = ctx
        self._state = state

    def fetch_arp(self) -> None:
        """Busca a tabela ARP do roteador."""
        self._ctx.touch_session()
        try:
            entries = self._ctx.drv().get_arp_table()
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(self._state.out, f"✘ Falha SSH: {exc}",
                      self._ctx.dispatch)
            return
        buf = io.StringIO()
        buf.write(f"{'IP Address':<18} {'MAC Address':<20} {'Tipo':<6} "
                  f"{'Interface'}\n")
        buf.write(f"{'-' * 60}\n")
        for e in entries:
            buf.write(f"{e.ip_address:<18} {e.mac_address:<20} "
                      f"{e.status:<6} {e.interface}\n")
        _ui.write(self._state.out, buf.getvalue(), self._ctx.dispatch)
        self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                      source="fetch",
                                      payload=CommandExecutedPayload(
                                          command="display arp")))
