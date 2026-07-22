"""Tests for EventQueue (thread-safe event bus with pub/sub)."""
from __future__ import annotations

import threading
from datetime import datetime

from huawei_manager.sdn_controller.event_queue import (
    Event,
    EventQueue,
    EventType,
)
from huawei_manager.sdn_controller.events import (
    ConfigChangedPayload,
    DeviceConnectedPayload,
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

    def test_has_alert_and_an_trigger(self):
        assert EventType.ALERT is not None
        assert EventType.AN_TRIGGER is not None


class TestEventDataclass:
    """Event dataclass must hold all required fields."""

    def test_creates_with_minimal_fields(self):
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        assert ev.type == EventType.DEVICE_CONNECTED
        assert ev.source == "gw-01"
        assert ev.payload is None
        assert isinstance(ev.timestamp, datetime)

    def test_creates_with_data(self):
        ev = Event(
            type=EventType.CONFIG_CHANGED,
            source="gw-01",
            payload=ConfigChangedPayload(commands=["vlan 10"], status="ok"),
        )
        assert isinstance(ev.payload, ConfigChangedPayload)
        assert ev.payload.commands == ["vlan 10"]
        assert ev.payload.status == "ok"

    def test_timestamp_is_set_on_creation(self):
        before = datetime.now()
        ev = Event(type=EventType.DEVICE_ERROR, source="test")
        after = datetime.now()
        assert before <= ev.timestamp <= after

    def test_creates_with_payload(self):
        payload = DeviceConnectedPayload(host="10.0.0.1", session_id="sess-01")
        ev = Event(
            type=EventType.DEVICE_CONNECTED,
            source="gw-01",
            payload=payload,
        )
        assert ev.payload is payload
        assert ev.payload.host == "10.0.0.1"


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
        eq.put(
            Event(type=EventType.DEVICE_CONNECTED, source="gw-02"),
            block=False,
        )
        ev = eq.get()
        assert ev is not None
        assert ev.source == "gw-01"


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


class TestEventPriority:
    """Priority field in Event dataclass."""

    def test_default_priority_is_10(self):
        ev = Event(type=EventType.DEVICE_CONNECTED, source="gw-01")
        assert ev.priority == 10

    def test_custom_priority(self):
        ev = Event(type=EventType.ALERT, source="gw-01", priority=0)
        assert ev.priority == 0

    def test_low_priority(self):
        ev = Event(type=EventType.VNF_STATUS_CHANGED, source="gw-01", priority=20)
        assert ev.priority == 20


class TestEventQueuePriorityOrder:
    """PriorityQueue must return higher priority events first."""

    def test_high_priority_comes_first(self):
        eq = EventQueue()
        normal = Event(type=EventType.DEVICE_CONNECTED, source="gw-01", priority=10)
        alert = Event(type=EventType.ALERT, source="gw-01", priority=0)
        eq.put(normal)
        eq.put(alert)
        assert eq.get() is alert
        assert eq.get() is normal

    def test_low_priority_comes_last(self):
        eq = EventQueue()
        normal = Event(type=EventType.DEVICE_CONNECTED, source="gw-01", priority=10)
        low = Event(type=EventType.VNF_STATUS_CHANGED, source="gw-01", priority=20)
        eq.put(normal)
        eq.put(low)
        assert eq.get() is normal
        assert eq.get() is low

    def test_same_priority_fifo(self):
        eq = EventQueue()
        ev1 = Event(type=EventType.DEVICE_CONNECTED, source="gw-01", priority=10)
        ev2 = Event(type=EventType.DEVICE_DISCONNECTED, source="gw-01", priority=10)
        ev3 = Event(type=EventType.DEVICE_ERROR, source="gw-01", priority=10)
        eq.put(ev1)
        eq.put(ev2)
        eq.put(ev3)
        assert eq.get() is ev1
        assert eq.get() is ev2
        assert eq.get() is ev3

    def test_critical_preempts_all(self):
        eq = EventQueue()
        low = Event(type=EventType.VNF_STATUS_CHANGED, source="gw-01", priority=20)
        normal = Event(type=EventType.DEVICE_CONNECTED, source="gw-01", priority=10)
        alert = Event(type=EventType.ALERT, source="gw-01", priority=0)
        eq.put(low)
        eq.put(normal)
        eq.put(alert)
        # alert has priority 0, should come out first
        assert eq.get() is alert
        assert eq.get() is normal
        assert eq.get() is low

    def test_poll_returns_priority_ordered(self):
        eq = EventQueue()
        low = Event(type=EventType.VNF_STATUS_CHANGED, source="gw-01", priority=20)
        alert = Event(type=EventType.ALERT, source="gw-01", priority=0)
        normal = Event(type=EventType.DEVICE_CONNECTED, source="gw-01", priority=10)
        eq.put(low)
        eq.put(alert)
        eq.put(normal)
        events = eq.poll(timeout=0.1)
        assert len(events) == 3
        assert events[0] is alert
        assert events[1] is normal
        assert events[2] is low

    def test_an_trigger_normal_priority(self):
        """AN_TRIGGER uses default priority (10) unless specified."""
        eq = EventQueue()
        trigger = Event(type=EventType.AN_TRIGGER, source="automation", priority=5)
        normal = Event(type=EventType.DEVICE_CONNECTED, source="gw-01", priority=10)
        eq.put(normal)
        eq.put(trigger)
        # trigger has higher priority (5 < 10)
        assert eq.get() is trigger
        assert eq.get() is normal


class TestEventQueueFullWithPriority:
    """Full queue behavior with priority items."""

    def test_maxsize_respected_with_priority(self):
        eq = EventQueue(maxsize=2)
        eq.put(Event(type=EventType.ALERT, source="gw-01", priority=0))
        eq.put(Event(type=EventType.DEVICE_CONNECTED, source="gw-02", priority=10))
        eq.put(
            Event(type=EventType.DEVICE_ERROR, source="gw-03"),
            block=False,
        )
        ev = eq.get()
        assert ev is not None
        assert ev.type == EventType.ALERT

    def test_full_queue_still_prioritizes(self):
        eq = EventQueue(maxsize=2)
        normal = Event(type=EventType.DEVICE_CONNECTED, source="gw-01", priority=10)
        alert = Event(type=EventType.ALERT, source="gw-01", priority=0)
        eq.put(normal)
        eq.put(alert)
        # Even though alert was put second, it comes out first
        assert eq.get() is alert
        assert eq.get() is normal


class TestEventQueuePriorityConcurrency:
    """Thread safety with priority ordering."""

    def test_concurrent_high_and_low_priority(self):
        eq = EventQueue()
        results: list[Event | None] = []
        results_lock = threading.Lock()

        def consumer() -> None:
            for _ in range(4):
                ev = eq.get(timeout=2)
                with results_lock:
                    results.append(ev)

        def producer_high() -> None:
            for i in range(2):
                eq.put(
                    Event(type=EventType.ALERT, source=f"alert-{i}", priority=0)
                )

        def producer_low() -> None:
            for i in range(2):
                eq.put(
                    Event(
                        type=EventType.VNF_STATUS_CHANGED,
                        source=f"vnf-{i}",
                        priority=20,
                    )
                )

        t_consumer = threading.Thread(target=consumer)
        t_high = threading.Thread(target=producer_high)
        t_low = threading.Thread(target=producer_low)

        t_consumer.start()
        t_high.start()
        t_low.start()

        t_high.join()
        t_low.join()
        t_consumer.join()

        assert len(results) == 4
        # First two should be alerts (priority 0)
        assert results[0] is not None
        assert results[0].priority == 0
        assert results[1] is not None
        assert results[1].priority == 0

    def test_subscriber_with_priority(self):
        """Subscribe still works with priority items."""
        eq = EventQueue()
        received: list[Event] = []

        def cb(ev: Event) -> None:
            received.append(ev)

        eq.subscribe(EventType.ALERT, cb)
        alert = Event(type=EventType.ALERT, source="gw-01", priority=0)
        eq.put(alert)
        assert received == [alert]
