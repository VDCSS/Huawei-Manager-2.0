#!/usr/bin/env python3
"""
services.py — Catálogo de Serviços por Tipo de VNF
====================================================
Define todos os serviços disponíveis para cada tipo de dispositivo,
com suporte a execução via Netmiko (CLI) ou modo mock.

Uso:
    from services import get_services_for, execute_service
    svcs = get_services_for("ROUTER", category="routing")
    result = execute_service(svcs[0], session_type="cli", session=netmiko_connection)
"""
from __future__ import annotations

import io
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from huawei_manager.utils import clean_output

log = logging.getLogger("huawei.services")

# ── Tipos suportados ──────────────────────────────────────────────────
VNF_TYPES = {
    "ROUTER":         "Roteador",
    "SWITCH":         "Switch",
    "FIREWALL":       "Firewall",
    "LOAD-BALANCER":  "Balanceador de Carga",
    "WAN-ACCEL":      "Acelerador WAN",
    "AP":             "Access Point / Controladora WiFi",
}

VNF_CATEGORIES = {
    "ROUTER": [
        "routing", "bgp", "ospf", "isis", "mpls", "interface",
        "vrf", "qos", "acl", "nat", "system", "security", "troubleshoot",
        "config-nat", "config-interface", "config-acl",
        "config-bgp", "config-ospf", "config-vlan",
    ],
    "SWITCH": [
        "vlan", "stp", "lacp", "mac", "lldp", "poe", "igmp",
        "dhcp", "interface", "security", "system", "troubleshoot",
    ],
    "FIREWALL": [
        "policy", "nat", "vpn", "ips", "antivirus", "url-filter",
        "zone", "ha", "system", "troubleshoot",
    ],
    "LOAD-BALANCER": [
        "slb", "health", "statistics", "system", "troubleshoot",
    ],
    "WAN-ACCEL": [
        "optimization", "statistics", "system", "troubleshoot",
    ],
    "AP": [
        "wireless", "client", "radio", "system", "troubleshoot",
    ],
}


# ═══════════════════════════════════════════════════════════════════════
#  SERVICE DATACLASS
# ═══════════════════════════════════════════════════════════════════════
@dataclass
class ServiceDef:
    id: str
    name: str
    description: str
    category: str
    vnf_types: list[str]
    cli_commands: list[str] = field(default_factory=list)
    yang_filter: Optional[str] = None
    yang_source: str = "get"
    output_format: str = "text"
    requires_privilege: bool = False
    config_mode: bool = False

    def cli(self) -> str:
        return "; ".join(self.cli_commands)


# ═══════════════════════════════════════════════════════════════════════
#  CATÁLOGO COMPLETO DE SERVIÇOS
# ═══════════════════════════════════════════════════════════════════════

