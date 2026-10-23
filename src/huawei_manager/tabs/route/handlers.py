"""Handlers da aba Roteamento — busca da tabela de rotas.

Extraído de ``handlers/fetch.py`` (F2-route do plano
``plano-abas-independentes.md``): o método ``_fetch_route`` do
``FetchMixin`` virou a classe injetada :class:`RouteHandlers`
``(ctx, state)`` — sem leitura do App, só do :class:`TabContext`.
``_fetch_arp`` e ``_fetch_info`` permanecem no mixin legado até as
fases 2 de ARP e Info migrarem.
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

from huawei_manager.constants import CLI_FILTERS
from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.tabs import _ui

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.route.state import RouteState


class RouteHandlers:
    """Busca da tabela de rotas (roda na IO thread via ctx.run)."""

    def __init__(self, ctx: TabContext, state: RouteState) -> None:
        self._ctx = ctx
        self._state = state

    def fetch_route(self, fkey: str = "") -> None:
        """Busca a tabela de roteamento com o filtro selecionado.

        fkey deve ser extraido da UI (filter_cb) ANTES de chamar este
        metodo, pois ele roda na IO thread.
        """
        self._ctx.touch_session()
        if not fkey:
            raise RuntimeError(
                "_fetch_route: fkey must be extracted in UI thread before calling")
        if fkey == "routing":
            try:
                entries = self._ctx.drv().get_routing_table()
            except SdnError as exc:
                self._ctx.sb.invalidate_connection()
                _ui.write(self._state.out, f"✘ Falha SSH: {exc}",
                          self._ctx.dispatch)
                return
            buf = io.StringIO()
            buf.write(f"{'Destino/Mask':<22} {'Proto':<10} {'Pre':>4} "
                      f"{'Custo':>6}  {'NextHop':<16} {'Interface'}\n")
            buf.write(f"{'-' * 72}\n")
            for e in entries:
                route = f"{e.destination}/{e.mask}"
                buf.write(f"{route:<22} {e.protocol:<10} {e.preference:>4} "
                          f"{e.cost:>6}  {e.next_hop:<16} {e.interface}\n")
            _ui.write(self._state.out, buf.getvalue(), self._ctx.dispatch)
            self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                          source="fetch",
                                          payload=CommandExecutedPayload(
                                              command="display ip routing-table")))
        else:
            cmd = CLI_FILTERS.get(fkey, "display ip routing-table")
            _ui.loading(self._state.out, f"Executando: {cmd}…",
                        self._ctx.dispatch)
            try:
                route_out = self._ctx.sb.send_command(cmd or "")
            except SdnError as exc:
                self._ctx.sb.invalidate_connection()
                _ui.write(self._state.out, f"✘ Falha SSH: {exc}",
                          self._ctx.dispatch)
                return
            _ui.write(self._state.out, route_out, self._ctx.dispatch)
            self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                          source="fetch",
                                          payload=CommandExecutedPayload(
                                              command=cmd or "")))
