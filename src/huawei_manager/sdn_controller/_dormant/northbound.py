"""Northbound API — Facade interno consumido pela GUI.

Fornece pontos de acesso padronizados para o ControllerCore, EventQueue,
e Southbound, com verificacao de RBAC em cada endpoint.

Cada metodo retorna um ``ApiResponse`` — nunca levanta excecoes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from huawei_manager.audit_log import AuditLogger
from huawei_manager.sdn_controller.authz import Role
from huawei_manager.sdn_controller.core import ControllerCore
from huawei_manager.sdn_controller.event_queue import EventQueue


@dataclass
class ApiResponse:
    """Resposta padronizada da API.

    Attributes:
        success: True se a operacao foi bem-sucedida.
        data: Payload da resposta (opcional).
        error: Mensagem de erro (opcional, presente apenas se success=False).
    """

    success: bool = True
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Converte para dict serializavel."""
        return {"success": self.success, "data": self.data, "error": self.error}


# Niveis minimos de acesso por endpoint
_REQUIRED_ROLES: dict[str, Role] = {
    "get_devices": Role.USER,
    "get_topology": Role.USER,
    "get_events": Role.USER,
    "get_config": Role.USER,
    "deploy_intent": Role.TECNICO,
    "get_policies": Role.USER,
    "get_audit_log": Role.TECNICO,
}


class NorthboundAPI:
    """Facade interno para operacoes SDN.

    Args:
        controller: Instancia de ``ControllerCore`` (obrigatorio).
        event_queue: Instancia de ``EventQueue`` (obrigatorio).
        audit_logger: Instancia de ``AuditLogger`` (obrigatorio).
        sb: Instancia opcional de Southbound para comandos/config.
    """

    def __init__(
        self,
        controller: ControllerCore,
        event_queue: EventQueue,
        audit_logger: AuditLogger,
        sb: Any | None = None,
    ) -> None:
        if controller is None:
            raise TypeError("controller is required")
        self._controller = controller
        self._event_queue = event_queue
        self._audit_logger = audit_logger
        self._sb = sb

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _check_role(required: Role, current: str) -> str | None:
        """Verifica se a role atual atende ao minimo exigido.

        Returns:
            None se permitido, string de erro caso contrario.
        """
        try:
            current_enum = Role.from_string(current)
        except ValueError:
            return f"Unknown role: {current!r}"
        if current_enum.hierarchy < required.hierarchy:
            return (
                f"Permission denied: requires {required.value}, "
                f"got {current}"
            )
        return None

    @staticmethod
    def _ok(data: Any = None) -> ApiResponse:
        return ApiResponse(success=True, data=data)

    @staticmethod
    def _err(message: str) -> ApiResponse:
        return ApiResponse(success=False, error=message)

    def _get_device_state(self, device_id: str) -> dict | None:
        """Retorna o estado de um dispositivo como dict, ou None."""
        state = self._controller.get_state(device_id)
        if state is None:
            return None
        return state.to_dict()

    def _require_endpoint(self, endpoint: str, role: str) -> str | None:
        """Verifica role para um endpoint especifico."""
        required = _REQUIRED_ROLES.get(endpoint, Role.USER)
        return self._check_role(required, role)

    # ── Endpoints ─────────────────────────────────────────────────────────

    def get_devices(self, role: str = "user") -> ApiResponse:
        """Retorna lista de todos os dispositivos registrados."""
        err = self._require_endpoint("get_devices", role)
        if err:
            return self._err(err)
        try:
            ids = self._controller.list_devices()
            result = [self._get_device_state(dev_id) for dev_id in ids]
            return self._ok([d for d in result if d is not None])
        except Exception as e:
            return self._err(str(e))

    def get_topology(self, role: str = "user") -> ApiResponse:
        """Retorna dados de topologia."""
        err = self._require_endpoint("get_topology", role)
        if err:
            return self._err(err)
        try:
            ids = self._controller.list_devices()
            devices = [self._get_device_state(dev_id) for dev_id in ids]
            return self._ok({
                "devices": [d for d in devices if d is not None],
                "total": len(ids),
            })
        except Exception as e:
            return self._err(str(e))

    def get_events(
        self, role: str = "user", limit: int = 50
    ) -> ApiResponse:
        """Retorna eventos recentes da fila."""
        err = self._require_endpoint("get_events", role)
        if err:
            return self._err(err)
        try:
            events = self._event_queue.poll(timeout=0.1)
            result = [
                {
                    "type": e.type.name,
                    "source": e.source,
                    "priority": e.priority,
                    "timestamp": e.timestamp.isoformat(),
                    "data": e.data,
                }
                for e in events[:limit]
            ]
            return self._ok(result)
        except Exception as e:
            return self._err(str(e))

    def get_config(
        self, device_id: str, role: str = "user"
    ) -> ApiResponse:
        """Retorna configuracao de um dispositivo."""
        err = self._require_endpoint("get_config", role)
        if err:
            return self._err(err)
        state = self._get_device_state(device_id)
        if state is None:
            return self._err(f"Device not found: {device_id}")
        if self._sb is None or not self._sb.is_alive():
            return self._ok({
                "device_id": device_id,
                "config": "(southbound not available)",
            })
        try:
            raw = self._sb.send_command("display current-configuration")
            return self._ok({"device_id": device_id, "config": raw})
        except Exception as e:
            return self._err(f"Config fetch failed: {e}")

    def deploy_intent(
        self,
        device_id: str,
        config: str,
        role: str = "user",
    ) -> ApiResponse:
        """Aplica configuracao em um dispositivo."""
        err = self._require_endpoint("deploy_intent", role)
        if err:
            return self._err(err)
        state = self._get_device_state(device_id)
        if state is None:
            return self._err(f"Device not found: {device_id}")
        if self._sb is None or not self._sb.is_alive():
            return self._err("Southbound not available")
        try:
            lines = config.strip().split("\n")
            ok, message = self._sb.send_config(lines)
            if ok:
                return self._ok({
                    "device_id": device_id,
                    "message": message,
                })
            return self._err(f"Deploy failed: {message}")
        except Exception as e:
            return self._err(f"Deploy error: {e}")

    def get_policies(self, role: str = "user") -> ApiResponse:
        """Retorna lista de politicas (stub para M14-M15)."""
        err = self._require_endpoint("get_policies", role)
        if err:
            return self._err(err)
        return self._ok([])

    def get_audit_log(
        self, role: str = "user", limit: int = 100
    ) -> ApiResponse:
        """Retorna entradas recentes do log de auditoria."""
        err = self._require_endpoint("get_audit_log", role)
        if err:
            return self._err(err)
        try:
            entries = self._audit_logger.tail(limit)
            return self._ok(entries)
        except Exception as e:
            return self._err(f"Audit log error: {e}")
