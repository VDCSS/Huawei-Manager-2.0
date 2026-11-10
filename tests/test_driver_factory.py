"""Testes da Driver Factory (Gap 1 — resolução por ``Device.type``)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from huawei_manager.device_models import Device
from huawei_manager.sdn_controller.drivers.factory import (
    driver_for,
    normalize_device_type,
)
from huawei_manager.sdn_controller.drivers.firewall import FirewallDriver
from huawei_manager.sdn_controller.drivers.router import RouterDriver
from huawei_manager.sdn_controller.drivers.switch import SwitchDriver


def _device(device_type: str) -> Device:
    return Device(id="d1", name="R1", host="10.0.0.1", type=device_type)


@pytest.mark.parametrize(
    ("device_type", "expected"),
    [
        ("ROUTER", RouterDriver),
        ("SWITCH", SwitchDriver),
        ("FIREWALL", FirewallDriver),
        ("switch", SwitchDriver),
        (" firewall ", FirewallDriver),
        ("Firewall", FirewallDriver),
    ],
)
def test_resolves_driver_by_device_type(device_type: str, expected: type) -> None:
    driver = driver_for(_device(device_type), MagicMock(), MagicMock())
    assert type(driver) is expected


@pytest.mark.parametrize(
    "device_type",
    ["LOAD-BALANCER", "WAN-ACCEL", "AP", "", "desconhecido"],
)
def test_unknown_type_falls_back_to_router(device_type: str) -> None:
    # Fail-safe: tipo não mapeado nunca fica sem driver (perfil VRP padrão).
    assert type(driver_for(_device(device_type), MagicMock(), MagicMock())) is RouterDriver


def test_none_device_uses_default_driver() -> None:
    assert type(driver_for(None, MagicMock(), MagicMock())) is RouterDriver


def test_driver_receives_southbound_and_event_bus() -> None:
    southbound = MagicMock()
    bus = MagicMock()
    driver = driver_for(_device("SWITCH"), southbound, bus)
    assert isinstance(driver, SwitchDriver)
    assert driver.device_type == "switch"
    assert driver._sb is southbound
    assert driver._eq is bus


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [(None, ""), ("ROUTER", "router"), (" Switch ", "switch")],
)
def test_normalize_device_type(raw: str | None, normalized: str) -> None:
    assert normalize_device_type(raw) == normalized
