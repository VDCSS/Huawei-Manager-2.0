"""Tests for EventQueue (thread-safe event bus with pub/sub)."""
from __future__ import annotations

import queue
import threading
from datetime import datetime

import pytest

from huawei_manager.sdn_controller.event_queue import (
    Event,
    EventQueue,
    EventType,
)


class TestEventType:
    """EventType enum must cover all SDN event categories."""

    def test_has_device_events(self):
        assert EventType.DEVICE_CONNECTED is not None
        assert EventType.DEVICE_DISCONNECTED is not None
        assert EventType.DEVICE_ERROR is not None

    def test_has_operational_events(self):
        assert EventType.CONFIG_CHANGED is not None
        assert EventType.TOPOLOGY_CHANGED is not None
        assert EventType.COMMAND_EXECUTED is not None
        assert EventType.VNF_STATUS_CHANGED is not None


class TestEventDataclass:
    """Event dataclass must hold all required fields."""

    def test_creates_with_minimal_fields(self):
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        assert ev.type == EventType.DEVICE_CONNECTED
        assert ev.source == "gw-01"
        assert ev.data is None
        assert isinstance(ev.timestamp, datetime)

    def test_creates_with_data(self):
        ev = Event(
            type=EventType.CONFIG_CHANGED,
            source="gw-01",
            data={"cmd": "vlan 10", "status": "ok"},
        )
        assert ev.data == {"cmd": "vlan 10", "status": "ok"}

    def test_timestamp_is_set_on_creation(self):
        before = datetime.now()
        ev = Event(type=EventType.DEVICE_ERROR, source="test")
        after = datetime.now()
        assert before <= ev.timestamp <= after


class TestEventQueuePutGet:
    """Basic put/get operations."""

    def test_put_and_get_single_event(self):
        eq = EventQueue()
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        eq.put(ev)
        result = eq.get(timeout=1)
        assert result is ev

    def test_get_returns_none_on_timeout(self):
        eq = EventQueue()
        result = eq.get(timeout=0.1)
        assert result is None

    def test_fifo_order(self):
        eq = EventQueue()
        ev1 = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        ev2 = Event(type=EventType.DEVICE_DISCONNECTED, source="gw-01")
        eq.put(ev1)
        eq.put(ev2)
        assert eq.get() is ev1
        assert eq.get() is ev2

    def test_maxsize_blocks_on_full(self):
        eq = EventQueue(maxsize=1)
        eq.put(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))
        with pytest.raises(queue.Full):
            eq.put(
                Event(type=EventType.DEVICE_CONNECTED, source="gw-02"),
                block=False,
            )


class TestEventQueueSubscribe:
    """Pub/sub subscription mechanics."""

    def test_subscriber_receives_matching_event(self):
        eq = EventQueue()
        received = []

        def cb(ev: Event) -> None:
            received.append(ev)

        eq.subscribe(EventType.DEVICE_CONNECTED, cb)
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        eq.put(ev)
        assert received == [ev]

    def test_subscriber_not_called_for_other_types(self):
        eq = EventQueue()
        received = []

        def cb(ev: Event) -> None:
            received.append(ev)

        eq.subscribe(EventType.CONFIG_CHANGED, cb)
        eq.put(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))
        assert received == []

    def test_unsubscribe_removes_callback(self):
        eq = EventQueue()
        received = []

        def cb(ev: Event) -> None:
            received.append(ev)

        eq.subscribe(EventType.DEVICE_CONNECTED, cb)
        eq.unsubscribe(EventType.DEVICE_CONNECTED, cb)
        eq.put(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))
        assert received == []

    def test_multiple_subscribers_same_type(self):
        eq = EventQueue()
        received_a = []
        received_b = []

        def cb_a(ev: Event) -> None:
            received_a.append(ev)

        def cb_b(ev: Event) -> None:
            received_b.append(ev)

        eq.subscribe(EventType.DEVICE_CONNECTED, cb_a)
        eq.subscribe(EventType.DEVICE_CONNECTED, cb_b)
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        eq.put(ev)
        assert received_a == [ev]
        assert received_b == [ev]


class TestEventQueuePoll:
    """Poll drains all available events."""

    def test_poll_returns_all_events(self):
        eq = EventQueue()
        ev1 = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        ev2 = Event(type=EventType.DEVICE_DISCONNECTED, source="gw-01")
        eq.put(ev1)
        eq.put(ev2)
        events = eq.poll(timeout=0.1)
        assert len(events) == 2
        assert events[0] is ev1
        assert events[1] is ev2

    def test_poll_returns_empty_when_empty(self):
        eq = EventQueue()
        assert eq.poll(timeout=0.1) == []


class TestEventQueueThreadSafety:
    """Must work correctly across threads."""

    def test_put_from_worker_get_from_main(self):
        eq = EventQueue()
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")

        def worker() -> None:
            eq.put(ev)

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        result = eq.get(timeout=1)
        assert result is ev

    def test_subscriber_called_from_put_thread(self):
        eq = EventQueue()
        caller_thread: list[threading.Thread | None] = [None]

        def cb(ev: Event) -> None:
            caller_thread[0] = threading.current_thread()

        eq.subscribe(EventType.DEVICE_CONNECTED, cb)

        def worker() -> None:
            eq.put(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        # Callback was invoked from put() thread
        assert caller_thread[0] is t

    def test_subscriber_exception_does_not_break_queue(self):
        eq = EventQueue()

        def broken_cb(ev: Event) -> None:
            raise RuntimeError("Kaboom")

        eq.subscribe(EventType.DEVICE_CONNECTED, broken_cb)
        eq.put(Event(type=EventType.DEVICE_CONNECTED, source="gw-01"))
        # Queue should still work after broken subscriber
        result = eq.get(timeout=1)
        assert result is not None
