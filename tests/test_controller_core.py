"""Tests for ControllerCore — centralized SDN state management."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from huawei_manager.sdn_controller.event_queue import (
    Event,
    EventQueue,
    EventType,
)
from huawei_manager.sdn_controller.events import (
    ConfigChangedPayload,
    DeviceErrorPayload,
    VnfStatusChangedPayload,
)
from tests.helpers import wait_until


@pytest.fixture
def event_queue() -> EventQueue:
    """Fresh EventQueue for each test."""
    return EventQueue()


@pytest.fixture
def dump_path(tmp_path: Path) -> str:
    """Temporary JSON dump path."""
    return str(tmp_path / "controller_state.json")


class TestDeviceState:
    """DeviceState dataclass must hold device metadata and runtime state."""

    def test_creates_with_minimal_fields(self) -> None:
        from huawei_manager.sdn_controller.core import DeviceState

        ds = DeviceState(device_id="gw-01", host="10.0.0.1", port=22, device_type="router")
        assert ds.device_id == "gw-01"
        assert ds.host == "10.0.0.1"
        assert ds.port == 22
        assert ds.device_type == "router"
        assert ds.status == "unknown"
        assert ds.last_seen is None
        assert ds.metadata == {}

    def test_creates_with_all_fields(self) -> None:
        from huawei_manager.sdn_controller.core import DeviceState

        now = datetime.now()
        ds = DeviceState(
            device_id="fw-01",
            host="10.0.0.2",
            port=443,
            device_type="firewall",
            status="online",
            last_seen=now,
            metadata={"vendor": "Huawei", "version": "V600R008"},
        )
        assert ds.device_id == "fw-01"
        assert ds.status == "online"
        assert ds.last_seen is now
        assert ds.metadata["vendor"] == "Huawei"

    def test_default_status_is_unknown(self) -> None:
        from huawei_manager.sdn_controller.core import DeviceState

        ds = DeviceState(device_id="sw-01", host="10.0.0.3", port=22, device_type="switch")
        assert ds.status == "unknown"

    def test_to_dict_roundtrip(self) -> None:
        from huawei_manager.sdn_controller.core import DeviceState

        original = DeviceState(
            device_id="gw-01",
            host="10.0.0.1",
            port=22,
            device_type="router",
            status="online",
            metadata={"vendor": "Huawei"},
        )
        data = original.to_dict()
        restored = DeviceState.from_dict(data)
        assert restored.device_id == original.device_id
        assert restored.host == original.host
        assert restored.port == original.port
        assert restored.device_type == original.device_type
        assert restored.status == original.status
        assert restored.metadata == original.metadata


class TestControllerCoreRegisterGetState:
    """Core operation: register device and retrieve its state."""

    def test_register_creates_device(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.device_id == "gw-01"
        assert state.host == "10.0.0.1"

    def test_register_with_metadata(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        meta = {"role": "core", "site": "SP01"}
        cc.register("gw-01", "10.0.0.1", 22, "router", metadata=meta)
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.metadata == meta

    def test_get_state_nonexistent(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        assert cc.get_state("nonexistent") is None

    def test_register_duplicate_overwrites(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.register("gw-01", "10.0.0.2", 22, "router", metadata={"version": "2"})
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.host == "10.0.0.2"
        assert state.metadata == {"version": "2"}

    def test_list_devices(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.register("sw-01", "10.0.0.2", 22, "switch")
        devices = cc.list_devices()
        assert set(devices) == {"gw-01", "sw-01"}

    def test_list_devices_empty(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        assert cc.list_devices() == []


class TestControllerCoreDeregister:
    """Deregister removes device and publishes event."""

    def test_deregister_removes_device(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        assert cc.deregister("gw-01") is True
        assert cc.get_state("gw-01") is None

    def test_deregister_nonexistent(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        assert cc.deregister("nonexistent") is False

    def test_deregister_publishes_event(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        # Drain the DEVICE_CONNECTED event from register()
        event_queue.poll(timeout=0.1)
        cc.deregister("gw-01")
        ev = event_queue.get(timeout=0.5)
        assert ev is not None
        assert ev.type == EventType.DEVICE_DISCONNECTED
        assert ev.source == "gw-01"


class TestControllerCoreEventsChangeState:
    """Events must automatically update device state."""

    def test_device_connected_sets_status_online(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        cc.process_event(ev)
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.status == "online"
        assert state.last_seen is not None

    def test_device_disconnected_sets_status_offline(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.process_event(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))
        cc.process_event(Event(type=EventType.DEVICE_DISCONNECTED, source="gw-01"))
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.status == "offline"

    def test_device_error_sets_status_error(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        ev = Event(
            type=EventType.DEVICE_ERROR,
            source="gw-01",
            payload=DeviceErrorPayload(error="Connection timeout"),
        )
        cc.process_event(ev)
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.status == "error"
        assert state.metadata.get("last_error") == "Connection timeout"

    def test_event_for_unregistered_device_ignored(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        # Should not raise
        cc.process_event(Event(type=EventType.DEVICE_CONNECTED, source="unknown"))
        assert cc.get_state("unknown") is None

    def test_config_changed_event_updates_metadata(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        ev = Event(
            type=EventType.CONFIG_CHANGED,
            source="gw-01",
            payload=ConfigChangedPayload(),
        )
        cc.process_event(ev)
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.metadata.get("last_config_change") is not None

    def test_vnf_status_changed_updates_status(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        ev = Event(
            type=EventType.VNF_STATUS_CHANGED,
            source="gw-01",
            payload=VnfStatusChangedPayload(status="degraded"),
        )
        cc.process_event(ev)
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.status == "degraded"


class TestControllerCoreManualUpdate:
    """Direct state updates without events."""

    def test_update_status(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.update_state("gw-01", status="online")
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.status == "online"

    def test_update_nonexistent_noop(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        # Should not raise
        cc.update_state("unknown", status="online")

    def test_update_metadata(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.update_state("gw-01", metadata={"version": "V200R019"})
        state = cc.get_state("gw-01")
        assert state is not None
        assert state.metadata["version"] == "V200R019"


class TestControllerCoreDumpLoad:
    """State serialization to/from JSON."""

    def test_dump_creates_file(self, event_queue: EventQueue, dump_path: str) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue, dump_path=dump_path)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.register("sw-01", "10.0.0.2", 22, "switch")
        cc.dump()
        assert Path(dump_path).exists()
        with open(dump_path) as f:
            data = json.load(f)
        assert "gw-01" in data
        assert "sw-01" in data

    def test_dump_roundtrip(self, event_queue: EventQueue, dump_path: str) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue, dump_path=dump_path)
        cc.register("gw-01", "10.0.0.1", 22, "router", metadata={"role": "core"})
        cc.process_event(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))
        cc.dump()

        cc2 = ControllerCore(event_queue=EventQueue(), dump_path=dump_path)
        count = cc2.load(dump_path)
        assert count == 1
        state = cc2.get_state("gw-01")
        assert state is not None
        assert state.host == "10.0.0.1"
        assert state.status == "online"
        assert state.metadata == {"role": "core"}

    def test_load_nonexistent_file(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        count = cc.load("/nonexistent/path.json")
        assert count == 0

    def test_dump_default_path_uses_configured(self, event_queue: EventQueue, dump_path: str) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue, dump_path=dump_path)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.dump()
        assert Path(dump_path).exists()


class TestControllerCoreConcurrency:
    """Thread-safe operations under concurrent access."""

    def test_concurrent_register(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        n = 50
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                cc.register(f"dev-{i}", f"10.0.0.{i}", 22, "router")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(cc.list_devices()) == n

    def test_concurrent_deregister(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        for i in range(50):
            cc.register(f"dev-{i}", f"10.0.0.{i}", 22, "router")

        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                cc.deregister(f"dev-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert cc.list_devices() == []

    def test_concurrent_read_write(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")

        errors: list[Exception] = []

        def writer() -> None:
            for i in range(100):
                try:
                    cc.update_state("gw-01", status="online" if i % 2 == 0 else "offline")
                except Exception as e:
                    errors.append(e)

        def reader() -> None:
            for _ in range(100):
                try:
                    cc.get_state("gw-01")
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0


class TestControllerCorePeriodicDump:
    """Periodic JSON dump timer."""

    def test_start_stop_does_not_raise(self, event_queue: EventQueue, dump_path: str) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue, dump_path=dump_path, dump_interval=3600)
        cc.start()
        time.sleep(0.05)
        cc.stop()  # Should not raise

    def test_periodic_dump_writes_file(self, event_queue: EventQueue, dump_path: str) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue, dump_path=dump_path, dump_interval=0.1)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.start()
        wait_until(lambda: Path(dump_path).exists(), timeout=2.0)
        cc.stop()
        with open(dump_path) as f:
            data = json.load(f)
        assert "gw-01" in data

    def test_no_dump_path_no_crash(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue, dump_path=None, dump_interval=0.1)
        cc.start()
        time.sleep(0.15)
        cc.stop()  # Should not raise even without dump_path


class TestControllerCoreIntegration:
    """Integration with EventQueue subscription."""

    def test_subscribe_updates_state_on_events(self, event_queue: EventQueue) -> None:
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=event_queue)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        cc.start()

        # Events published via EventQueue should update state
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        event_queue.put(ev)
        time.sleep(0.05)

        state = cc.get_state("gw-01")
        assert state is not None
        assert state.status == "online"

        cc.stop()

    def test_no_event_queue_no_crash(self) -> None:
        """ControllerCore works without an EventQueue."""
        from huawei_manager.sdn_controller.core import ControllerCore

        cc = ControllerCore(event_queue=None)
        cc.register("gw-01", "10.0.0.1", 22, "router")
        assert cc.get_state("gw-01") is not None
        cc.process_event(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))
        assert cc.get_state("gw-01") is not None
