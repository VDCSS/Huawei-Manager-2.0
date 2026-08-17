"""Services mixin — service execution handler."""

from __future__ import annotations

import logging
import re

from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.sdn_controller.validator import _DEFAULT_DENY_PATTERNS
from huawei_manager.services import ServiceDef, execute_service

log = logging.getLogger(__name__)


def _template_to_pattern(tpl: str) -> re.Pattern[str]:
    """Converte um template de serviço em regex de allowlist.

    Placeholders ``<x>`` viram ``.+`` (aceitam valores multi-word, ex.:
    ``description <text>``); o texto literal é escapado.
    O template pode conter ``|`` como alternância de comandos possíveis
    (ex.: ``"shutdown | undo shutdown"``).
    """
    parts: list[str] = []
    pos = 0
    for m in re.finditer(r"<[^>]*>", tpl):
        parts.append(re.escape(tpl[pos:m.start()]))
        parts.append(r".+")
        pos = m.end()
    parts.append(re.escape(tpl[pos:]))
    return re.compile(r"^" + "".join(parts) + r"\s*$", re.IGNORECASE)


def _build_service_allow_patterns(svc: ServiceDef) -> list[re.Pattern[str]]:
    """Monta a allowlist a partir do template (description) e comandos concretos."""
    patterns: list[re.Pattern[str]] = []
    for tpl in [svc.description, *svc.cli_commands]:
        for alt in tpl.split("|"):
            alt = alt.strip()
            if alt:
                patterns.append(_template_to_pattern(alt))
    return patterns


class ServicesMixin:
    """Mixin com metodos de execucao de servicos."""

    # ══════════════════════════════════════════════════════════════════
    #  SERVICOS
    # ══════════════════════════════════════════════════════════════════
    def _run_service(self: AppCoreProtocol, svc: ServiceDef,
                     final_svc: ServiceDef | None = None) -> None:
        """Executa um servico no modo mock ou cli, com substituicao de parametros e sanitizacao."""
        _DENY_COMPILED = [re.compile(p, re.IGNORECASE)
                          for p in _DEFAULT_DENY_PATTERNS]
        _DENY_COMPILED = _DENY_COMPILED + [
            re.compile(r"^shutdown(?:\s|$)", re.IGNORECASE)]
        prova_cmds = [final_svc.cli_commands] if final_svc else [svc.cli_commands]
        destrutivo = svc.config_mode and any(
            p.search(cmd) for cmds in prova_cmds for cmd in cmds
            for p in _DENY_COMPILED
        )
        if destrutivo:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                None, "Confirmar operação destrutiva",
                f"O serviço '{svc.name}' executa: {chr(10).join(svc.cli_commands)}\n\n"
                "Continuar?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._write(self._svc_output, "Operação cancelada pelo usuário.")
                return

        mode = self._svc_mode_var
        device = self._target_device
        label = f"Servico: {svc.name}  |  Modo: {mode}"
        if device:
            label += f"  |  Alvo: {device.name} ({device.host})"
        self._svc_device_lbl.setText(label)

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
                category=svc.category, device_types=svc.device_types,
                cli_commands=[cmd],
                config_mode=svc.config_mode,
            )

        rejected = self._validate_service(svc, final_svc.cli_commands)
        if rejected:
            for cmd, reason in rejected:
                self._write(self._svc_output,
                            f"\u2718  Comando bloqueado ({reason}): {cmd}")
            logger = getattr(self, "audit_logger", None)
            if logger is not None:
                session = getattr(self, "session", None)
                logger.log_operation(
                    "command_denied",
                    user=getattr(session, "_user", "unknown"),
                    host=getattr(session, "_host", "unknown"),
                    status="blocked",
                    service=svc.name,
                    rejected=[c for c, _ in rejected],
                )
            return

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

    def _validate_service(self: AppCoreProtocol, svc: ServiceDef,
                          final_cmds: list[str]) -> list[tuple[str, str]]:
        """Valida comandos finais do serviço contra allowlist e deny-list.

        Args:
            svc: Definição do serviço (template + comandos concretos).
            final_cmds: Comandos finais pós-substituição de parâmetros.

        Returns:
            Lista de ``(cmd, reason)`` rejeitados; vazia = todos ok.
        """
        allow_patterns = _build_service_allow_patterns(svc)
        deny_patterns = [re.compile(p, re.IGNORECASE)
                         for p in _DEFAULT_DENY_PATTERNS]
        rejected: list[tuple[str, str]] = []
        for c in final_cmds:
            allowed = any(p.search(c) for p in allow_patterns)
            denied = any(p.search(c) for p in deny_patterns)
            if denied or not allowed:
                rejected.append((c, "destrutivo" if denied
                                 else "fora do template do serviço"))
        return rejected
