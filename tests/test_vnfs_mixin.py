"""Testes de caracterização — congelam comportamento do VnfsMixin
antes da refatoração.

Alterações no VnfsMixin devem manter estes testes a passar.
Qt não é necessário — todos os mocks são MagicMock simples.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from _factories import make_vnf as _make_vnf
from huawei_manager.handlers.vnfs import VnfsMixin
from huawei_manager.sdn_controller.event_queue import EventType
from huawei_manager.services.vnf_service import SessionOverrides


def _make_vnf_service(returns=None):
    """Cria um mock de VnfService com métodos padrão."""
    svc = MagicMock()
    svc.set_target.return_value = SessionOverrides(
        host="10.0.0.1", port=22, username="admin",
        password="secret", ssh_key="",
    )
    svc.load_inventory.return_value = returns if returns is not None else []
    svc.probe_or_simulate.side_effect = lambda v, m: v
    svc.save_inventory.return_value = None
    svc.delete_device.return_value = ([MagicMock()], None)
    return svc


def _make_mixin(**attrs) -> VnfsMixin:
    """Cria um VnfsMixin com mock de atributos AppCoreProtocol."""
    mixin = VnfsMixin()
    defaults = dict(
        _target_vnf=None,
        _vnf_info_lbl=None,
        _vnf_target_lbl=MagicMock(),
        _vnf_status_lbl=None,
        _vnfs=[],
        _vnfs_lock=MagicMock(),
        _vnfs_gen=0,
        _mock_mode=True,
        _access_level="admin",
        _topo_canvas=None,
        _event_queue=MagicMock(),
        _sb=MagicMock(),
        session=MagicMock(),
        _controller=MagicMock(),
        _dispatch=lambda fn: fn(),
        _spawn_io=lambda fn, *args: None,
        _set_status=MagicMock(),
        _set_conn_btn=MagicMock(),
        _refresh_service_list=MagicMock(),
        _require_access=MagicMock(return_value=True),
        _vnf_service=_make_vnf_service(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


def _make_session_mock() -> MagicMock:
    """Cria um mock de sessão com atributos override."""
    session = MagicMock()
    session.override_host = None
    session.override_port = None
    session.override_username = None
    session.override_password = None
    session.override_ssh_key = None
    return session


# ══════════════════════════════════════════════════════════════════════════
#  _on_vnf_selected
# ══════════════════════════════════════════════════════════════════════════


class TestOnVnfSelected:
    """_on_vnf_selected define alvo e atualiza labels."""

    def test_sets_target_vnf(self):
        mixin = _make_mixin()
        vnf = _make_vnf()
        mixin._on_vnf_selected(vnf)
        assert mixin._target_vnf is vnf

    def test_updates_vnf_info_lbl_when_exists(self):
        info_lbl = MagicMock()
        mixin = _make_mixin(_vnf_info_lbl=info_lbl)
        vnf = _make_vnf(name="gw-01", host="10.0.0.1", port=22, username="admin")
        mixin._on_vnf_selected(vnf)
        info_lbl.setText.assert_called_once()
        called_arg = info_lbl.setText.call_args[0][0]
        assert "gw-01" in called_arg
        assert "10.0.0.1" in called_arg
        assert "admin" in called_arg

    def test_updates_vnf_target_lbl(self):
        target_lbl = MagicMock()
        mixin = _make_mixin(_vnf_target_lbl=target_lbl)
        vnf = _make_vnf(name="gw-01", host="10.0.0.1", port=22, username="admin")
        mixin._on_vnf_selected(vnf)
        target_lbl.setText.assert_called_once_with("gw-01 (10.0.0.1):22  user:admin")

    def test_calls_refresh_service_list(self):
        mixin = _make_mixin()
        mixin._on_vnf_selected(_make_vnf())
        mixin._refresh_service_list.assert_called_once()

    def test_skips_vnf_info_lbl_when_none(self):
        mixin = _make_mixin(_vnf_info_lbl=None)
        mixin._on_vnf_selected(_make_vnf())
        # Should not crash — no attribute access on None

    def test_limits_info_for_user_access(self):
        info_lbl = MagicMock()
        mixin = _make_mixin(_vnf_info_lbl=info_lbl, _access_level="user")
        vnf = _make_vnf(name="gw-01", host="10.0.0.1", port=22, username="admin")
        mixin._on_vnf_selected(vnf)
        info_lbl.setText.assert_called_once()
        called_arg = info_lbl.setText.call_args[0][0]
        assert "admin" not in called_arg  # user level does not show credentials


# ══════════════════════════════════════════════════════════════════════════
#  _clear_vnf_target
# ══════════════════════════════════════════════════════════════════════════


class TestClearVnfTarget:
    """_clear_vnf_target limpa alvo e publica evento se conectado."""

    def test_clears_target_vnf(self):
        mixin = _make_mixin(_target_vnf=_make_vnf())
        mixin._clear_vnf_target()
        assert mixin._target_vnf is None

    def test_clears_session_overrides(self):
        session = _make_session_mock()
        session.override_host = "10.0.0.1"
        session.override_port = 22
        mixin = _make_mixin(_target_vnf=_make_vnf(), session=session)
        mixin._clear_vnf_target()
        assert session.override_host is None
        assert session.override_port is None
        assert session.override_username is None
        assert session.override_password is None
        assert session.override_ssh_key is None

    def test_deselects_topo_canvas_when_exists(self):
        canvas = MagicMock()
        mixin = _make_mixin(_target_vnf=_make_vnf(), _topo_canvas=canvas)
        mixin._clear_vnf_target()
        canvas.deselect.assert_called_once()

    def test_skips_topo_canvas_when_none(self):
        mixin = _make_mixin(_target_vnf=_make_vnf(), _topo_canvas=None)
        mixin._clear_vnf_target()
        # Should not crash

    def test_updates_target_lbl(self):
        target_lbl = MagicMock()
        mixin = _make_mixin(_target_vnf=_make_vnf(), _vnf_target_lbl=target_lbl)
        mixin._clear_vnf_target()
        target_lbl.setText.assert_called_once_with("(roteador padrao)")

    def test_publishes_event_when_connected(self):
        sb = MagicMock()
        sb.is_alive.return_value = True
        eq = MagicMock()
        mixin = _make_mixin(_target_vnf=_make_vnf(), _sb=sb, _event_queue=eq)
        mixin._clear_vnf_target()
        eq.put.assert_called_once()
        event = eq.put.call_args[0][0]
        assert event.type == EventType.DEVICE_DISCONNECTED
        assert event.source == "vnf"
        assert event.payload is not None
        assert event.payload.reason == "target_cleared"

    def test_does_not_publish_event_when_disconnected(self):
        sb = MagicMock()
        sb.is_alive.return_value = False
        eq = MagicMock()
        mixin = _make_mixin(_target_vnf=_make_vnf(), _sb=sb, _event_queue=eq)
        mixin._clear_vnf_target()
        eq.put.assert_not_called()

    def test_disconnects_when_alive(self):
        sb = MagicMock()
        sb.is_alive.return_value = True
        mixin = _make_mixin(_target_vnf=_make_vnf(), _sb=sb)
        mixin._clear_vnf_target()
        sb.disconnect.assert_called_once()

    def test_skips_disconnect_when_not_alive(self):
        sb = MagicMock()
        sb.is_alive.return_value = False
        mixin = _make_mixin(_target_vnf=_make_vnf(), _sb=sb)
        mixin._clear_vnf_target()
        sb.disconnect.assert_not_called()

    def test_calls_refresh_service_list(self):
        mixin = _make_mixin(_target_vnf=_make_vnf())
        mixin._clear_vnf_target()
        mixin._refresh_service_list.assert_called_once()

    def test_clears_vnf_info_lbl_when_exists(self):
        info_lbl = MagicMock()
        mixin = _make_mixin(_target_vnf=_make_vnf(), _vnf_info_lbl=info_lbl)
        mixin._clear_vnf_target()
        info_lbl.setText.assert_called_once()
        assert "Nenhum VNF" in info_lbl.setText.call_args[0][0]


# ══════════════════════════════════════════════════════════════════════════
#  _refresh_vnfs
# ══════════════════════════════════════════════════════════════════════════


class TestRefreshVnfs:
    """_refresh_vnfs carrega inventário, faz probe e atualiza UI."""

    def test_loads_inventory(self):
        vnfs = [_make_vnf()]
        svc = _make_vnf_service(returns=vnfs)
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_vnfs_lock=lock, _vnf_service=svc)
        mixin._refresh_vnfs()
        assert mixin._vnfs_gen == 1

    def test_calls_simulate_in_mock_mode(self):
        svc = _make_vnf_service(returns=[])
        svc.save_inventory = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_vnfs_lock=lock, _mock_mode=True, _vnf_service=svc)
        mixin._refresh_vnfs()
        svc.probe_or_simulate.assert_called_once_with([], True)

    def test_calls_probe_in_non_mock_mode(self):
        svc = _make_vnf_service(returns=[])
        svc.save_inventory = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_vnfs_lock=lock, _mock_mode=False, _vnf_service=svc)
        mixin._refresh_vnfs()
        svc.probe_or_simulate.assert_called_once_with([], False)

    def test_dispatches_ui_update(self):
        svc = _make_vnf_service(returns=[])
        svc.save_inventory = MagicMock()
        dispatched: list[tuple] = []

        def fake_dispatch(fn):
            dispatched.append(fn)
            fn()

        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_vnfs_lock=lock, _dispatch=fake_dispatch, _vnf_service=svc)
        mixin._refresh_vnfs()
        # Should have dispatched _update_vnfs_ui and status label update
        assert len(dispatched) >= 1

    def test_skips_when_lock_not_available(self):
        lock = MagicMock()
        lock.acquire.return_value = False
        mixin = _make_mixin(_vnfs_lock=lock)
        mixin._refresh_vnfs()
        # Should return early — gen unchanged
        assert mixin._vnfs_gen == 0

    def test_releases_lock_in_finally(self):
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_vnfs_lock=lock)
        mixin._refresh_vnfs()
        lock.release.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
#  _delete_device
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteDevice:
    """_delete_device remove VNF e limpa target se necessário."""

    @staticmethod
    def _patch_msgbox():
        """PATCH: QMessageBox.question → Yes (evita Qt crash)."""
        import PySide6.QtWidgets as QW
        return MagicMock(return_value=QW.QMessageBox.StandardButton.Yes)

    def _make_delete_svc(self):
        """VnfService mock that records save_inventory calls."""
        svc = _make_vnf_service()
        svc.save_inventory = MagicMock()
        return svc

    def test_removes_vnf_from_inventory(self, monkeypatch):
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.question",
            self._patch_msgbox(),
        )
        vnf = _make_vnf(id="vnf-001")
        remaining = [_make_vnf(id="vnf-002")]
        svc = self._make_delete_svc()
        svc.delete_device.return_value = (remaining, vnf)
        lock = MagicMock()
        mixin = _make_mixin(_vnfs_lock=lock, _target_vnf=None, _vnf_service=svc)
        mixin._delete_device(vnf)
        svc.delete_device.assert_called_once_with(vnf.id, svc.load_inventory.return_value)
        # save_inventory is called internally by VnfService.delete_device(),
        # not by the mixin — no explicit assertion needed here

    def test_clears_target_if_deleted_vnf_is_target(self, monkeypatch):
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", self._patch_msgbox())
        target_vnf = _make_vnf(id="vnf-001", name="target-device")
        remaining = [_make_vnf(id="vnf-002")]
        svc = self._make_delete_svc()
        svc.delete_device.return_value = (remaining, target_vnf)
        lock = MagicMock()
        mixin = _make_mixin(_vnfs_lock=lock, _target_vnf=target_vnf, _vnf_service=svc)
        mixin._delete_device(target_vnf)
        assert mixin._target_vnf is None

    def test_increments_gen(self, monkeypatch):
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", self._patch_msgbox())
        svc = self._make_delete_svc()
        lock = MagicMock()
        mixin = _make_mixin(_vnfs_lock=lock, _vnfs_gen=5, _vnf_service=svc)
        mixin._delete_device(_make_vnf())
        assert mixin._vnfs_gen == 6

    def test_spawns_refresh(self, monkeypatch):
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", self._patch_msgbox())
        svc = self._make_delete_svc()
        spawned: list[tuple] = []

        def fake_spawn(fn, *args):
            spawned.append((fn, args))

        lock = MagicMock()
        mixin = _make_mixin(_vnfs_lock=lock, _spawn_io=fake_spawn, _vnf_service=svc)
        mixin._delete_device(_make_vnf())
        assert len(spawned) == 1
        assert spawned[0][0] == mixin._refresh_vnfs


# ══════════════════════════════════════════════════════════════════════════
#  _update_vnfs_ui
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateVnfsUi:
    """_update_vnfs_ui atualiza canvas e controller com lista de VNFs."""

    def test_sets_vnfs_attribute(self):
        mixin = _make_mixin()
        vnfs = [_make_vnf(), _make_vnf(id="vnf-002", name="other")]
        mixin._update_vnfs_ui(vnfs)
        assert mixin._vnfs is vnfs
        assert len(mixin._vnfs) == 2

    def test_calls_sync_from_vnfs(self):
        mixin = _make_mixin()
        vnfs = [_make_vnf()]
        mixin._update_vnfs_ui(vnfs)
        mixin._controller.sync_from_vnfs.assert_called_once_with(
            vnfs, publish_events=False
        )

    def test_calls_topo_canvas_update_vnfs(self):
        canvas = MagicMock()
        mixin = _make_mixin(_topo_canvas=canvas, _access_level="admin")
        vnfs = [_make_vnf()]
        mixin._update_vnfs_ui(vnfs)
        canvas.update_vnfs.assert_called_once_with(vnfs)

    def test_calls_set_access_on_canvas(self):
        canvas = MagicMock()
        mixin = _make_mixin(_topo_canvas=canvas, _access_level="tecnico")
        mixin._update_vnfs_ui([_make_vnf()])
        canvas.set_access.assert_called_once_with("tecnico")

    def test_skips_topo_canvas_when_none(self):
        mixin = _make_mixin(_topo_canvas=None)
        mixin._update_vnfs_ui([_make_vnf()])
        # Should not crash — no canvas calls


# ══════════════════════════════════════════════════════════════════════════
#  _show_device_dialog
# ══════════════════════════════════════════════════════════════════════════


class TestShowDeviceDialog:
    """_show_device_dialog abre DeviceDialog e processa resultado."""

    def test_calls_require_access(self):
        mixin = _make_mixin(_require_access=MagicMock(return_value=False))
        mixin._show_device_dialog()
        mixin._require_access.assert_called_once()

    def test_blocks_without_access(self):
        mixin = _make_mixin(_require_access=MagicMock(return_value=False))
        mixin._show_device_dialog()
        # Should return early — no dialog created

    def test_creates_dialog_with_vnf_types(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = False
        monkeypatch.setattr(
            "huawei_manager.handlers.vnfs.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        mixin._show_device_dialog()
        mock_dialog_cls.assert_called_once()
        call_kwargs = mock_dialog_cls.call_args
        vnf_types = (
            call_kwargs.kwargs.get("vnf_types")
            or call_kwargs[1].get("vnf_types", [])
        )
        assert "ROUTER" in vnf_types

    def test_creates_dialog_with_vnf_for_edit(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = False
        monkeypatch.setattr(
            "huawei_manager.handlers.vnfs.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        vnf = _make_vnf()
        mixin._show_device_dialog(vnf)
        call_kwargs = mock_dialog_cls.call_args
        assert (call_kwargs.kwargs.get("vnf") == vnf) or (
            call_kwargs[1].get("vnf") == vnf
        )

    def test_creates_dialog_without_vnf_for_add(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = False
        monkeypatch.setattr(
            "huawei_manager.handlers.vnfs.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        mixin._show_device_dialog()
        call_kwargs = mock_dialog_cls.call_args
        assert (call_kwargs.kwargs.get("vnf") is None) or (
            call_kwargs[1].get("vnf") is None
        )

    def test_on_accept_calls_add_device(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = True
        mock_dialog_cls.return_value.get_data.return_value = {"name": "new-vnf"}
        monkeypatch.setattr(
            "huawei_manager.handlers.vnfs.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        mixin._show_device_dialog()
        mixin._vnf_service.add_device.assert_called_once_with({"name": "new-vnf"})

    def test_on_accept_calls_update_device(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = True
        mock_dialog_cls.return_value.get_data.return_value = {"name": "updated"}
        monkeypatch.setattr(
            "huawei_manager.handlers.vnfs.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        vnf = _make_vnf()
        mixin._show_device_dialog(vnf)
        mixin._vnf_service.update_device.assert_called_once_with(
            vnf, {"name": "updated"}
        )

    def test_on_accept_calls_spawn_io_refresh(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = True
        mock_dialog_cls.return_value.get_data.return_value = {"name": "new"}
        monkeypatch.setattr(
            "huawei_manager.handlers.vnfs.DeviceDialog", mock_dialog_cls
        )
        spawned: list[tuple] = []

        def fake_spawn(fn, *args):
            spawned.append((fn, args))

        mixin = _make_mixin(_spawn_io=fake_spawn)
        mixin._show_device_dialog()
        assert len(spawned) == 1
        assert spawned[0][0] == mixin._refresh_vnfs
