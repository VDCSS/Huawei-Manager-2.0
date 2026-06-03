from __future__ import annotations

from typing import Optional

# ─── PALETA NEON ─────────────────────────────────────────────────────
BG_BASE    = "#0d0d1a"
BG_CARD    = "#13132b"
BG_SIDEBAR = "#0a0a18"
BG_INPUT   = "#1a1a30"

NEON_CYAN  = "#00e5ff"
NEON_MAG   = "#e040fb"
NEON_PURP  = "#7c4dff"
NEON_AMBER = "#ffab00"

FG_MAIN    = "#e0e0ff"
FG_DIM     = "#6a6a9a"
FG_CODE    = "#c8c8ff"

BORDER_NRM = "#2a2a4a"

THEME = {
    "BG_BASE":    BG_BASE,    "BG_CARD":    BG_CARD,
    "BG_SIDEBAR": BG_SIDEBAR, "BG_INPUT":   BG_INPUT,
    "NEON_CYAN":  NEON_CYAN,  "NEON_MAG":   NEON_MAG,
    "NEON_PURP":  NEON_PURP,  "NEON_AMBER": NEON_AMBER,
    "FG_MAIN":    FG_MAIN,    "FG_DIM":     FG_DIM,
    "FG_CODE":    FG_CODE,    "BORDER_NRM": BORDER_NRM,
}

# ─── COMANDOS CLI ────────────────────────────────────────────────────
CLI_FILTERS: dict[str, Optional[str]] = {
    "full_config": "display current-configuration",
    "interfaces": "display interface",
    "interfaces_counters": "display counters interface",
    "routing": "display ip routing-table",
    "bgp": "display bgp peer",
    "vrfs": "display ip vpn-instance",
    "ospf": "display ospf peer",
    "lldp": "display lldp neighbor brief",
    "qos": "display qos policy",
    "system_info": "display version",
    "arp": "display arp",
    "cpu_mem": "display cpu-usage",
    "huawei_bgp": "display bgp peer",
    "huawei_mpls": "display mpls ldp peer",
}

# ─── CATEGORIAS DE COMANDOS DE VISUALIZAÇÃO (aba Config) ────────────
VIEW_CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "Rede": [
        ("display ip interface brief", "display ip interface brief"),
        ("display interface brief", "display interface brief"),
        ("display ip routing-table", "display ip routing-table"),
        ("display arp", "display arp"),
        ("display mac-address", "display mac-address"),
        ("display vlan", "display vlan"),
    ],
    "Protocolos": [
        ("display ospf peer", "display ospf peer"),
        ("display bgp peer", "display bgp peer"),
        ("display isis peer", "display isis peer"),
        ("display mpls ldp peer", "display mpls ldp peer"),
        ("display ip vpn-instance", "display ip vpn-instance"),
    ],
    "Diagnostico": [
        ("display logbuffer", "display logbuffer"),
        ("display diagnostic-information", "display diagnostic-information"),
        ("display this", "display this"),
        ("display elabel", "display elabel"),
        ("display alarm active", "display alarm active"),
        ("display environment", "display environment"),
        ("display temperature", "display temperature"),
    ],
}

# ─── CATEGORIAS DE COMANDOS DE CONFIGURAÇÃO (aba Serviços) ──────────
CONFIG_CATEGORIES: dict[str, list[tuple[str, list[str]]]] = {
    "NAT": [
        ("nat outbound", [
            "nat outbound 2000 address-group 1",
            "nat outbound 3000 address-group 2"]),
        ("nat inbound", [
            "nat inbound 2000 address-group 1",
            "nat inbound 3000 address-group 2"]),
        ("nat server", [
            "nat server protocol tcp global 10.0.0.1 80 inside 192.168.1.10 80"]),
        ("nat static", [
            "nat static global 10.0.0.1 inside 192.168.1.1"]),
        ("nat address-group", [
            "nat address-group 1 10.0.0.1 10.0.0.254"]),
    ],
    "Interface": [
        ("interface GigabitEthernet", [
            "interface GigabitEthernet0/0/0",
            "interface GigabitEthernet0/0/1"]),
        ("ip address", [
            "ip address 10.0.0.1 255.255.255.0"]),
        ("description", [
            "description LINK-REDE"]),
        ("shutdown / no shutdown", [
            "shutdown",
            "undo shutdown"]),
    ],
    "ACL": [
        ("acl number", [
            "acl number 3000",
            "acl number 2000"]),
        ("rule permit/deny", [
            "rule 5 permit ip source 10.0.0.0 0.0.0.255",
            "rule 10 deny ip source 192.168.0.0 0.0.0.255"]),
    ],
    "BGP": [
        ("bgp", [
            "bgp 65000"]),
        ("router-id", [
            "router-id 1.1.1.1"]),
        ("peer", [
            "peer 10.0.0.2 as-number 65001"]),
        ("network", [
            "network 10.0.0.0 255.255.255.0"]),
    ],
    "OSPF": [
        ("ospf", [
            "ospf 1"]),
        ("area", [
            "area 0"]),
        ("network", [
            "network 10.0.0.0 0.0.0.255 area 0"]),
    ],
    "VLAN": [
        ("vlan batch", [
            "vlan batch 10 to 20"]),
        ("port link-type", [
            "port link-type trunk",
            "port link-type access"]),
        ("port default vlan", [
            "port default vlan 10"]),
    ],
}

CMD_TEMPLATES: dict[str, str] = {
    "(vazio — digite um comando)": "",
    "display device": "display device",
    "display license": "display license",
    "display logbuffer": "display logbuffer",
    "display diagnostic-information": "display diagnostic-information",
    "display this": "display this",
    "display ip interface brief": "display ip interface brief",
    "display elabel": "display elabel",
    "display alarm active": "display alarm active",
    "display environment": "display environment",
    "display temperature": "display temperature",
    "display fan": "display fan",
    "display power": "display power",
    "ping": "ping 10.0.0.1",
    "tracert": "tracert 10.0.0.1",
    "sysname": "sysname ROTEADOR-MEU",
    "commit": "commit",
    "interface GigabitEthernet": "interface GigabitEthernet0/0/0",
    "interface NULL 0": "interface NULL 0",
    "reset counters interface": "reset counters interface GigabitEthernet0/0/0",
    "display current-configuration": "display current-configuration",
}
