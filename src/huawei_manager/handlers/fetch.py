"""Fetch mixin — command output retrieval (config, route, arp, info)."""

from __future__ import annotations

import io
import logging

from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.constants import CLI_FILTERS
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload

log = logging.getLogger(__name__)


class FetchMixin:
    """Mixin com metodos de fetch de dados do roteador."""

    # ══════════════════════════════════════════════════════════════════
    #  FETCH METHODS
    # ══════════════════════════════════════════════════════════════════
    def _fetch_config(self: AppCoreProtocol) -> None:
        """Busca a configuracao atual do roteador (display current-configuration)."""
        self._session_tracker.touch()
        self._loading(self.out_config, "Carregando configuracao atual\u2026")
        try:
            output = self._sb.send_command("display current-configuration")
        except RuntimeError:
            self._sb.invalidate_connection()
            return
        self._write(self.out_config, output)
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="fetch",
                                    payload=CommandExecutedPayload(command="display current-configuration")))

    def _fetch_route(self: AppCoreProtocol, fkey: str = "") -> None:
        """Busca a tabela de roteamento com o filtro selecionado.

        fkey deve ser extraido da UI (self._route_filter_cb) ANTES de
        chamar este metodo, pois ele roda na IO thread.
        """
        self._session_tracker.touch()
        assert fkey, "_fetch_route: fkey must be extracted in UI thread before calling"
        if fkey == "routing":
            try:
                entries = self._drv.get_routing_table()
            except RuntimeError:
                self._sb.invalidate_connection()
                return
            buf = io.StringIO()
            buf.write(f"{'Destino/Mask':<22} {'Proto':<10} {'Pre':>4} {'Custo':>6}  {'NextHop':<16} {'Interface'}\n")
            buf.write(f"{'-' * 72}\n")
            for e in entries:
                route = f"{e.destination}/{e.mask}"
                buf.write(f"{route:<22} {e.protocol:<10} {e.preference:>4} {e.cost:>6}"
                          f"  {e.next_hop:<16} {e.interface}\n")
            self._write(self.out_route, buf.getvalue())
            self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                        source="fetch",
                                        payload=CommandExecutedPayload(command="display ip routing-table")))
        else:
            cmd = CLI_FILTERS.get(fkey, "display ip routing-table")
            self._loading(self.out_route, f"Executando: {cmd}\u2026")
            try:
                route_out = self._sb.send_command(cmd or "")
            except RuntimeError:
                self._sb.invalidate_connection()
                return
            self._write(self.out_route, route_out)
            self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                        source="fetch",
                                        payload=CommandExecutedPayload(command=cmd or "")))

    def _fetch_arp(self: AppCoreProtocol) -> None:
        """Busca a tabela ARP do roteador."""
        self._session_tracker.touch()
        try:
            entries = self._drv.get_arp_table()
        except RuntimeError:
            self._sb.invalidate_connection()
            return
        buf = io.StringIO()
        buf.write(f"{'IP Address':<18} {'MAC Address':<20} {'Tipo':<6} {'Interface'}\n")
        buf.write(f"{'-' * 60}\n")
        for e in entries:
            buf.write(f"{e.ip_address:<18} {e.mac_address:<20} {e.status:<6} {e.interface}\n")
        self._write(self.out_arp, buf.getvalue())
        self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                    source="fetch",
                                    payload=CommandExecutedPayload(command="display arp")))

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
        except RuntimeError:
            self._sb.invalidate_connection()
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
