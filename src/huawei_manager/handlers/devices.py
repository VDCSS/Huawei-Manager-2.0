"""Devices mixin — ponte fina entre AppCore (UI+eventos) e DeviceService (dominio)."""
from __future__ import annotations

import logging

import huawei_manager.constants as C
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.device_models import Device
from huawei_manager.sdn_controller.authz import role_meets
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import DeviceDisconnectedPayload
from huawei_manager.widgets.device_dialog import DeviceDialog

log = logging.getLogger(__name__)


class DevicesMixin:
    def _refresh_devices(self: AppCoreProtocol) -> None:
        lock = self._devices_lock
        if lock is not None and not lock.acquire(blocking=False):
            return
        try:
            devices = self._device_service.load_inventory()
            if not devices:
                log.warning("_refresh_devices: load_inventory retornou 0 devices")
            devices = self._device_service.probe_or_simulate(devices, self._mock_mode)
            try:
                self._device_service.save_inventory(devices)
            except Exception as exc:
                log.error(
                    "_refresh_devices: falha ao salvar inventario (mantendo "
                    "estado em memoria): %s", exc,
                )
            self._devices_gen += 1
            self._dispatch(lambda: self._update_devices_ui(devices))
        finally:
            if lock is not None:
                lock.release()

    def _update_devices_ui(self: AppCoreProtocol, devices: list[Device]) -> None:
        self._devices = devices
        self._controller.sync_from_devices(devices, publish_events=False)
        if self._topo_canvas is not None:
            self._topo_canvas.set_access(self._access_level)
            self._topo_canvas.update_devices(devices)
        if self._device_status_lbl is not None:
            self._device_status_lbl.setText(f"Invent\u00e1rio: {len(devices)} devices")

    def _show_device_dialog(self: AppCoreProtocol, device: Device | None = None) -> None:
        if not self._require_access("tecnico"):
            return
        dialog = DeviceDialog(
            parent=None,
            device=device,
            device_types=["ROUTER", "SWITCH", "FIREWALL", "LOAD-BALANCER",
                          "WAN-ACCEL", "AP"],
        )
        if dialog.exec():
            data = dialog.get_data()
            if device is not None:
                self._device_service.update_device(device, data)
            else:
                self._device_service.add_device(data)
            self._spawn_io(self._refresh_devices)

    def _delete_device(self: AppCoreProtocol, device: Device) -> None:
        if not self._require_access("tecnico"):
            return
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            None, "Excluir",
            f"Confirmar exclusao de {device.name} ({device.host})?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        devices = self._device_service.load_inventory()
        remaining, removed = self._device_service.delete_device(device.id, devices)
        if removed is not None and self._target_device is not None:
            if self._target_device.id == removed.id:
                self._clear_device_target()
        self._devices_gen += 1
        self._spawn_io(self._refresh_devices)

    def _on_device_selected(self: AppCoreProtocol, device: Device) -> None:
        self._target_device = device
        overrides = self._device_service.set_target(device)
        if overrides.host:
            self.session.override_host = overrides.host
        if overrides.port:
            self.session.override_port = overrides.port
        if overrides.username:
            self.session.override_username = overrides.username
        if overrides.password:
            self.session.override_password = overrides.password
        if overrides.ssh_key:
            self.session.override_ssh_key = overrides.ssh_key
        info = f"{device.name} ({device.host})"
        if role_meets(self._access_level, "tecnico"):
            info += f":{device.port}"
        if role_meets(self._access_level, "tecnico") and device.username:
            info += f"  user:{device.username}"
        if self._device_info_lbl is not None:
            self._device_info_lbl.setText(f"  Selecionado: {info}")
        if self._device_target_lbl is not None:
            self._device_target_lbl.setText(info)
        self._refresh_service_list()

    def _clear_device_target(self: AppCoreProtocol) -> None:
        self._target_device = None
        self.session.override_host = None
        self.session.override_port = None
        self.session.override_username = None
        self.session.override_password = None
        self.session.override_ssh_key = None
        if self._topo_canvas is not None:
            self._topo_canvas.deselect()
        self._device_target_lbl.setText("(roteador padrao)")
        if self._device_info_lbl is not None:
            self._device_info_lbl.setText("  Nenhum device selecionado")
        if self._sb.is_alive():
            self._sb.disconnect()
            self._set_status("Desconectado", C.NEON_RED)
            self._set_conn_btn()
            self._event_queue.put(Event(EventType.DEVICE_DISCONNECTED,
                                        source="device",
                                        payload=DeviceDisconnectedPayload(reason="target_cleared")))
        self._refresh_service_list()
