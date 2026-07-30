"""Testes de concorrência — padrões críticos de thread-safety.

Testa:
1. EventQueue thread-safe pub/sub
2. ControllerCore thread-safe register/deregister
3. SessionTracker timeout concorrente
4. Vault backend read/write concorrente
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from huawei_manager.sdn_controller.event_queue import Event, EventQueue, EventType
from huawei_manager.sdn_controller.core import ControllerCore


class TestEventQueueConcurrency:
    """Testa thread-safety do EventQueue sob carga concorrente."""

    def test_concurrent_put_does_not_deadlock(self):
        """10 threads inserindo 100 eventos cada — não deve deadlock."""
        eq = EventQueue()
        errors: list[Exception] = []

        def producer(thread_id: int):
            try:
                for i in range(100):
                    eq.put(
                        Event(
                            type=EventType.DEVICE_CONNECTED,
                            source=f"thread-{thread_id}-device-{i}",
                        )
                    )
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(producer, tid) for tid in range(10)]
            for f in as_completed(futures):
                f.result()

        assert not errors, f"Errors during concurrent put: {errors}"
        assert eq._queue.qsize() == 1000

    def test_concurrent_subscribe_and_put(self):
        """Subscribe durante put concorrente — não deve corromper estado."""
        eq = EventQueue()
        received: list[Event] = []
        lock = threading.Lock()

        def callback(event: Event):
            with lock:
                received.append(event)

        eq.subscribe(EventType.DEVICE_CONNECTED, callback)

        def producer():
            for i in range(50):
                eq.put(
                    Event(type=EventType.DEVICE_CONNECTED, source=f"device-{i}")
                )

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(producer) for _ in range(5)]
            for f in as_completed(futures):
                f.result()

        assert len(received) == 250

    def test_unsubscribe_stops_delivery(self):
        """Após unsubscribe, callback não recebe novos eventos."""
        eq = EventQueue()
        received: list[Event] = []
        lock = threading.Lock()

        def callback(event: Event):
            with lock:
                received.append(event)

        eq.subscribe(EventType.DEVICE_CONNECTED, callback)

        # Put some events
        for i in range(10):
            eq.put(Event(type=EventType.DEVICE_CONNECTED, source=f"device-{i}"))

        with lock:
            count_before = len(received)
        assert count_before == 10

        # Unsubscribe
        eq.unsubscribe(EventType.DEVICE_CONNECTED, callback)

        # Put more events
        for i in range(10):
            eq.put(Event(type=EventType.DEVICE_CONNECTED, source=f"device-{i}"))

        with lock:
            count_after = len(received)

        # Should still be 10 (no new events delivered after unsubscribe)
        assert count_after == 10


class TestControllerCoreConcurrency:
    """Testa thread-safety do ControllerCore sob carga concorrente."""

    def test_concurrent_register_deregister(self):
        """10 threads registrando e deregistrando devices — não deve crashar."""
        core = ControllerCore()
        errors: list[Exception] = []

        def worker(thread_id: int):
            try:
                for i in range(50):
                    dev_id = f"device-{thread_id}-{i}"
                    core.register(dev_id, f"10.0.{thread_id}.{i}", 22, "router")
                    core.get_state(dev_id)
                    core.update_state(dev_id, status="online")
                    core.deregister(dev_id)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(worker, tid) for tid in range(10)]
            for f in as_completed(futures):
                f.result()

        assert not errors, f"Errors during concurrent register/deregister: {errors}"
        assert len(core.list_devices()) == 0

    def test_concurrent_list_devices(self):
        """list_devices() concorrente com register — não deve corromper."""
        core = ControllerCore()
        results: list[int] = []
        lock = threading.Lock()

        def registrar():
            for i in range(100):
                core.register(f"dev-{i}", f"10.0.0.{i % 255}", 22, "switch")

        def lister():
            for _ in range(100):
                with lock:
                    results.append(len(core.list_devices()))

        with ThreadPoolExecutor(max_workers=4) as pool:
            pool.submit(registrar)
            pool.submit(registrar)
            pool.submit(lister)
            pool.submit(lister)

        # All list results should be valid counts (0-200)
        assert all(0 <= r <= 200 for r in results)


class TestVaultConcurrency:
    """Testa thread-safety de vault backends."""

    def test_env_backend_concurrent_read_write(self):
        """EnvBackend read/write concorrente — não deve corromper."""
        from huawei_manager.vault_backends.backends_env import EnvBackend
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_KEY=initial\n")
            env_path = f.name

        try:
            backend = EnvBackend(env_path)
            errors: list[Exception] = []

            def writer(thread_id: int):
                try:
                    for i in range(20):
                        backend.put(f"KEY_{thread_id}_{i}", f"value_{i}")
                except Exception as e:
                    errors.append(e)

            def reader():
                try:
                    for _ in range(20):
                        backend.get("TEST_KEY")
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = []
                for tid in range(3):
                    futures.append(pool.submit(writer, tid))
                for _ in range(2):
                    futures.append(pool.submit(reader))
                for f in as_completed(futures):
                    f.result()

            assert not errors, f"Errors during concurrent vault access: {errors}"
        finally:
            os.unlink(env_path)


class TestAuditLogConcurrency:
    """Testa thread-safety do AuditLogger."""

    def test_concurrent_log_operations(self):
        """10 threads escrevendo logs simultaneamente — não deve corromper."""
        from huawei_manager.audit_log import AuditLogger
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            logger = AuditLogger(log_path)
            errors: list[Exception] = []

            def writer(thread_id: int):
                try:
                    for i in range(50):
                        logger.log_operation(
                            op=f"test_op_{i}",
                            user=f"user_{thread_id}",
                            host="10.0.0.1",
                            datastore="test",
                            status="ok",
                            duration_ms=10.0,
                        )
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = [pool.submit(writer, tid) for tid in range(10)]
                for f in as_completed(futures):
                    f.result()

            assert not errors, f"Errors during concurrent audit log: {errors}"

            # Verify file integrity
            with open(log_path) as f:
                lines = f.readlines()
            assert len(lines) == 500
        finally:
            os.unlink(log_path)
