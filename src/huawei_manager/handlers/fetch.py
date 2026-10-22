"""Fetch mixin — command output retrieval (info).

``_fetch_config`` migrou para ``tabs/config/`` (F2-config).
``_fetch_route`` migrou para ``tabs/route/`` (F2-route).
``_fetch_arp`` migrou para ``tabs/arp/`` (F2-arp).
"""

from __future__ import annotations

import io
import logging

from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.exceptions import SdnError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload

log = logging.getLogger(__name__)


class FetchMixin:
    """Mixin com metodos de fetch de dados do roteador."""

    # ══════════════════════════════════════════════════════════════════
    #  FETCH METHODS
    # ══════════════════════════════════════════════════════════════════
    def _fetch_info(self: AppCoreProtocol) -> None:
        """Coleta multiplas informacoes do sistema (versao, CPU, memoria, interfaces, LLDP)."""
        self._session_tracker.touch()
        self._loading(self.out_info, "Coletando informacoes do sistema\u2026")
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
                buf.write(f"{'=' * 70}\n\u25b6  {title}\n{'-' * 70}\n")
                buf.write(self._sb.send_command(cmd or ""))
                buf.write("\n\n")
        except SdnError as exc:
            self._sb.invalidate_connection()
            self._write(self.out_info, f"\u2718 Falha SSH: {exc}")
            return
        buf.write(f"{'=' * 70}\n\u25b6  Interfaces\n{'-' * 70}\n")
        intf_entries = self._drv.get_interfaces()
        if intf_entries:
            buf.write(f"{'Interface':<30} {'Status':<8} {'Protocolo'}\n")
            buf.write(f"{'-' * 50}\n")
            for e in intf_entries:
                buf.write(f"{e.name:<30} {e.status:<8} {e.protocol_status}\n")
        else:
            buf.write("(nenhuma interface encontrada)\n")
        buf.write("\n\n")
        self._write(self.out_info, buf.getvalue())
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="fetch",
                                    payload=CommandExecutedPayload(command="display version, interfaces, lldp, etc.")))
