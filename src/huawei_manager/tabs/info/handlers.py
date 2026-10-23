"""Handler da aba Info do Sistema — coleta multipla via SSH + driver.

Extraído de ``handlers/fetch.py`` (``FetchMixin._fetch_info``, F2-info
do plano ``plano-abas-independentes.md``): a classe injetada
:class:`InfoHandlers` ``(ctx, state)`` lê só o :class:`TabContext`.
``_fetch_info`` era o último método do FetchMixin — o mixin legado foi
removido junto com ``handlers/fetch.py``.
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
    from huawei_manager.tabs.info.state import InfoState


class InfoHandlers:
    """Coleta de informações do sistema (roda na IO thread via ctx.run)."""

    def __init__(self, ctx: TabContext, state: InfoState) -> None:
        self._ctx = ctx
        self._state = state

    def fetch_info(self) -> None:
        """Coleta multiplas informacoes do sistema (versao, CPU, memoria, interfaces, LLDP)."""
        self._ctx.touch_session()
        out = self._state.out
        dispatch = self._ctx.dispatch
        _ui.loading(out, "Coletando informacoes do sistema…", dispatch)
        buf = io.StringIO()
        commands = [
            ("Versao / Sistema", "display version"),
            ("Dispositivo", "display device"),
            ("Licenca", "display license"),
            ("CPU", "display cpu-usage"),
            ("Memoria", "display memory-usage"),
            ("LLDP", "display lldp neighbor brief"),
        ]
        try:
            for title, cmd in commands:
                buf.write(f"{'=' * 70}\n▶  {title}\n{'-' * 70}\n")
                buf.write(self._ctx.sb.send_command(cmd or ""))
                buf.write("\n\n")
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(out, f"✘ Falha SSH: {exc}", dispatch)
            return
        buf.write(f"{'=' * 70}\n▶  Interfaces\n{'-' * 70}\n")
        intf_entries = self._ctx.drv().get_interfaces()
        if intf_entries:
            buf.write(f"{'Interface':<30} {'Status':<8} {'Protocolo'}\n")
            buf.write(f"{'-' * 50}\n")
            for e in intf_entries:
                buf.write(f"{e.name:<30} {e.status:<8} {e.protocol_status}\n")
        else:
            buf.write("(nenhuma interface encontrada)\n")
        buf.write("\n\n")
        _ui.write(out, buf.getvalue(), dispatch)
        self._ctx.event_bus.put(Event(EventType.COMMAND_EXECUTED,
                                      source="fetch",
                                      payload=CommandExecutedPayload(
                                          command="display version, interfaces, lldp, etc.")))
