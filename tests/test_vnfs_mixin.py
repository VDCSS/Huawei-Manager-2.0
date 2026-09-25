"""Testes de caracterização — congelam comportamento do DevicesMixin
antes da refatoração.

Alterações no DevicesMixin devem manter estes testes a passar.
Qt não é necessário — todos os mocks são MagicMock simples.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from ._factories import make_device as _make_device

from huawei_manager.handlers.devices import DevicesMixin
from huawei_manager.sdn_controller.event_queue import EventType
from huawei_manager.services.device_service import SessionOverrides


def _make_device_service(returns=None):
    """Cria um mock de DeviceService com métodos padrão."""
    svc = MagicMock()
    svc.set_target.return_value = SessionOverrides(
        host="10.0.0.1", port=22, username="admin",
        password="secret", ssh_key="",
    )
    svc.load_inventory.return_value = returns if returns is not None else []
    svc.probe_or_simulate.side_effect = lambda d, m: d
    svc.save_inventory.return_value = None
    svc.delete_device.return_value = ([MagicMock()], None)
    return svc


def _make_mixin(**attrs) -> DevicesMixin:
    """Cria um DevicesMixin com mock de atributos AppCoreProtocol."""
    mixin = DevicesMixin()
    defaults = dict(
        _target_device=None,
        _device_info_lbl=None,
        _device_target_lbl=MagicMock(),
        _device_status_lbl=None,
        _devices=[],
        _devices_lock=MagicMock(),
        _devices_gen=0,
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
        _device_service=_make_device_service(),
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
#  _on_device_selected
# ══════════════════════════════════════════════════════════════════════════


class TestOnDeviceSelected:
    """_on_device_selected define alvo e atualiza labels."""

    def test_sets_target_device(self):
        mixin = _make_mixin()
        device = _make_device()
        mixin._on_device_selected(device)
        assert mixin._target_device is device

    def test_updates_device_info_lbl_when_exists(self):
        info_lbl = MagicMock()
        mixin = _make_mixin(_device_info_lbl=info_lbl)
        device = _make_device(name="gw-01", host="10.0.0.1", port=22, username="admin")
        mixin._on_device_selected(device)
        info_lbl.setText.assert_called_once()
        called_arg = info_lbl.setText.call_args[0][0]
        assert "gw-01" in called_arg
        assert "10.0.0.1" in called_arg
        assert "admin" in called_arg

    def test_updates_device_target_lbl(self):
        target_lbl = MagicMock()
        mixin = _make_mixin(_device_target_lbl=target_lbl)
        device = _make_device(name="gw-01", host="10.0.0.1", port=22, username="admin")
        mixin._on_device_selected(device)
        target_lbl.setText.assert_called_once_with("gw-01 (10.0.0.1):22  user:admin")

    def test_calls_refresh_service_list(self):
        mixin = _make_mixin()
        mixin._on_device_selected(_make_device())
        mixin._refresh_service_list.assert_called_once()

    def test_skips_device_info_lbl_when_none(self):
        mixin = _make_mixin(_device_info_lbl=None)
        mixin._on_device_selected(_make_device())
        # Should not crash — no attribute access on None

    def test_limits_info_for_user_access(self):
        info_lbl = MagicMock()
        mixin = _make_mixin(_device_info_lbl=info_lbl, _access_level="user")
        device = _make_device(name="gw-01", host="10.0.0.1", port=22, username="admin")
        mixin._on_device_selected(device)
        info_lbl.setText.assert_called_once()
        called_arg = info_lbl.setText.call_args[0][0]
        assert "admin" not in called_arg  # user level does not show credentials


# ══════════════════════════════════════════════════════════════════════════
#  _clear_device_target
# ══════════════════════════════════════════════════════════════════════════


class TestClearDeviceTarget:
    """_clear_device_target limpa alvo e publica evento se conectado."""

    def test_clears_target_device(self):
        mixin = _make_mixin(_target_device=_make_device())
        mixin._clear_device_target()
        assert mixin._target_device is None

    def test_clears_session_overrides(self):
        session = _make_session_mock()
        session.override_host = "10.0.0.1"
        session.override_port = 22
        mixin = _make_mixin(_target_device=_make_device(), session=session)
        mixin._clear_device_target()
        assert session.override_host is None
        assert session.override_port is None
        assert session.override_username is None
        assert session.override_password is None
        assert session.override_ssh_key is None

    def test_deselects_topo_canvas_when_exists(self):
        canvas = MagicMock()
        mixin = _make_mixin(_target_device=_make_device(), _topo_canvas=canvas)
        mixin._clear_device_target()
        canvas.deselect.assert_called_once()

    def test_skips_topo_canvas_when_none(self):
        mixin = _make_mixin(_target_device=_make_device(), _topo_canvas=None)
        mixin._clear_device_target()
        # Should not crash

    def test_updates_target_lbl(self):
        target_lbl = MagicMock()
        mixin = _make_mixin(_target_device=_make_device(), _device_target_lbl=target_lbl)
        mixin._clear_device_target()
        target_lbl.setText.assert_called_once_with("(roteador padrao)")

    def test_publishes_event_when_connected(self):
        sb = MagicMock()
        sb.is_alive.return_value = True
        eq = MagicMock()
        mixin = _make_mixin(_target_device=_make_device(), _sb=sb, _event_queue=eq)
        mixin._clear_device_target()
        eq.put.assert_called_once()
        event = eq.put.call_args[0][0]
        assert event.type == EventType.DEVICE_DISCONNECTED
        assert event.source == "device"
        assert event.payload is not None
        assert event.payload.reason == "target_cleared"

    def test_does_not_publish_event_when_disconnected(self):
        sb = MagicMock()
        sb.is_alive.return_value = False
        eq = MagicMock()
        mixin = _make_mixin(_target_device=_make_device(), _sb=sb, _event_queue=eq)
        mixin._clear_device_target()
        eq.put.assert_not_called()

    def test_disconnects_when_alive(self):
        sb = MagicMock()
        sb.is_alive.return_value = True
        mixin = _make_mixin(_target_device=_make_device(), _sb=sb)
        mixin._clear_device_target()
        sb.disconnect.assert_called_once()

    def test_skips_disconnect_when_not_alive(self):
        sb = MagicMock()
        sb.is_alive.return_value = False
        mixin = _make_mixin(_target_device=_make_device(), _sb=sb)
        mixin._clear_device_target()
        sb.disconnect.assert_not_called()

    def test_calls_refresh_service_list(self):
        mixin = _make_mixin(_target_device=_make_device())
        mixin._clear_device_target()
        mixin._refresh_service_list.assert_called_once()

    def test_clears_device_info_lbl_when_exists(self):
        info_lbl = MagicMock()
        mixin = _make_mixin(_target_device=_make_device(), _device_info_lbl=info_lbl)
        mixin._clear_device_target()
        info_lbl.setText.assert_called_once()
        assert "Nenhum device" in info_lbl.setText.call_args[0][0]


# ══════════════════════════════════════════════════════════════════════════
#  _refresh_devices
# ══════════════════════════════════════════════════════════════════════════


class TestRefreshDevices:
    """_refresh_devices carrega inventário, faz probe e atualiza UI."""

    def test_loads_inventory(self):
        devices = [_make_device()]
        svc = _make_device_service(returns=devices)
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_devices_lock=lock, _device_service=svc)
        mixin._refresh_devices()
        assert mixin._devices_gen == 1

    def test_calls_simulate_in_mock_mode(self):
        svc = _make_device_service(returns=[])
        svc.save_inventory = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_devices_lock=lock, _mock_mode=True, _device_service=svc)
        mixin._refresh_devices()
        svc.probe_or_simulate.assert_called_once_with([], True)

    def test_calls_probe_in_non_mock_mode(self):
        svc = _make_device_service(returns=[])
        svc.save_inventory = MagicMock()
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_devices_lock=lock, _mock_mode=False, _device_service=svc)
        mixin._refresh_devices()
        svc.probe_or_simulate.assert_called_once_with([], False)

    def test_dispatches_ui_update(self):
        svc = _make_device_service(returns=[])
        svc.save_inventory = MagicMock()
        dispatched: list[tuple] = []

        def fake_dispatch(fn):
            dispatched.append(fn)
            fn()

        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_devices_lock=lock, _dispatch=fake_dispatch, _device_service=svc)
        mixin._refresh_devices()
        # Should have dispatched _update_devices_ui and status label update
        assert len(dispatched) >= 1

    def test_skips_when_lock_not_available(self):
        lock = MagicMock()
        lock.acquire.return_value = False
        mixin = _make_mixin(_devices_lock=lock)
        mixin._refresh_devices()
        # Should return early — gen unchanged
        assert mixin._devices_gen == 0

    def test_releases_lock_in_finally(self):
        lock = MagicMock()
        lock.acquire.return_value = True
        mixin = _make_mixin(_devices_lock=lock)
        mixin._refresh_devices()
        lock.release.assert_called_once()

    def test_save_failure_does_not_propagate(self):
        svc = _make_device_service(returns=[_make_device()])
        svc.save_inventory.side_effect = ValueError(
            "DEVICE_ENCRYPT_KEY nao configurada"
        )
        lock = MagicMock()
        lock.acquire.return_value = True
        dispatch = MagicMock()
        mixin = _make_mixin(
            _devices_lock=lock, _device_service=svc, _dispatch=dispatch
        )
        mixin._refresh_devices()
        assert mixin._devices_gen == 1
        dispatch.assert_called_once()
        lock.release.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
#  _delete_device
# ══════════════════════════════════════════════════════════════════════════


class TestDeleteDevice:
    """_delete_device remove device e limpa target se necessário."""

    @staticmethod
    def _patch_msgbox():
        """PATCH: QMessageBox.question → Yes (evita Qt crash)."""
        import PySide6.QtWidgets as QW
        return MagicMock(return_value=QW.QMessageBox.StandardButton.Yes)

    def _make_delete_svc(self):
        """DeviceService mock that records save_inventory calls."""
        svc = _make_device_service()
        svc.save_inventory = MagicMock()
        return svc

    def test_removes_device_from_inventory(self, monkeypatch):
        monkeypatch.setattr(
            "PySide6.QtWidgets.QMessageBox.question",
            self._patch_msgbox(),
        )
        device = _make_device(id="dev-001")
        remaining = [_make_device(id="dev-002")]
        svc = self._make_delete_svc()
        svc.delete_device.return_value = (remaining, device)
        lock = MagicMock()
        mixin = _make_mixin(_devices_lock=lock, _target_device=None, _device_service=svc)
        mixin._delete_device(device)
        svc.delete_device.assert_called_once_with(device.id, svc.load_inventory.return_value)
        # save_inventory is called internally by DeviceService.delete_device(),
        # not by the mixin — no explicit assertion needed here

    def test_clears_target_if_deleted_device_is_target(self, monkeypatch):
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", self._patch_msgbox())
        target_device = _make_device(id="dev-001", name="target-device")
        remaining = [_make_device(id="dev-002")]
        svc = self._make_delete_svc()
        svc.delete_device.return_value = (remaining, target_device)
        lock = MagicMock()
        mixin = _make_mixin(_devices_lock=lock, _target_device=target_device, _device_service=svc)
        mixin._delete_device(target_device)
        assert mixin._target_device is None

    def test_increments_gen(self, monkeypatch):
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", self._patch_msgbox())
        svc = self._make_delete_svc()
        lock = MagicMock()
        mixin = _make_mixin(_devices_lock=lock, _devices_gen=5, _device_service=svc)
        mixin._delete_device(_make_device())
        assert mixin._devices_gen == 6

    def test_spawns_refresh(self, monkeypatch):
        monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question", self._patch_msgbox())
        svc = self._make_delete_svc()
        spawned: list[tuple] = []

        def fake_spawn(fn, *args):
            spawned.append((fn, args))

        lock = MagicMock()
        mixin = _make_mixin(_devices_lock=lock, _spawn_io=fake_spawn, _device_service=svc)
        mixin._delete_device(_make_device())
        assert len(spawned) == 1
        assert spawned[0][0] == mixin._refresh_devices


# ══════════════════════════════════════════════════════════════════════════
#  _update_devices_ui
# ══════════════════════════════════════════════════════════════════════════


class TestUpdateDevicesUi:
    """_update_devices_ui atualiza canvas e controller com lista de devices."""

    def test_sets_devices_attribute(self):
        mixin = _make_mixin()
        devices = [_make_device(), _make_device(id="dev-002", name="other")]
        mixin._update_devices_ui(devices)
        assert mixin._devices is devices
        assert len(mixin._devices) == 2

    def test_calls_sync_from_devices(self):
        mixin = _make_mixin()
        devices = [_make_device()]
        mixin._update_devices_ui(devices)
        mixin._controller.sync_from_devices.assert_called_once_with(
            devices, publish_events=False
        )

    def test_calls_topo_canvas_update_devices(self):
        canvas = MagicMock()
        mixin = _make_mixin(_topo_canvas=canvas, _access_level="admin")
        devices = [_make_device()]
        mixin._update_devices_ui(devices)
        canvas.update_devices.assert_called_once_with(devices)

    def test_calls_set_access_on_canvas(self):
        canvas = MagicMock()
        mixin = _make_mixin(_topo_canvas=canvas, _access_level="tecnico")
        mixin._update_devices_ui([_make_device()])
        canvas.set_access.assert_called_once_with("tecnico")

    def test_skips_topo_canvas_when_none(self):
        mixin = _make_mixin(_topo_canvas=None)
        mixin._update_devices_ui([_make_device()])
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

    def test_creates_dialog_with_device_types(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = False
        monkeypatch.setattr(
            "huawei_manager.handlers.devices.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        mixin._show_device_dialog()
        mock_dialog_cls.assert_called_once()
        call_kwargs = mock_dialog_cls.call_args
        device_types = (
            call_kwargs.kwargs.get("device_types")
            or call_kwargs[1].get("device_types", [])
        )
        assert "ROUTER" in device_types

    def test_creates_dialog_with_device_for_edit(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = False
        monkeypatch.setattr(
            "huawei_manager.handlers.devices.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        device = _make_device()
        mixin._show_device_dialog(device)
        call_kwargs = mock_dialog_cls.call_args
        assert (call_kwargs.kwargs.get("device") == device) or (
            call_kwargs[1].get("device") == device
        )

    def test_creates_dialog_without_device_for_add(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = False
        monkeypatch.setattr(
            "huawei_manager.handlers.devices.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        mixin._show_device_dialog()
        call_kwargs = mock_dialog_cls.call_args
        assert (call_kwargs.kwargs.get("device") is None) or (
            call_kwargs[1].get("device") is None
        )

    def test_on_accept_calls_add_device(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = True
        mock_dialog_cls.return_value.get_data.return_value = {"name": "new-device"}
        monkeypatch.setattr(
            "huawei_manager.handlers.devices.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        mixin._show_device_dialog()
        mixin._device_service.add_device.assert_called_once_with({"name": "new-device"})

    def test_on_accept_calls_update_device(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = True
        mock_dialog_cls.return_value.get_data.return_value = {"name": "updated"}
        monkeypatch.setattr(
            "huawei_manager.handlers.devices.DeviceDialog", mock_dialog_cls
        )
        mixin = _make_mixin()
        device = _make_device()
        mixin._show_device_dialog(device)
        mixin._device_service.update_device.assert_called_once_with(
            device, {"name": "updated"}
        )

    def test_on_accept_calls_spawn_io_refresh(self, monkeypatch):
        mock_dialog_cls = MagicMock()
        mock_dialog_cls.return_value.exec.return_value = True
        mock_dialog_cls.return_value.get_data.return_value = {"name": "new"}
        monkeypatch.setattr(
            "huawei_manager.handlers.devices.DeviceDialog", mock_dialog_cls
        )
        spawned: list[tuple] = []

        def fake_spawn(fn, *args):
            spawned.append((fn, args))

        mixin = _make_mixin(_spawn_io=fake_spawn)
        mixin._show_device_dialog()
        assert len(spawned) == 1
        assert spawned[0][0] == mixin._refresh_devices


class TestSshEventSource:
    def test_connect_event_uses_device_id(self):
        from huawei_manager.sdn_controller.event_queue import Event, EventType

        device = _make_device(id="dev-r1")
        event = Event(
            type=EventType.DEVICE_CONNECTED,
            priority=10,
            payload={"device_id": device.id, "name": device.name},
            source=device.id,
        )
        assert event.source == "dev-r1"

    def test_disconnect_event_uses_device_id(self):
        from huawei_manager.sdn_controller.event_queue import Event, EventType

        device = _make_device(id="dev-r1")
        event = Event(
            type=EventType.DEVICE_DISCONNECTED,
            priority=10,
            payload={"device_id": device.id, "name": device.name},
            source=device.id,
        )
        assert event.source == "dev-r1"
