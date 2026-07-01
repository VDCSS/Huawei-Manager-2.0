"""Tests for Normalizer — parse Huawei CLI outputs to structured data."""
from __future__ import annotations

from huawei_manager.sdn_controller.normalizer import (
    ArpEntry,
    InterfaceEntry,
    RouteEntry,
    VlanEntry,
    parse_arp_table,
    parse_interfaces,
    parse_routing_table,
    parse_vlans,
)

# ── Sample CLI outputs ──────────────────────────────────────────────────────

SAMPLE_ROUTING_TABLE = """\
Route Flags: R - relay, D - download to fib
------------------------------------------------------------------------------
Routing Table : _public_
         Destinations : 5        Routes : 5

Destination/Mask    Proto   Pre  Cost        NextHop         Interface
      0.0.0.0/0     Static  60   0          10.10.10.1      GigabitEthernet0/0/0
     10.10.10.0/24  Direct  0    0          10.10.10.100    GigabitEthernet0/0/0
     10.10.10.100/32 Direct 0    0          127.0.0.1       GigabitEthernet0/0/0
     192.168.1.0/24 OSPF    10   2          10.10.10.1      GigabitEthernet0/0/0
     192.168.2.0/24 Static  60   0          10.20.20.1      GigabitEthernet0/0/1
"""

SAMPLE_INTERFACES = """\
PHY: Physical
*down: administratively down
^down: standby
(l): loopback
(g): gigabit
(s): speed forced
(i): internal
Interface                   PHY  Protocol    InUti  OutUti    inErrors  outErrors
GigabitEthernet0/0/0        up    up         0.01%  0.01%     0         0
GigabitEthernet0/0/1        up    up         0.00%  0.00%     0         0
GigabitEthernet0/0/2        down  down       0.00%  0.00%     0         0
LoopBack0                   up    up(s)      0.00%  0.00%     0         0
NULL0                       up    up(s)      0.00%  0.00%     0         0
"""

SAMPLE_ARP_TABLE = """\
ARP Type: Dynamic - D, Static - S, Open - O
Flags: I - Internal, E - External
IP ADDRESS      MAC ADDRESS    EXPIRE(M)  TYPE  INTERFACE      VPN-INSTANCE
10.10.10.1      aabb-cc01-0101  120        D    GE0/0/0
10.10.10.100    aabb-cc01-0102  117        D    GE0/0/0
10.20.20.1      aabb-cc01-0201  110        D    GE0/0/1
192.168.1.1     aabb-cc01-0301  95         D    GE0/0/1
"""

SAMPLE_VLANS = """\
The total number of vlans is : 4
U: Up      G: Guard      D: Down      #: Part of learning

VLAN ID   Name            Status     Ports
1         default         up         GE0/0/0 GE0/0/1
10        management      up         GE0/0/0
20        data            up         GE0/0/1
100       voice           down       GE0/0/2
"""


class TestRouteEntry:
    """RouteEntry dataclass must hold routing table fields."""

    def test_creates_with_all_fields(self):
        entry = RouteEntry(
            destination="0.0.0.0",
            mask="0",
            next_hop="10.10.10.1",
            interface="GigabitEthernet0/0/0",
            protocol="Static",
            preference=60,
            cost=0,
        )
        assert entry.destination == "0.0.0.0"
        assert entry.next_hop == "10.10.10.1"
        assert entry.protocol == "Static"


class TestArpEntry:
    """ArpEntry dataclass must hold ARP table fields."""

    def test_creates_with_all_fields(self):
        entry = ArpEntry(
            ip_address="10.10.10.1",
            mac_address="aabb-cc01-0101",
            interface="GE0/0/0",
            status="D",
        )
        assert entry.ip_address == "10.10.10.1"
        assert entry.mac_address == "aabb-cc01-0101"


class TestInterfaceEntry:
    """InterfaceEntry dataclass must hold interface fields."""

    def test_creates_with_all_fields(self):
        entry = InterfaceEntry(
            name="GigabitEthernet0/0/0",
            status="up",
            protocol_status="up",
        )
        assert entry.name == "GigabitEthernet0/0/0"
        assert entry.status == "up"


