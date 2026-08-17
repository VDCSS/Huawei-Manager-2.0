"""SSH mixin — connect / disconnect helpers."""

from __future__ import annotations

import logging

from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.device_models import Device
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import (
    DeviceConnectedPayload,
    DeviceDisconnectedPayload,
)

log = logging.getLogger(__name__)


class SshMixin:
    """Mixin com metodos de conexao SSH."""

    def _get_selected_device(self: AppCoreProtocol) -> Device | None:
        return (self._topo_canvas.get_selected()
                if self._topo_canvas else None) or self._target_device

    def _toggle_connect(self: AppCoreProtocol) -> None:
        if self._sb.is_alive():
            self._sb.disconnect()
            self._set_status("Desconectado", C.NEON_PURP)
            self._set_conn_btn()
            device = self._get_selected_device()
            device_id = device.id if device else "user"
            self._event_queue.put(Event(EventType.DEVICE_DISCONNECTED,
                                        source=device_id,
                                        payload=DeviceDisconnectedPayload(reason="manual")))
            return

        device = self._get_selected_device()
        if device:
            self._connect_with_device(device)
        else:
            self._connect_default()

    def _do_connect(self: AppCoreProtocol, on_success_fmt: str, on_error_msg: str) -> None:
        self._session_tracker.touch()

        def _do():
            try:
                self._sb.connect()
                sid = self.session._session_id or "?"
                self._dispatch(lambda: self._set_status(
                    on_success_fmt.format(sid=sid), C.NEON_CYAN))
                self._set_conn_btn("  DESCONECTAR  ")
                device = self._get_selected_device()
                device_id = device.id if device else "user"
                self._event_queue.put(Event(EventType.DEVICE_CONNECTED,
                                            source=device_id,
                                            payload=DeviceConnectedPayload(
                                                host=self.session.override_host or "",
                                                session_id=sid,
                                            )))
            except NetmikoAuthenticationException:
                self._dispatch(lambda: self._set_status(
                    "Falha de autenticacao", C.NEON_AMBER))
                self._set_conn_btn()
            except NetmikoTimeoutException:
                self._dispatch(lambda: self._set_status(
                    "Timeout de conexao", C.NEON_AMBER))
                self._set_conn_btn()
            except ValueError as exc:
                msg = f"Config: {exc}"
                self._dispatch(lambda: self._set_status(msg, C.NEON_AMBER))
                self._set_conn_btn()
            except SdnValidationError as exc:
                msg = f"Config: {exc}"
                self._dispatch(lambda: self._set_status(msg, C.NEON_AMBER))
                self._set_conn_btn()
            except Exception as exc:
                log.exception("Falha inesperada em _do_connect: %s", exc)
                self._dispatch(lambda: self._set_status(
                    on_error_msg, C.NEON_AMBER))
                self._set_conn_btn()

        self._spawn_io(_do)

    def _connect_default(self: AppCoreProtocol) -> None:
        self._set_status("Conectando SSH\u2026", C.NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect("SSH \u2714  {sid}", "Erro ao conectar")

    def _connect_with_device(self: AppCoreProtocol, device: Device) -> None:
        if self._sb.is_alive():
            self._sb.disconnect()
        self.session.override_host = device.host
        self.session.override_port = device.port
        self.session.override_username = device.username or None
        self.session.override_password = device.password or None
        self.session.override_ssh_key = device.ssh_key or None
        self._set_status(f"Conectando ao device {device.name}\u2026", C.NEON_AMBER)
        self._set_conn_btn(disabled=True)
        self._do_connect(f"Device \u2714  {device.name}  {{sid}}", "Erro ao conectar ao device")
