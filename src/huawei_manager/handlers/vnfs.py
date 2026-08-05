"""VNF mixin — ponte fina entre AppCore (UI+eventos) e VnfService (domínio).

Delega toda a lógica de CRUD, probe e target para VnfService.
A UI (formulário) foi extraída para DeviceDialog.
"""
from __future__ import annotations

import logging

from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import DeviceDisconnectedPayload
from huawei_manager.vnf_models import VNF
from huawei_manager.widgets.device_dialog import DeviceDialog

log = logging.getLogger(__name__)


class VnfsMixin:
    """Ponte fina entre AppCore (UI+eventos) e VnfService (domínio)."""

    def _init_topology_backend(self: AppCoreProtocol) -> None:
        self._dispatch(lambda: None)  # kept for compat — no-op

    def _refresh_vnfs(self: AppCoreProtocol) -> None:
        """Recarrega inventário, faz probe/simula e atualiza a UI."""
        lock = self._vnfs_lock
        if lock is not None and not lock.acquire(blocking=False):
            return
        try:
            vnfs = self._vnf_service.load_inventory()
            if not vnfs:
                log.warning("_refresh_vnfs: load_inventory retornou 0 VNFs")
            vnfs = self._vnf_service.probe_or_simulate(vnfs, self._mock_mode)
            self._vnf_service.save_inventory(vnfs)
            self._vnfs_gen += 1
            self._dispatch(lambda: self._update_vnfs_ui(vnfs))
        finally:
            if lock is not None:
                lock.release()

    def _update_vnfs_ui(self: AppCoreProtocol, vnfs: list[VNF]) -> None:
        """Atualiza o canvas de topologia com a nova lista de VNFs."""
        self._vnfs = vnfs
        self._controller.sync_from_vnfs(vnfs, publish_events=False)
        if self._topo_canvas is not None:
            self._topo_canvas.set_access(self._access_level)
            self._topo_canvas.update_vnfs(vnfs)

    def _show_device_dialog(self: AppCoreProtocol, vnf: VNF | None = None) -> None:
        """Abre DeviceDialog para cadastrar ou editar um VNF."""
        if not self._require_access():
            return
        dialog = DeviceDialog(
            parent=None,
            vnf=vnf,
            vnf_types=["ROUTER", "SWITCH", "FIREWALL", "LOAD-BALANCER",
                        "WAN-ACCEL", "AP"],
        )
        if dialog.exec():
            data = dialog.get_data()
            if vnf is not None:
                self._vnf_service.update_device(vnf, data)
            else:
                self._vnf_service.add_device(data)
            self._spawn_io(self._refresh_vnfs)

    def _delete_device(self: AppCoreProtocol, vnf: VNF) -> None:
        """Remove um VNF do inventário após confirmação."""
        if not self._require_access():
            return
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            None, "Excluir",
            f"Confirmar exclusao de {vnf.name} ({vnf.host})?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        vnfs = self._vnf_service.load_inventory()
        remaining, removed = self._vnf_service.delete_device(vnf.id, vnfs)
        if removed is not None and self._target_vnf is not None:
            if self._target_vnf.id == removed.id:
                self._clear_vnf_target()
        self._vnfs_gen += 1
        self._spawn_io(self._refresh_vnfs)

    def _on_vnf_selected(self: AppCoreProtocol, vnf: VNF) -> None:
        """Atualiza o alvo SSH ao selecionar um VNF no canvas."""
        self._target_vnf = vnf
        overrides = self._vnf_service.set_target(vnf)
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
        info = f"{vnf.name} ({vnf.host})"
        if self._access_level in ("admin", "tecnico"):
            info += f":{vnf.port}"
        if self._access_level in ("admin", "tecnico") and vnf.username:
            info += f"  user:{vnf.username}"
        if self._vnf_info_lbl is not None:
            self._vnf_info_lbl.setText(f"  Selecionado: {info}")
        if self._vnf_target_lbl is not None:
            self._vnf_target_lbl.setText(info)
        self._refresh_service_list()

    def _clear_vnf_target(self: AppCoreProtocol) -> None:
        """Limpa o alvo VNF e volta ao roteador padrão."""
        self._target_vnf = None
        self.session.override_host = None
        self.session.override_port = None
        self.session.override_username = None
        self.session.override_password = None
        self.session.override_ssh_key = None
        if self._topo_canvas is not None:
            self._topo_canvas.deselect()
        self._vnf_target_lbl.setText("(roteador padrao)")
        if self._vnf_info_lbl is not None:
            self._vnf_info_lbl.setText("  Nenhum VNF selecionado")
        if self._sb.is_alive():
            self._sb.disconnect()
            self._set_status("Desconectado")
            self._set_conn_btn()
            self._event_queue.put(Event(EventType.DEVICE_DISCONNECTED,
                                        source="vnf",
                                        payload=DeviceDisconnectedPayload(reason="target_cleared")))
        self._refresh_service_list()