SERVICE_REGISTRY: list[ServiceDef] = [
    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ROUTER — Roteamento                                           ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="router-routing-table", name="Tabela de Roteamento",
               description="display ip routing-table",
               category="routing", vnf_types=["ROUTER"],
               cli_commands=["display ip routing-table"]),
    ServiceDef(id="router-routing-table-verbose", name="Roteamento (detalhado)",
               description="display ip routing-table verbose",
               category="routing", vnf_types=["ROUTER"],
               cli_commands=["display ip routing-table verbose"]),
    ServiceDef(id="router-routing-table-stats", name="Estatísticas de Roteamento",
               description="display ip routing-table statistics",
               category="routing", vnf_types=["ROUTER"],
               cli_commands=["display ip routing-table statistics"]),
    ServiceDef(id="router-fib", name="Tabela FIB",
               description="display fib",
               category="routing", vnf_types=["ROUTER"],
               cli_commands=["display fib"]),
    ServiceDef(id="router-route-policy", name="Route Policy",
               description="display route-policy",
               category="routing", vnf_types=["ROUTER"],
               cli_commands=["display route-policy"]),

    # ── ROUTER — BGP ──────────────────────────────────────────────────
    ServiceDef(id="router-bgp-summary", name="BGP Sumário",
               description="display bgp peer",
               category="bgp", vnf_types=["ROUTER"],
               cli_commands=["display bgp peer"]),
    ServiceDef(id="router-bgp-routes", name="BGP Rotas",
               description="display bgp routing-table",
               category="bgp", vnf_types=["ROUTER"],
               cli_commands=["display bgp routing-table"]),
    ServiceDef(id="router-bgp-community", name="BGP Community",
               description="display bgp routing-table community",
               category="bgp", vnf_types=["ROUTER"],
               cli_commands=["display bgp routing-table community"]),
    ServiceDef(id="router-bgp-vpnv4", name="BGP VPNv4",
               description="display bgp vpnv4 all peer",
               category="bgp", vnf_types=["ROUTER"],
               cli_commands=["display bgp vpnv4 all peer"]),
    ServiceDef(id="router-bgp-vpnv6", name="BGP VPNv6",
               description="display bgp vpnv6 all peer",
               category="bgp", vnf_types=["ROUTER"],
               cli_commands=["display bgp vpnv6 all peer"]),

    # ── ROUTER — OSPF ─────────────────────────────────────────────────
    ServiceDef(id="router-ospf-peer", name="OSPF Vizinhos",
               description="display ospf peer",
               category="ospf", vnf_types=["ROUTER"],
               cli_commands=["display ospf peer"]),
    ServiceDef(id="router-ospf-routes", name="OSPF Rotas",
               description="display ospf routing-table",
               category="ospf", vnf_types=["ROUTER"],
               cli_commands=["display ospf routing-table"]),
    ServiceDef(id="router-ospf-lsdb", name="OSPF LSDB",
               description="display ospf lsdb",
               category="ospf", vnf_types=["ROUTER"],
               cli_commands=["display ospf lsdb"]),
    ServiceDef(id="router-ospf-interface", name="OSPF Interfaces",
               description="display ospf interface",
               category="ospf", vnf_types=["ROUTER"],
               cli_commands=["display ospf interface"]),
    ServiceDef(id="router-ospf-error", name="OSPF Erros / Contadores",
               description="display ospf error",
               category="ospf", vnf_types=["ROUTER"],
               cli_commands=["display ospf error"]),

    # ── ROUTER — IS-IS ────────────────────────────────────────────────
    ServiceDef(id="router-isis-peer", name="IS-IS Vizinhos",
               description="display isis peer",
               category="isis", vnf_types=["ROUTER"],
               cli_commands=["display isis peer"]),
    ServiceDef(id="router-isis-lsdb", name="IS-IS LSDB",
               description="display isis lsdb",
               category="isis", vnf_types=["ROUTER"],
               cli_commands=["display isis lsdb"]),
    ServiceDef(id="router-isis-route", name="IS-IS Rotas",
               description="display isis routing-table",
               category="isis", vnf_types=["ROUTER"],
               cli_commands=["display isis routing-table"]),

    # ── ROUTER — MPLS ─────────────────────────────────────────────────
    ServiceDef(id="router-mpls-ldp", name="MPLS LDP Sessões",
               description="display mpls ldp peer",
               category="mpls", vnf_types=["ROUTER"],
               cli_commands=["display mpls ldp peer"]),
    ServiceDef(id="router-mpls-lsp", name="MPLS LSP",
               description="display mpls lsp",
               category="mpls", vnf_types=["ROUTER"],
               cli_commands=["display mpls lsp"]),
    ServiceDef(id="router-mpls-te", name="MPLS TE Tunnel",
               description="display mpls te tunnel",
               category="mpls", vnf_types=["ROUTER"],
               cli_commands=["display mpls te tunnel"]),
    ServiceDef(id="router-mpls-vpn", name="MPLS L3VPN",
               description="display ip vpn-instance",
               category="mpls", vnf_types=["ROUTER"],
               cli_commands=["display ip vpn-instance"]),

    # ── ROUTER — Interface ────────────────────────────────────────────
    ServiceDef(id="router-interface-brief", name="Sumário de Interfaces",
               description="display interface brief",
               category="interface", vnf_types=["ROUTER"],
               cli_commands=["display interface brief"]),
    ServiceDef(id="router-interface-desc", name="Descrição de Interfaces",
               description="display interface description",
               category="interface", vnf_types=["ROUTER"],
               cli_commands=["display interface description"]),
    ServiceDef(id="router-interface-ip", name="IP de Interfaces",
               description="display ip interface brief",
               category="interface", vnf_types=["ROUTER"],
               cli_commands=["display ip interface brief"]),
    ServiceDef(id="router-interface-stats", name="Estatísticas de Interface",
               description="display counters interface",
               category="interface", vnf_types=["ROUTER"],
               cli_commands=["display counters interface"]),

    # ── ROUTER — VRF ──────────────────────────────────────────────────
    ServiceDef(id="router-vrf", name="VRF Instâncias",
               description="display ip vpn-instance",
               category="vrf", vnf_types=["ROUTER"],
               cli_commands=["display ip vpn-instance"]),
    ServiceDef(id="router-vrf-route", name="Roteamento por VRF",
               description="display ip routing-table vpn-instance",
               category="vrf", vnf_types=["ROUTER"],
               cli_commands=["display ip routing-table vpn-instance"]),
    ServiceDef(id="router-vrf-brief", name="VRF Resumo",
               description="display ip vpn-instance brief",
               category="vrf", vnf_types=["ROUTER"],
               cli_commands=["display ip vpn-instance brief"]),

    # ── ROUTER — QoS ──────────────────────────────────────────────────
    ServiceDef(id="router-qos-policy", name="QoS Policy",
               description="display qos policy",
               category="qos", vnf_types=["ROUTER"],
               cli_commands=["display qos policy"]),
    ServiceDef(id="router-qos-queue", name="QoS Filas",
               description="display qos queue statistics",
               category="qos", vnf_types=["ROUTER"],
               cli_commands=["display qos queue statistics"]),
    ServiceDef(id="router-qos-cir", name="QoS CIR/PIR",
               description="display qos car",
               category="qos", vnf_types=["ROUTER"],
               cli_commands=["display qos car"]),

    # ── ROUTER — ACL ──────────────────────────────────────────────────
    ServiceDef(id="router-acl", name="ACLs",
               description="display acl all",
               category="acl", vnf_types=["ROUTER"],
               cli_commands=["display acl all"]),

    # ── ROUTER — NAT ──────────────────────────────────────────────────
    ServiceDef(id="router-nat-session", name="Sessões NAT",
               description="display nat session",
               category="nat", vnf_types=["ROUTER"],
               cli_commands=["display nat session"]),
    ServiceDef(id="router-nat-rule", name="Regras NAT",
               description="display nat outbound",
               category="nat", vnf_types=["ROUTER"],
               cli_commands=["display nat outbound"]),
    ServiceDef(id="router-nat-server", name="NAT Server",
               description="display nat server",
               category="nat", vnf_types=["ROUTER"],
               cli_commands=["display nat server"]),

    # ── ROUTER — Segurança ────────────────────────────────────────────
    ServiceDef(id="router-vrrp", name="VRRP Status",
               description="display vrrp",
               category="security", vnf_types=["ROUTER"],
               cli_commands=["display vrrp"]),
    ServiceDef(id="router-bfd", name="BFD Sessões",
               description="display bfd session",
               category="security", vnf_types=["ROUTER"],
               cli_commands=["display bfd session"]),
    ServiceDef(id="router-nqa", name="NQA Resultados",
               description="display nqa results",
               category="troubleshoot", vnf_types=["ROUTER"],
               cli_commands=["display nqa results"]),

    # ── ROUTER — Troubleshooting ──────────────────────────────────────
    ServiceDef(id="router-ping", name="Ping",
               description="ping diagnóstico",
               category="troubleshoot", vnf_types=["ROUTER"],
               cli_commands=["ping 10.0.0.1"]),
    ServiceDef(id="router-tracert", name="Traceroute",
               description="tracert diagnóstico",
               category="troubleshoot", vnf_types=["ROUTER"],
               cli_commands=["tracert 10.0.0.1"]),
    ServiceDef(id="router-log", name="Log do Sistema",
               description="display logbuffer",
               category="troubleshoot", vnf_types=["ROUTER"],
               cli_commands=["display logbuffer"]),
    ServiceDef(id="router-debug", name="Debug Info",
               description="display debugging",
               category="troubleshoot", vnf_types=["ROUTER"],
               cli_commands=["display debugging"]),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ROUTER — Config Mode — NAT                                    ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="router-config-nat-outbound", name="NAT Outbound",
               description="nat outbound <acl> address-group <id>",
               category="config-nat", vnf_types=["ROUTER"],
               cli_commands=["nat outbound 2000 address-group 1"],
               config_mode=True),
    ServiceDef(id="router-config-nat-inbound", name="NAT Inbound",
               description="nat inbound <acl> address-group <id>",
               category="config-nat", vnf_types=["ROUTER"],
               cli_commands=["nat inbound 3000 address-group 1"],
               config_mode=True),
    ServiceDef(id="router-config-nat-server", name="NAT Server",
               description="nat server protocol tcp global <ip> <port> inside <ip> <port>",
               category="config-nat", vnf_types=["ROUTER"],
               cli_commands=["nat server protocol tcp global 10.0.0.1 80 inside 192.168.1.10 80"],
               config_mode=True),
    ServiceDef(id="router-config-nat-static", name="NAT Static",
               description="nat static global <ip> inside <ip>",
               category="config-nat", vnf_types=["ROUTER"],
               cli_commands=["nat static global 10.0.0.1 inside 192.168.1.1"],
               config_mode=True),
    ServiceDef(id="router-config-nat-address-group", name="NAT Address-Group",
               description="nat address-group <id> <start> <end>",
               category="config-nat", vnf_types=["ROUTER"],
               cli_commands=["nat address-group 1 10.0.0.1 10.0.0.254"],
               config_mode=True),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ROUTER — Config Mode — Interface                              ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="router-config-interface", name="Interface GigabitEthernet",
               description="interface GigabitEthernet <x/x/x>",
               category="config-interface", vnf_types=["ROUTER"],
               cli_commands=["interface GigabitEthernet0/0/0"],
               config_mode=True),
    ServiceDef(id="router-config-ip-address", name="IP Address",
               description="ip address <ip> <mask>",
               category="config-interface", vnf_types=["ROUTER"],
               cli_commands=["ip address 10.0.0.1 255.255.255.0"],
               config_mode=True),
    ServiceDef(id="router-config-description", name="Description",
               description="description <text>",
               category="config-interface", vnf_types=["ROUTER"],
               cli_commands=["description LINK-REDE"],
               config_mode=True),
    ServiceDef(id="router-config-shutdown", name="Shutdown / No Shutdown",
               description="shutdown | undo shutdown",
               category="config-interface", vnf_types=["ROUTER"],
               cli_commands=["shutdown"],
               config_mode=True),
    ServiceDef(id="router-config-undo-shutdown", name="Undo Shutdown",
               description="undo shutdown",
               category="config-interface", vnf_types=["ROUTER"],
               cli_commands=["undo shutdown"],
               config_mode=True),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ROUTER — Config Mode — ACL                                    ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="router-config-acl-number", name="ACL Number",
               description="acl number <id>",
               category="config-acl", vnf_types=["ROUTER"],
               cli_commands=["acl number 3000"],
               config_mode=True),
    ServiceDef(id="router-config-acl-rule", name="ACL Rule",
               description="rule <id> permit/deny ip source <ip> <wildcard>",
               category="config-acl", vnf_types=["ROUTER"],
               cli_commands=["rule 5 permit ip source 10.0.0.0 0.0.0.255"],
               config_mode=True),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ROUTER — Config Mode — BGP                                    ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="router-config-bgp", name="BGP",
               description="bgp <asn>",
               category="config-bgp", vnf_types=["ROUTER"],
               cli_commands=["bgp 65000"],
               config_mode=True),
    ServiceDef(id="router-config-bgp-router-id", name="BGP Router-ID",
               description="router-id <id>",
               category="config-bgp", vnf_types=["ROUTER"],
               cli_commands=["router-id 1.1.1.1"],
               config_mode=True),
    ServiceDef(id="router-config-bgp-peer", name="BGP Peer",
               description="peer <ip> as-number <asn>",
               category="config-bgp", vnf_types=["ROUTER"],
               cli_commands=["peer 10.0.0.2 as-number 65001"],
               config_mode=True),
    ServiceDef(id="router-config-bgp-network", name="BGP Network",
               description="network <prefix>",
               category="config-bgp", vnf_types=["ROUTER"],
               cli_commands=["network 10.0.0.0 255.255.255.0"],
               config_mode=True),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ROUTER — Config Mode — OSPF                                   ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="router-config-ospf", name="OSPF",
               description="ospf <id>",
               category="config-ospf", vnf_types=["ROUTER"],
               cli_commands=["ospf 1"],
               config_mode=True),
    ServiceDef(id="router-config-ospf-area", name="OSPF Area",
               description="area <id>",
               category="config-ospf", vnf_types=["ROUTER"],
               cli_commands=["area 0"],
               config_mode=True),
    ServiceDef(id="router-config-ospf-network", name="OSPF Network",
               description="network <prefix> <wildcard> area <id>",
               category="config-ospf", vnf_types=["ROUTER"],
               cli_commands=["network 10.0.0.0 0.0.0.255 area 0"],
               config_mode=True),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  ROUTER — Config Mode — VLAN                                   ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="router-config-vlan-batch", name="VLAN Batch",
               description="vlan batch <start> to <end>",
               category="config-vlan", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["vlan batch 10 to 20"],
               config_mode=True),
    ServiceDef(id="router-config-vlan-port-type", name="Port Link-Type",
               description="port link-type <access|trunk|hybrid>",
               category="config-vlan", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["port link-type trunk"],
               config_mode=True),
    ServiceDef(id="router-config-vlan-default", name="Port Default VLAN",
               description="port default vlan <id>",
               category="config-vlan", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["port default vlan 10"],
               config_mode=True),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  SWITCH — VLAN                                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="switch-vlan", name="VLANs",
               description="display vlan",
               category="vlan", vnf_types=["SWITCH"],
               cli_commands=["display vlan"]),
    ServiceDef(id="switch-vlan-all", name="Todas as VLANs",
               description="display vlan all",
               category="vlan", vnf_types=["SWITCH"],
               cli_commands=["display vlan all"]),
    ServiceDef(id="switch-vlan-if", name="Interface VLAN",
               description="display vlan brief",
               category="vlan", vnf_types=["SWITCH"],
               cli_commands=["display vlan brief"]),

    # ── SWITCH — STP ──────────────────────────────────────────────────
    ServiceDef(id="switch-stp", name="STP Status",
               description="display stp brief",
               category="stp", vnf_types=["SWITCH"],
               cli_commands=["display stp brief"]),
    ServiceDef(id="switch-stp-detail", name="STP Detalhado",
               description="display stp",
               category="stp", vnf_types=["SWITCH"],
               cli_commands=["display stp"]),
    ServiceDef(id="switch-rstp", name="RSTP/MSTP",
               description="display stp region-configuration",
               category="stp", vnf_types=["SWITCH"],
               cli_commands=["display stp region-configuration"]),

    # ── SWITCH — LACP / Link Aggregation ──────────────────────────────
    ServiceDef(id="switch-lacp", name="Link Aggregation",
               description="display link-aggregation summary",
               category="lacp", vnf_types=["SWITCH"],
               cli_commands=["display link-aggregation summary"]),
    ServiceDef(id="switch-lacp-verbose", name="LACP Detalhado",
               description="display link-aggregation verbose",
               category="lacp", vnf_types=["SWITCH"],
               cli_commands=["display link-aggregation verbose"]),

    # ── SWITCH — MAC Table ────────────────────────────────────────────
    ServiceDef(id="switch-mac", name="Tabela MAC",
               description="display mac-address",
               category="mac", vnf_types=["SWITCH"],
               cli_commands=["display mac-address"]),
    ServiceDef(id="switch-mac-dynamic", name="MAC Dinâmicas",
               description="display mac-address dynamic",
               category="mac", vnf_types=["SWITCH"],
               cli_commands=["display mac-address dynamic"]),
    ServiceDef(id="switch-mac-static", name="MAC Estáticas",
               description="display mac-address static",
               category="mac", vnf_types=["SWITCH"],
               cli_commands=["display mac-address static"]),

    # ── SWITCH — LLDP ─────────────────────────────────────────────────
    ServiceDef(id="switch-lldp", name="LLDP Vizinhos",
               description="display lldp neighbor brief",
               category="lldp", vnf_types=["SWITCH"],
               cli_commands=["display lldp neighbor brief"]),
    ServiceDef(id="switch-lldp-all", name="LLDP Todos",
               description="display lldp neighbor",
               category="lldp", vnf_types=["SWITCH"],
               cli_commands=["display lldp neighbor"]),

    # ── SWITCH — PoE ──────────────────────────────────────────────────
    ServiceDef(id="switch-poe", name="PoE Status",
               description="display poe power-state",
               category="poe", vnf_types=["SWITCH"],
               cli_commands=["display poe power-state"]),
    ServiceDef(id="switch-poe-detail", name="PoE Detalhado",
               description="display poe power-state interface",
               category="poe", vnf_types=["SWITCH"],
               cli_commands=["display poe power-state interface"]),

    # ── SWITCH — IGMP Snooping ────────────────────────────────────────
    ServiceDef(id="switch-igmp", name="IGMP Snooping",
               description="display igmp-snooping",
               category="igmp", vnf_types=["SWITCH"],
               cli_commands=["display igmp-snooping"]),

    # ── SWITCH — DHCP Snooping ────────────────────────────────────────
    ServiceDef(id="switch-dhcp-snoop", name="DHCP Snooping",
               description="display dhcp snooping",
               category="dhcp", vnf_types=["SWITCH"],
               cli_commands=["display dhcp snooping"]),

    # ── SWITCH — Interface ────────────────────────────────────────────
    ServiceDef(id="switch-int-brief", name="Sumário de Interfaces",
               description="display interface brief",
               category="interface", vnf_types=["SWITCH"],
               cli_commands=["display interface brief"]),
    ServiceDef(id="switch-int-desc", name="Descrição Interfaces",
               description="display interface description",
               category="interface", vnf_types=["SWITCH"],
               cli_commands=["display interface description"]),

    # ── SWITCH — Segurança ────────────────────────────────────────────
    ServiceDef(id="switch-port-sec", name="Port Security",
               description="display port-security",
               category="security", vnf_types=["SWITCH"],
               cli_commands=["display port-security"]),
    ServiceDef(id="switch-storm", name="Storm Control",
               description="display storm-control",
               category="security", vnf_types=["SWITCH"],
               cli_commands=["display storm-control"]),
    ServiceDef(id="switch-arp", name="Tabela ARP",
               description="display arp",
               category="security", vnf_types=["SWITCH"],
               cli_commands=["display arp"]),

    # ── SWITCH — Stack ────────────────────────────────────────────────
    ServiceDef(id="switch-stack", name="Stack Info",
               description="display stack",
               category="system", vnf_types=["SWITCH"],
               cli_commands=["display stack"]),
    ServiceDef(id="switch-device", name="Info do Dispositivo",
               description="display device",
               category="system", vnf_types=["SWITCH"],
               cli_commands=["display device"]),

    # ── SWITCH — Troubleshooting ──────────────────────────────────────
    ServiceDef(id="switch-log", name="Logbuffer",
               description="display logbuffer",
               category="troubleshoot", vnf_types=["SWITCH"],
               cli_commands=["display logbuffer"]),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  FIREWALL — Policy                                             ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="fw-security-policy", name="Security Policy",
               description="display security-policy",
               category="policy", vnf_types=["FIREWALL"],
               cli_commands=["display security-policy"]),
    ServiceDef(id="fw-security-policy-stats", name="Policy Hit Count",
               description="display security-policy statistics",
               category="policy", vnf_types=["FIREWALL"],
               cli_commands=["display security-policy statistics"]),
    ServiceDef(id="fw-session-table", name="Tabela de Sessões",
               description="display firewall session table",
               category="policy", vnf_types=["FIREWALL"],
               cli_commands=["display firewall session table"]),
    ServiceDef(id="fw-session-stat", name="Estatísticas de Sessão",
               description="display firewall session statistics",
               category="policy", vnf_types=["FIREWALL"],
               cli_commands=["display firewall session statistics"]),

    # ── FIREWALL — NAT ────────────────────────────────────────────────
    ServiceDef(id="fw-nat-policy", name="NAT Policy",
               description="display nat-policy",
               category="nat", vnf_types=["FIREWALL"],
               cli_commands=["display nat-policy"]),
    ServiceDef(id="fw-nat-session", name="Sessões NAT",
               description="display nat session",
               category="nat", vnf_types=["FIREWALL"],
               cli_commands=["display nat session"]),

    # ── FIREWALL — VPN ────────────────────────────────────────────────
    ServiceDef(id="fw-ipsec", name="IPSec Policy",
               description="display ipsec policy",
               category="vpn", vnf_types=["FIREWALL"],
               cli_commands=["display ipsec policy"]),
    ServiceDef(id="fw-ike", name="IKE Proposal",
               description="display ike proposal",
               category="vpn", vnf_types=["FIREWALL"],
               cli_commands=["display ike proposal"]),
    ServiceDef(id="fw-ike-sa", name="IKE SA",
               description="display ike sa",
               category="vpn", vnf_types=["FIREWALL"],
               cli_commands=["display ike sa"]),
    ServiceDef(id="fw-ipsec-sa", name="IPSec SA",
               description="display ipsec sa",
               category="vpn", vnf_types=["FIREWALL"],
               cli_commands=["display ipsec sa"]),
    ServiceDef(id="fw-l2tp", name="L2TP Tunnel",
               description="display l2tp tunnel",
               category="vpn", vnf_types=["FIREWALL"],
               cli_commands=["display l2tp tunnel"]),
    ServiceDef(id="fw-vpn-instance", name="VPN Instâncias",
               description="display vpn-instance",
               category="vpn", vnf_types=["FIREWALL"],
               cli_commands=["display vpn-instance"]),

    # ── FIREWALL — IPS ────────────────────────────────────────────────
    ServiceDef(id="fw-ips", name="IPS Status",
               description="display ips status",
               category="ips", vnf_types=["FIREWALL"],
               cli_commands=["display ips status"]),
    ServiceDef(id="fw-ips-signature", name="IPS Assinaturas",
               description="display ips signature",
               category="ips", vnf_types=["FIREWALL"],
               cli_commands=["display ips signature"]),

    # ── FIREWALL — Antivírus ──────────────────────────────────────────
    ServiceDef(id="fw-antivirus", name="Anti-Virus Status",
               description="display antivirus status",
               category="antivirus", vnf_types=["FIREWALL"],
               cli_commands=["display antivirus status"]),

    # ── FIREWALL — URL Filter ─────────────────────────────────────────
    ServiceDef(id="fw-url-filter", name="URL Filter Stats",
               description="display url-filter statistics",
               category="url-filter", vnf_types=["FIREWALL"],
               cli_commands=["display url-filter statistics"]),

    # ── FIREWALL — Zone ───────────────────────────────────────────────
    ServiceDef(id="fw-zone", name="Zonas de Segurança",
               description="display firewall zone",
               category="zone", vnf_types=["FIREWALL"],
               cli_commands=["display firewall zone"]),

    # ── FIREWALL — HA ─────────────────────────────────────────────────
    ServiceDef(id="fw-hrp", name="HRP (HA) Status",
               description="display hrp status",
               category="ha", vnf_types=["FIREWALL"],
               cli_commands=["display hrp status"]),

    # ── FIREWALL — System ─────────────────────────────────────────────
    ServiceDef(id="fw-cpu", name="CPU Usage",
               description="display firewall cpu-usage",
               category="system", vnf_types=["FIREWALL"],
               cli_commands=["display firewall cpu-usage"]),
    ServiceDef(id="fw-mem", name="Memory Usage",
               description="display memory-usage",
               category="system", vnf_types=["FIREWALL"],
               cli_commands=["display memory-usage"]),
    ServiceDef(id="fw-context", name="Contextos (VSYS)",
               description="display switch VSYS",
               category="system", vnf_types=["FIREWALL"],
               cli_commands=["display switch VSYS"]),

    # ── FIREWALL — Troubleshoot ───────────────────────────────────────
    ServiceDef(id="fw-log", name="Logbuffer",
               description="display logbuffer",
               category="troubleshoot", vnf_types=["FIREWALL"],
               cli_commands=["display logbuffer"]),
    ServiceDef(id="fw-firewall-stat", name="Firewall Statistics",
               description="display firewall statistics",
               category="troubleshoot", vnf_types=["FIREWALL"],
               cli_commands=["display firewall statistics"]),
    ServiceDef(id="fw-interface-stat", name="Interface Stats",
               description="display interface brief",
               category="troubleshoot", vnf_types=["FIREWALL"],
               cli_commands=["display interface brief"]),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  LOAD-BALANCER                                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="slb-service-group", name="Service Groups",
               description="display slb service-group",
               category="slb", vnf_types=["LOAD-BALANCER"],
               cli_commands=["display slb service-group"]),
    ServiceDef(id="slb-virtual-server", name="Virtual Servers",
               description="display slb virtual-server",
               category="slb", vnf_types=["LOAD-BALANCER"],
               cli_commands=["display slb virtual-server"]),
    ServiceDef(id="slb-real-server", name="Real Servers",
               description="display slb real-server",
               category="slb", vnf_types=["LOAD-BALANCER"],
               cli_commands=["display slb real-server"]),
    ServiceDef(id="slb-health", name="Health Checks",
               description="display slb health",
               category="health", vnf_types=["LOAD-BALANCER"],
               cli_commands=["display slb health"]),
    ServiceDef(id="slb-stats", name="Estatísticas SLB",
               description="display slb statistics",
               category="statistics", vnf_types=["LOAD-BALANCER"],
               cli_commands=["display slb statistics"]),
    ServiceDef(id="slb-sticky", name="Sticky Sessions",
               description="display sticky",
               category="slb", vnf_types=["LOAD-BALANCER"],
               cli_commands=["display sticky"]),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  WAN-ACCEL                                                     ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="wanac-optimization", name="Otimização WAN",
               description="display wan-optimization status",
               category="optimization", vnf_types=["WAN-ACCEL"],
               cli_commands=["display wan-optimization status"]),
    ServiceDef(id="wanac-flow", name="Fluxos Ativos",
               description="display wan-optimization flow",
               category="optimization", vnf_types=["WAN-ACCEL"],
               cli_commands=["display wan-optimization flow"]),
    ServiceDef(id="wanac-compression", name="Compressão",
               description="display wan-optimization compression",
               category="optimization", vnf_types=["WAN-ACCEL"],
               cli_commands=["display wan-optimization compression"]),
    ServiceDef(id="wanac-stats", name="Estatísticas",
               description="display wan-optimization statistics",
               category="statistics", vnf_types=["WAN-ACCEL"],
               cli_commands=["display wan-optimization statistics"]),
    ServiceDef(id="wanac-interface", name="Interfaces",
               description="display interface brief",
               category="system", vnf_types=["WAN-ACCEL"],
               cli_commands=["display interface brief"]),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  AP / Wireless                                                 ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="ap-wireless", name="Status Wireless",
               description="display wireless status",
               category="wireless", vnf_types=["AP"],
               cli_commands=["display wireless status"]),
    ServiceDef(id="ap-client", name="Clientes Conectados",
               description="display station",
               category="client", vnf_types=["AP"],
               cli_commands=["display station"]),
    ServiceDef(id="ap-radio", name="Rádio Status",
               description="display radio all",
               category="radio", vnf_types=["AP"],
               cli_commands=["display radio all"]),
    ServiceDef(id="ap-ssid", name="SSIDs",
               description="display ssid",
               category="wireless", vnf_types=["AP"],
               cli_commands=["display ssid"]),
    ServiceDef(id="ap-ap-list", name="APs Gerenciados",
               description="display ap all",
               category="wireless", vnf_types=["AP"],
               cli_commands=["display ap all"]),
    ServiceDef(id="ap-int-brief", name="Interfaces",
               description="display interface brief",
               category="system", vnf_types=["AP"],
               cli_commands=["display interface brief"]),

    # ╔══════════════════════════════════════════════════════════════════╗
    # ║  COMUNS — Sistema (todos os tipos)                             ║
    # ╚══════════════════════════════════════════════════════════════════╝
    ServiceDef(id="sys-version", name="Versão do Sistema",
               description="display version",
               category="system", vnf_types=["ROUTER", "SWITCH", "FIREWALL",
                                                "LOAD-BALANCER", "WAN-ACCEL", "AP"],
               cli_commands=["display version"]),
    ServiceDef(id="sys-cpu", name="CPU Usage",
               description="display cpu-usage",
               category="system", vnf_types=["ROUTER", "SWITCH", "WAN-ACCEL", "AP"],
               cli_commands=["display cpu-usage"]),
    ServiceDef(id="sys-mem", name="Memory Usage",
               description="display memory-usage",
               category="system", vnf_types=["ROUTER", "SWITCH", "WAN-ACCEL", "AP"],
               cli_commands=["display memory-usage"]),
    ServiceDef(id="sys-date", name="Relógio do Sistema",
               description="display clock",
               category="system", vnf_types=["ROUTER", "SWITCH", "FIREWALL",
                                                "LOAD-BALANCER", "WAN-ACCEL", "AP"],
               cli_commands=["display clock"]),
    ServiceDef(id="sys-uptime", name="Uptime",
               description="display system uptime",
               category="system", vnf_types=["ROUTER", "SWITCH", "FIREWALL",
                                                "LOAD-BALANCER", "WAN-ACCEL", "AP"],
               cli_commands=["display system uptime"]),
    ServiceDef(id="sys-config", name="Configuração Atual",
               description="display current-configuration",
               category="system", vnf_types=["ROUTER", "SWITCH", "FIREWALL",
                                                "LOAD-BALANCER", "WAN-ACCEL", "AP"],
               cli_commands=["display current-configuration"]),
    ServiceDef(id="sys-config-last", name="Últimas Alterações",
               description="display current-configuration | include sysname",
               category="system", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["display current-configuration | include sysname"]),
    ServiceDef(id="sys-diagnose", name="Diagnóstico do Sistema",
               description="display diagnostic-information",
               category="troubleshoot", vnf_types=["ROUTER", "SWITCH", "FIREWALL",
                                                     "LOAD-BALANCER", "WAN-ACCEL", "AP"],
               cli_commands=["display diagnostic-information"]),
    ServiceDef(id="sys-license", name="Licenças",
               description="display license",
               category="system", vnf_types=["ROUTER", "SWITCH", "FIREWALL"],
               cli_commands=["display license"]),
    ServiceDef(id="sys-hardware", name="Hardware",
               description="display device hardware",
               category="system", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["display device hardware"]),
    ServiceDef(id="sys-power", name="Fonte de Alimentação",
               description="display power",
               category="system", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["display power"]),
    ServiceDef(id="sys-fan", name="Ventoinhas",
               description="display fan",
               category="system", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["display fan"]),
    ServiceDef(id="sys-temperature", name="Temperatura",
               description="display temperature all",
               category="system", vnf_types=["ROUTER", "SWITCH"],
               cli_commands=["display temperature all"]),
]


