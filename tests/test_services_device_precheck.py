"""Pré-checagem contra o estado real do device (interfaces existentes).

O campo "interface" aceita qualquer nome sintaticamente válido, mas o
device só aceita interfaces que existem — sem esta checagem a VRP
responde "Wrong parameter found at '^' position" e o operador não
descobre o nome correto.
"""
from __future__ import annotations

from huawei_manager.services.device_precheck import (
    interfaces_in_block,
    missing_interfaces,
)

SNAPSHOT = """
interface GigabitEthernet0/0/0
 description uplink
#
interface GigabitEthernet0/0/1
#
interface LoopBack0
#
"""


class TestInterfacesInBlock:
    def test_finds_interface_lines(self):
        lines = [
            "acl number 3000",
            "interface GigabitEthernet0/0/1",
            "traffic-policy P_FILTRO_INTERFACE inbound",
            "quit",
        ]
        assert interfaces_in_block(lines) == ["GigabitEthernet0/0/1"]

    def test_deduplicates(self):
        lines = [
            "interface GigabitEthernet0/0/1",
            "quit",
            "interface GigabitEthernet0/0/1",
        ]
        assert interfaces_in_block(lines) == ["GigabitEthernet0/0/1"]

    def test_no_interface(self):
        assert interfaces_in_block(["acl number 3000", "quit"]) == []


class TestMissingInterfaces:
    def test_existing_interface(self):
        assert missing_interfaces(SNAPSHOT, ["GigabitEthernet0/0/1"]) == []

    def test_unknown_interface(self):
        missing = missing_interfaces(SNAPSHOT, ["GigabitEthernet0/0/9"])
        assert missing == ["GigabitEthernet0/0/9"]

    def test_case_insensitive(self):
        assert missing_interfaces(SNAPSHOT, ["gigabitethernet0/0/0"]) == []

    def test_reports_all_missing(self):
        missing = missing_interfaces(
            SNAPSHOT, ["GigabitEthernet0/0/0", "GigabitEthernet0/0/7"]
        )
        assert missing == ["GigabitEthernet0/0/7"]
