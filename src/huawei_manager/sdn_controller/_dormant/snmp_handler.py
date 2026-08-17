from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger("huawei.sdn.snmp")


@dataclass
class SnmpTrap:
    trap_oid: str
    source: str
    community: str = "public"
    timestamp: datetime = field(default_factory=datetime.now)
    variables: dict[str, str] = field(default_factory=dict)


class SnmpTrapHandler:
    def __init__(self) -> None:
        self._callbacks: dict[str, list[Callable[[SnmpTrap], None]]] = {}

    def register_callback(self, trap_oid: str, callback: Callable[[SnmpTrap], None]) -> None:
        self._callbacks.setdefault(trap_oid, []).append(callback)

    def unregister_callback(self, trap_oid: str, callback: Callable[[SnmpTrap], None]) -> None:
        if trap_oid in self._callbacks:
            self._callbacks[trap_oid].remove(callback)

    def handle_trap(self, trap: SnmpTrap) -> list[str]:
        results: list[str] = []
        for oid, cbs in self._callbacks.items():
            if trap.trap_oid.startswith(oid):
                for cb in cbs:
                    try:
                        cb(trap)
                        results.append(f"callback OK for {oid}")
                    except Exception as e:
                        log.exception("SNMP callback failed for %s: %s", oid, e)
                        results.append(f"callback FAIL for {oid}: {e}")
        if not results:
            log.info("No handler for SNMP trap %s from %s", trap.trap_oid, trap.source)
            results.append("unhandled")
        return results