class TestVlanEntry:
    """VlanEntry dataclass must hold VLAN fields."""

    def test_creates_with_all_fields(self):
        entry = VlanEntry(
            vlan_id=10,
            name="management",
            status="up",
            ports=["GE0/0/0"],
        )
        assert entry.vlan_id == 10
        assert entry.ports == ["GE0/0/0"]


class TestParseRoutingTable:
    """Parse 'display ip routing-table' output."""

    def test_parses_five_routes(self):
        routes = parse_routing_table(SAMPLE_ROUTING_TABLE)
        assert len(routes) == 5

    def test_parses_default_route(self):
        routes = parse_routing_table(SAMPLE_ROUTING_TABLE)
        default = routes[0]
        assert default.destination == "0.0.0.0"
        assert default.mask == "0"
        assert default.next_hop == "10.10.10.1"
        assert default.protocol == "Static"

    def test_parses_direct_route(self):
        routes = parse_routing_table(SAMPLE_ROUTING_TABLE)
        direct = routes[1]
        assert direct.destination == "10.10.10.0"
        assert direct.mask == "24"
        assert direct.protocol == "Direct"

    def test_parses_ospf_route(self):
        routes = parse_routing_table(SAMPLE_ROUTING_TABLE)
        ospf = routes[3]
        assert ospf.destination == "192.168.1.0"
        assert ospf.protocol == "OSPF"
        assert ospf.preference == 10
        assert ospf.cost == 2

    def test_returns_empty_for_empty_output(self):
        assert parse_routing_table("") == []

    def test_returns_empty_for_header_only(self):
        output = "Destination/Mask    Proto   Pre  Cost        NextHop         Interface\n"
        assert parse_routing_table(output) == []


class TestParseInterfaces:
    """Parse 'display interface brief' output."""

    def test_parses_five_interfaces(self):
        interfaces = parse_interfaces(SAMPLE_INTERFACES)
        assert len(interfaces) == 5

    def test_parses_ethernet_interface(self):
        interfaces = parse_interfaces(SAMPLE_INTERFACES)
        eth = interfaces[0]
        assert eth.name == "GigabitEthernet0/0/0"
        assert eth.status == "up"
        assert eth.protocol_status == "up"

    def test_parses_down_interface(self):
        interfaces = parse_interfaces(SAMPLE_INTERFACES)
        down = interfaces[2]
        assert down.name == "GigabitEthernet0/0/2"
        assert down.status == "down"

    def test_parses_loopback(self):
        interfaces = parse_interfaces(SAMPLE_INTERFACES)
        lo = interfaces[3]
        assert lo.name == "LoopBack0"
        assert lo.status == "up"
        assert lo.protocol_status == "up"

    def test_returns_empty_for_empty_output(self):
        assert parse_interfaces("") == []


class TestParseArpTable:
    """Parse 'display arp' output."""

    def test_parses_four_entries(self):
        entries = parse_arp_table(SAMPLE_ARP_TABLE)
        assert len(entries) == 4

    def test_parses_ip_and_mac(self):
        entries = parse_arp_table(SAMPLE_ARP_TABLE)
        first = entries[0]
        assert first.ip_address == "10.10.10.1"
        assert first.mac_address == "aabb-cc01-0101"
        assert first.interface == "GE0/0/0"
        assert first.status == "D"

    def test_returns_empty_for_empty_output(self):
        assert parse_arp_table("") == []


class TestParseVlans:
    """Parse 'display vlan' output."""

    def test_parses_four_vlans(self):
        vlans = parse_vlans(SAMPLE_VLANS)
        assert len(vlans) == 4

    def test_parses_vlan_1(self):
        vlans = parse_vlans(SAMPLE_VLANS)
        v1 = vlans[0]
        assert v1.vlan_id == 1
        assert v1.name == "default"
        assert v1.status == "up"
        assert v1.ports == ["GE0/0/0", "GE0/0/1"]

    def test_parses_vlan_with_single_port(self):
        vlans = parse_vlans(SAMPLE_VLANS)
        v10 = vlans[1]
        assert v10.vlan_id == 10
        assert v10.name == "management"
        assert v10.ports == ["GE0/0/0"]

    def test_parses_down_vlan(self):
        vlans = parse_vlans(SAMPLE_VLANS)
        v100 = vlans[3]
        assert v100.vlan_id == 100
        assert v100.status == "down"

    def test_returns_empty_for_empty_output(self):
        assert parse_vlans("") == []
