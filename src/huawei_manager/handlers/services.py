"""Services mixin — service execution handler."""

from __future__ import annotations

import logging
import re

from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.services import ServiceDef, execute_service

log = logging.getLogger(__name__)


class ServicesMixin:
    """Mixin com metodos de execucao de servicos."""

    # ══════════════════════════════════════════════════════════════════
    #  SERVICOS
    # ══════════════════════════════════════════════════════════════════
    def _run_service(self: AppCoreProtocol, svc: ServiceDef) -> None:
        """Executa um servico no modo mock ou cli, com substituicao de parametros e sanitizacao."""
        mode = self._svc_mode_var
        vnf = self._target_vnf
        label = f"Servico: {svc.name}  |  Modo: {mode}"
        if vnf:
            label += f"  |  Alvo: {vnf.name} ({vnf.host})"
        self._svc_vnf_lbl.setText(label)

        _REJECT_PARAM = re.compile(r"[;&|`$(){}]")

        final_svc = svc
        if svc.config_mode and self._svc_param_entries:
            cmd = svc.description
            for name, entry in self._svc_param_entries.items():
                val = entry.text().strip()
                if _REJECT_PARAM.search(val):
                    self._write(self._svc_output,
                        f"\u2718  Parametro '{name}' contem caracteres invalidos "
                        f"(& ; | ` $ ( ) {{ }}).")
                    return
                cmd = cmd.replace(f"<{name}>", val)
            final_svc = ServiceDef(
                id=svc.id, name=svc.name, description=svc.description,
                category=svc.category, vnf_types=svc.vnf_types,
                cli_commands=[cmd],
                config_mode=svc.config_mode,
            )

        def _do():
            """Executa o servico selecionado (mock ou SSH real)."""
            self._loading(self._svc_output, f"Executando: {svc.name} ({mode})\u2026")

            if mode == "mock":
                result = execute_service(final_svc, session_type="mock")
                self._write(self._svc_output, result)
                self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                            source="service",
                                            payload=CommandExecutedPayload(
                                                command=svc.name,
                                                data={"mode": "mock"},
                                            )))
                return

            if not self._sb.is_alive():
                self._write(self._svc_output,
                    "\u2718  Sem sessao SSH ativa. Conecte-se primeiro.")
                return

            if mode == "cli":
                result = self._sb.send_service_commands(
                    final_svc.cli_commands,
                    config_mode=final_svc.config_mode,
                    requires_privilege=final_svc.requires_privilege,
                )
                self._write(self._svc_output, result)
                self._event_queue.put(Event(EventType.COMMAND_EXECUTED,
                                            source="service",
                                            payload=CommandExecutedPayload(
                                                command=svc.name,
                                                data={"mode": "cli"},
                                            )))
                return

            self._write(self._svc_output, f"Modo desconhecido: {mode}")

        self._spawn_io(_do)
