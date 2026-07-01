"""Normalizer — Parse de outputs CLI Huawei para dados estruturados.

Cada parser recebe o output bruto de um comando show e retorna uma
lista de dataclasses tipadas. Usado pelo ControllerCore para transformar
respostas textuais em objetos consultaveis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ── Dataclasses de saída ────────────────────────────────────────────────────


@dataclass
class RouteEntry:
    """Entrada de tabela de roteamento."""

    destination: str
    mask: str
    next_hop: str
    interface: str
    protocol: str
    preference: int
    cost: int


@dataclass
class InterfaceEntry:
    """Entrada de interface de rede."""

    name: str
    status: str
    protocol_status: str


@dataclass
class ArpEntry:
    """Entrada de tabela ARP."""

    ip_address: str
    mac_address: str
    interface: str
    status: str


@dataclass
class VlanEntry:
    """Entrada de VLAN."""

    vlan_id: int
    name: str
    status: str
    ports: list[str]


# ── Routing table ───────────────────────────────────────────────────────────

_ROUTE_RE = re.compile(
    r"^\s+"
    r"(\S+)/(\d+)\s+"  # destination/mask
    r"(\S+)\s+"        # protocol
    r"(\d+)\s+"        # preference
    r"(\d+)\s+"        # cost
    r"(\S+)\s+"        # next-hop
    r"(\S+)"           # interface
)


def parse_routing_table(output: str) -> list[RouteEntry]:
    """Parse output de ``display ip routing-table``.

    Extrai linhas do formato::

        Destination/Mask    Proto   Pre  Cost        NextHop         Interface
          0.0.0.0/0         Static  60   0          10.10.10.1      GE0/0/0
    """
    entries: list[RouteEntry] = []
    for line in output.splitlines():
        m = _ROUTE_RE.match(line)
        if not m:
            continue
        entries.append(
            RouteEntry(
                destination=m.group(1),
                mask=m.group(2),
                next_hop=m.group(6),
                interface=m.group(7),
                protocol=m.group(3),
                preference=int(m.group(4)),
                cost=int(m.group(5)),
            )
        )
    return entries


# ── Interfaces ──────────────────────────────────────────────────────────────

_INTF_RE = re.compile(
    r"^(\S+)\s+(\S+)\s+(\S+)"  # name, PHY, Protocol
)


def parse_interfaces(output: str) -> list[InterfaceEntry]:
    """Parse output de ``display interface brief``.

    Extrai linhas do formato::

        Interface                   PHY  Protocol
        GigabitEthernet0/0/0        up    up
    """
    entries: list[InterfaceEntry] = []
    # Pula linhas de legenda (PHY, *down, etc.)
    in_table = False
    for line in output.splitlines():
        if line.startswith("Interface"):
            in_table = True
            continue
        if not in_table or not line.strip():
            continue
        m = _INTF_RE.match(line)
        if not m:
            continue
        # Remove flags como (s), (l) do protocol status
        proto = m.group(3).split("(")[0]
        entries.append(
            InterfaceEntry(
                name=m.group(1),
                status=m.group(2),
                protocol_status=proto,
            )
        )
    return entries


# ── ARP table ───────────────────────────────────────────────────────────────

_ARP_RE = re.compile(
    r"^(\S+)\s+(\S+)\s+\S+\s+(\S+)\s+(\S+)"  # IP, MAC, type, interface
)


def parse_arp_table(output: str) -> list[ArpEntry]:
    """Parse output de ``display arp``.

    Extrai linhas do formato::

        IP ADDRESS      MAC ADDRESS    EXPIRE(M)  TYPE  INTERFACE
        10.10.10.1      aabb-cc01-0101  120        D     GE0/0/0
    """
    entries: list[ArpEntry] = []
    in_table = False
    for line in output.splitlines():
        if line.startswith("IP ADDRESS"):
            in_table = True
            continue
        if not in_table or not line.strip():
            continue
        m = _ARP_RE.match(line)
        if not m:
            continue
        entries.append(
            ArpEntry(
                ip_address=m.group(1),
                mac_address=m.group(2),
                status=m.group(3),
                interface=m.group(4),
            )
        )
    return entries


# ── VLANs ───────────────────────────────────────────────────────────────────

_VLAN_RE = re.compile(
    r"^(\d+)\s+(\S+)\s+(\S+)\s+(.+)$"  # id, name, status, port-list
)


def parse_vlans(output: str) -> list[VlanEntry]:
    """Parse output de ``display vlan``.

    Extrai linhas do formato::

        VLAN ID   Name            Status     Ports
        1         default         up         GE0/0/0 GE0/0/1
    """
    entries: list[VlanEntry] = []
    in_table = False
    for line in output.splitlines():
        if line.startswith("VLAN ID"):
            in_table = True
            continue
        if not in_table or not line.strip():
            continue
        m = _VLAN_RE.match(line)
        if not m:
            continue
        ports_str = m.group(4).strip()
        ports = ports_str.split() if ports_str else []
        entries.append(
            VlanEntry(
                vlan_id=int(m.group(1)),
                name=m.group(2),
                status=m.group(3),
                ports=ports,
            )
        )
    return entries