# ═══════════════════════════════════════════════════════════════════════
#  SERVICE ACCESS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def get_services_for(vnf_type: str, category: Optional[str] = None) -> list[ServiceDef]:
    """Retorna serviços disponíveis para um tipo de VNF, opcionalmente filtrados por categoria."""
    results = [s for s in SERVICE_REGISTRY if vnf_type.upper() in s.vnf_types]
    if category:
        results = [s for s in results if s.category == category]
    return results


def get_categories_for(vnf_type: str) -> list[str]:
    """Retorna categorias disponíveis para um tipo de VNF."""
    from collections import OrderedDict
    cats = OrderedDict()
    for s in SERVICE_REGISTRY:
        if vnf_type.upper() in s.vnf_types:
            cats[s.category] = True
    return list(cats.keys())


def get_service_by_id(svc_id: str) -> Optional[ServiceDef]:
    """Busca um serviço pelo ID."""
    for s in SERVICE_REGISTRY:
        if s.id == svc_id:
            return s
    return None


# ═══════════════════════════════════════════════════════════════════════
#  EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════════════
def execute_service(
    service: ServiceDef,
    session_type: str = "mock",
    session=None,
    **kwargs,
) -> str:
    """
    Executa um serviço no dispositivo alvo via Netmiko.

    Args:
        service: Definição do serviço
        session_type: 'mock' | 'cli' (ambos usam Netmiko CLI)
        session: Conexão Netmiko
        **kwargs: Argumentos adicionais

    Returns:
        str: Resultado formatado
    """
    if session_type == "mock":
        return _execute_mock(service)
    return _execute_cli(service, session, **kwargs)


def _execute_mock(service: ServiceDef) -> str:
    """Gera dados simulados para demonstração sem dispositivo real."""
    buf = io.StringIO()
    buf.write(f"{'=' * 70}\n")
    buf.write(f"  {service.name}\n")
    buf.write(f"  {service.description}\n")
    buf.write(f"{'=' * 70}\n\n")

    mock_data = _generate_mock_output(service)
    buf.write(mock_data)
    buf.write(f"\n{'─' * 70}\n")
    buf.write("  [MODO MOCK] Dados simulados — sem dispositivo real\n")
    buf.write(f"  [{datetime.now(timezone.utc).isoformat()}]\n")
    return buf.getvalue()


def _generate_mock_output(service: ServiceDef) -> str:
    """Gera saída simulada baseada no tipo/categoria do serviço."""
    svc_id = service.id
    name = service.name
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    templates = {
        # ── ROUTER ────────────────────────────────────────────────
        "router-routing-table": f"""Protocolo  Pref   Destino               Próximo Hop        Interface
  OSPF     10     10.0.1.0/24          10.0.0.2           GigabitEthernet0/0/1
  OSPF     10     10.0.2.0/24          10.0.0.3           GigabitEthernet0/0/2
  BGP      256    192.168.0.0/16       10.0.0.254         GigabitEthernet0/0/0
  Static   60     172.16.0.0/12        10.0.0.1           GigabitEthernet0/0/0
  Direct   0      10.0.0.0/24          10.0.0.1           GigabitEthernet0/0/0
  Direct   0      192.168.1.0/24       192.168.1.1        GigabitEthernet0/0/3

Total: 6 rotas, 4 protocolos""",

        "router-bgp-summary": f"""BGP local router ID : 192.168.1.1
Local AS number    : 65001
Total peers        : 3
Peers in established: 2

  Peer          AS     MsgRcvd  MsgSent  Up/Down    State
  10.0.0.254    65000  124580   112450   02:15:30   Established
  10.0.1.254    65002  45890    46780    01:45:22   Established
  192.168.2.1   65100  0        0        00:00:05   Active""",

        "router-bgp-routes": f"""BGP Local router ID: 192.168.1.1
  Network            NextHop        MED        LocPrf    PrefVal Path/Ogn
*> 10.10.0.0/16      10.0.0.254               0                  65000i
*> 10.20.0.0/16      10.0.0.254               0                  65000 65100i
*> 172.16.0.0/12     10.0.1.254               0                  65002i
*> 192.168.0.0/16    10.0.0.254               100                65000i

Total number of routes: 4""",

        "router-ospf-peer": f"""OSPF Process 1 with Router ID 192.168.1.1
  Neighbor ID     Pri   State              Dead Time   Interface
  10.0.0.2        1     Full/DR            00:00:34    GigabitEthernet0/0/1
  10.0.0.3        1     Full/BDR           00:00:32    GigabitEthernet0/0/2

Area: 0.0.0.0 (Backbone)""",

        "router-mpls-lsp": f"""LSP Information:
  Tipo        Destino         InLabel  OutLabel  Interface
  Static      10.0.1.0/24     1024     2048      GE0/0/1
  LDP         10.0.2.0/24     1025     2049      GE0/0/2
  LDP         10.0.3.0/24     1026     2050      GE0/0/1
  BGP-ILABEL  192.168.0.0/16  1027     2051      GE0/0/0""",

        "router-interface-brief": f"""Interface                   IP Address        Status  Protocol
GigabitEthernet0/0/0        10.0.0.1/24       up      up
GigabitEthernet0/0/1        10.0.1.1/24       up      up
GigabitEthernet0/0/2        10.0.2.1/24       up      up
GigabitEthernet0/0/3        192.168.1.1/24    up      up
LoopBack0                    1.1.1.1/32        up      up(s)""",

        "router-vrf": f"""VPN-Instance                    RD              Interfaces
  VRF-CLIENTES               65001:100        GE0/0/3.100
  VRF-SERVIDORES             65001:200        GE0/0/3.200
  VRF-DMZ                    65001:300        GE0/0/3.300""",

        "router-nat-session": f"""NAT Session Table:
  Protocol    Source              Dest                VPN
  TCP         192.168.1.100:45000 203.0.113.5:80      VRF-CLIENTES
  TCP         192.168.1.101:45001 203.0.113.10:443    VRF-CLIENTES
  UDP         192.168.1.102:53000 8.8.8.8:53          VRF-CLIENTES

Total sessions: 1247""",

        "router-acl": f"""ACL 3000 (Advanced):
  rule 5 permit tcp 192.168.1.0 0.0.0.255 any eq 80
  rule 10 permit tcp 192.168.1.0 0.0.0.255 any eq 443
  rule 15 deny ip any any

ACL 3001 (Advanced):
  rule 5 permit ip 10.0.0.0 0.255.255.255 any""",

        # ── SWITCH ─────────────────────────────────────────────────
        "switch-vlan": f"""VLAN ID  Name                        Status
  1       default                    active
  10      CLIENTES                   active
  20      SERVIDORES                 active
  30      DMZ                        active
  100     MANAGEMENT                 active
  200     VOIP                       active""",

        "switch-stp": f"""MSTID  Port                Role  State      Cost    Priority
  0     GigabitEthernet0/0/1   ROOT  FORWARDING  20000   128
  0     GigabitEthernet0/0/2   ALTN  DISCARDING  20000   128
  0     GigabitEthernet0/0/3   DESG  FORWARDING  20000   128
  0     GigabitEthernet0/0/4   DESG  FORWARDING  20000   128""",

        "switch-lacp": f"""Interface        Bond Mode    Status
  GigabitEthernet0/0/1  Eth-Trunk1  Active  Selected
  GigabitEthernet0/0/2  Eth-Trunk1  Active  Selected
  GigabitEthernet0/0/3  Eth-Trunk2  Active  Selected
  GigabitEthernet0/0/4  Eth-Trunk2  Active  Selected

Eth-Trunk1: 2 ports, 2 Gbps, LACP mode
Eth-Trunk2: 2 ports, 2 Gbps, LACP mode""",

        "switch-mac": f"""MAC Address        VLAN  Learned-By          Interface
  0001.2345.6789     10    Dynamic             GE0/0/1
  0001.2345.6790     10    Dynamic             GE0/0/1
  0001.2345.6791     20    Dynamic             GE0/0/2
  aaaa.bbbb.cccc     100   Static              GE0/0/24

Total MAC entries: 243""",

        "switch-lldp": f"""Local Interface  Neighbor Interface  Neighbor Device
  GE0/0/1           GE0/0/3             CORE-SWITCH
  GE0/0/2           GE0/0/4             CORE-SWITCH
  GE0/0/5           GE0/0/1             ACCESS-SWITCH-F1
  GE0/0/6           GE0/0/1             ACCESS-SWITCH-F2""",

        "switch-arp": f"""ARP Table:
  IP Address        MAC Address        Interface          Type
  192.168.1.1       0001.2345.6001     GE0/0/0            static
  192.168.1.5       0001.2345.6005     GE0/0/0            dynamic
  192.168.1.10      0001.2345.6010     GE0/0/0            dynamic
  10.0.0.1          aaaa.bbbb.0001     VLAN 10            dynamic""",

        "switch-stack": f"""Stack Status: Stacking enabled
  Member ID  Role       MAC               Priority  Status
  1          Master     0001.2345.6100    150       Active
  2          Standby    0001.2345.6101    100       Active
  3          Slave      0001.2345.6102    50        Active""",

        # ── FIREWALL ───────────────────────────────────────────────
        "fw-security-policy": f"""Security Policy:
  Name               Source Zone    Dest Zone     Action  Hit
  permit-lan-wan     trust          untrust       permit  152340
  deny-wan-lan       untrust        trust         deny    45210
  permit-dmz-wan     dmz            untrust       permit  23450
  deny-all           any            any           deny    67890

Total rules: 12""",

        "fw-session-table": f"""Firewall Session Table:
  Protocol  Source:Port         Dest:Port           App       State
  TCP       192.168.1.100:35000 203.0.113.5:80      HTTP      ESTABLISHED
  TCP       192.168.1.101:35001 203.0.113.10:443    HTTPS     ESTABLISHED
  UDP       10.0.0.5:53         8.8.8.8:53          DNS       ACTIVE

Total sessions: 4520""",

        "fw-ipsec": f"""IPSec Policy: IPSEC-POLICY-1
  Profile:         PROFILE-CORP
  Mode:            Tunnel
  Local IP:        200.100.50.1
  Remote IP:       200.100.50.2
  Proposal:        esp-aes256 esp-sha256
  PFS:             dh14
  Status:          Active""",

        "fw-zone": f"""Security Zones:
  Zone            Interfaces                    Type
  trust           GE0/0/0, GE0/0/1, GE0/0/2    Layer3
  untrust         GE0/0/3                       Layer3
  dmz             GE0/0/4                       Layer3
  management      GE0/0/7                       Layer3

Total zones: 4""",

        # ── LOAD-BALANCER ──────────────────────────────────────────
        "slb-service-group": f"""SLB Service Groups:
  Name            Protocol  Type      Members
  WEB-SERVERS     TCP       http      192.168.10.10:80, 192.168.10.11:80
  APP-SERVERS     TCP       http      192.168.10.20:8080, 192.168.10.21:8080
  DB-SERVERS      TCP       mysql     192.168.10.30:3306, 192.168.10.31:3306""",

        "slb-virtual-server": f"""Virtual Servers:
  Name            VIP               Port    Type      Pool
  WEB-VIP         203.0.113.10      80/443  HTTP/HTTPS WEB-SERVERS
  APP-VIP         203.0.113.11      8080    HTTP      APP-SERVERS
  DB-VIP          10.0.0.100        3306    MySQL     DB-SERVERS""",

        # ── SYSTEM COMMON ──────────────────────────────────────────
        "sys-version": f"""Huawei Versatile Routing Platform Software
VRP (R) Software, Version 8.021
Copyright (C) 2012-2025 Huawei Technologies Co., Ltd.
  NE8000-M8  uptime: 45 days, 12 hours, 30 minutes
  Memory: 16 GB total, 12 GB free
  CPU: 8 cores @ 2.1 GHz""",

        "sys-cpu": f"""CPU Usage:
  CPU0: 12.5%
  CPU1: 8.3%
  CPU2: 15.7%
  CPU3: 5.2%
  Average: 10.4%""",

        "sys-mem": f"""Memory Usage:
  Total:  16384 MB
  Used:   4096 MB (25%)
  Free:   12288 MB (75%)""",

        "sys-temperature": f"""Temperature Information:
  Slot  Sensor         Current  Lower    Upper    Status
  1     CPU            45°C     0°C      85°C     Normal
  1     Board          38°C     0°C      75°C     Normal
  2     CPU            42°C     0°C      85°C     Normal
  2     Board          36°C     0°C      75°C     Normal""",

        # ── WIRELESS ───────────────────────────────────────────────
        "ap-client": f"""Station Information:
  MAC Address       VLAN  Radio  RSSI  SNR  Status
  aa:bb:cc:00:11:01 10    1      -45   35   Associated
  aa:bb:cc:00:11:02 10    1      -55   30   Associated
  aa:bb:cc:00:11:03 20    2      -60   28   Associated

Total stations: 3""",

        "ap-radio": f"""Radio Information:
  ID  Band           Channel  Power(dBm)  Status
  1   2.4 GHz        6        20          Active
  2   5 GHz          36       20          Active
  3   5 GHz          149      17          Active""",

        "ap-ap-list": f"""Managed APs:
  AP ID  Name          MAC               Model              Status  Users
  1      AP-F1-01      aabb.ccdd.0001    AirEngine 8760     online  12
  2      AP-F1-02      aabb.ccdd.0002    AirEngine 8760     online  8
  3      AP-F2-01      aabb.ccdd.0003    AirEngine 8760     offline 0
  4      AP-F2-02      aabb.ccdd.0004    AirEngine 8760     online  15""",

        "sys-license": f"""License Information:
  Feature             Status     Expiry
  MPLS L3VPN          Active     2026-12-31
  BGP EVPN            Active     2026-12-31
  Segment Routing     Active     2026-12-31
  NetStream           Active     2026-12-31
  VXLAN               Not Licensed""",
    }

    result = templates.get(svc_id, f"  {name} executado com sucesso.\n  Timestamp: {ts}\n  Resultado simulado para modo de demonstração.")
    return result + f"\n\n  Timestamp: {ts}"



def _execute_cli(service: ServiceDef, connection, **kwargs) -> str:
    """Executa via CLI (Netmiko)."""
    if connection is None:
        return "✘  Sem conexão CLI ativa"

    try:
        prev_mode = None
        if service.requires_privilege or service.config_mode:
            prev_mode = connection.send_command_timing("system-view")

        result_parts = []
        if service.config_mode:
            out = connection.send_config_set(service.cli_commands, read_timeout=60)
            result_parts.append(f"▶  Config applied:\n{'─' * 40}\n{clean_output(out)}")
        else:
            for cmd in service.cli_commands:
                out = connection.send_command(cmd, read_timeout=120)
                result_parts.append(f"▶  {cmd}\n{'─' * 40}\n{clean_output(out)}")

        if prev_mode is not None:
            connection.send_command_timing("quit")

        return "\n\n".join(result_parts)
    except Exception as e:
        return f"✘  Erro CLI: {e}"



