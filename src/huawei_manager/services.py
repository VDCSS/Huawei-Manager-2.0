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
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

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
    yang_filter: str | None = None
    yang_source: str = "get"
    output_format: str = "text"
    requires_privilege: bool = False
    config_mode: bool = False

    def cli(self) -> str:
        return "; ".join(self.cli_commands)


# ── factory helper ──────────────────────────────────────────────────
def _svc(id_, name, desc, cat, types, cmds=None, config=False):
    return ServiceDef(
        id=id_, name=name, description=desc,
        category=cat, vnf_types=types,
        cli_commands=cmds or [desc],
        config_mode=config,
    )

# VNF type shorthands para evitar linhas longas no catálogo
_T_ALL = ['ROUTER', 'SWITCH', 'FIREWALL', 'LOAD-BALANCER', 'WAN-ACCEL', 'AP']


# ═══════════════════════════════════════════════════════════════════════
#  CATÁLOGO COMPLETO DE SERVIÇOS
# ═══════════════════════════════════════════════════════════════════════

SERVICE_REGISTRY: list[ServiceDef] = [
    _svc('router-routing-table', 'Tabela de Roteamento', 'display ip routing-table', 'routing', ['ROUTER']),
    _svc('router-routing-table-verbose', 'Roteamento (detalhado)',
         'display ip routing-table verbose', 'routing', ['ROUTER']),
    _svc('router-routing-table-stats', 'Estatísticas de Roteamento',
         'display ip routing-table statistics', 'routing', ['ROUTER']),
    _svc('router-fib', 'Tabela FIB', 'display fib', 'routing', ['ROUTER']),
    _svc('router-route-policy', 'Route Policy', 'display route-policy', 'routing', ['ROUTER']),
    _svc('router-bgp-summary', 'BGP Sumário', 'display bgp peer', 'bgp', ['ROUTER']),
    _svc('router-bgp-routes', 'BGP Rotas', 'display bgp routing-table', 'bgp', ['ROUTER']),
    _svc('router-bgp-community', 'BGP Community', 'display bgp routing-table community', 'bgp', ['ROUTER']),
    _svc('router-bgp-vpnv4', 'BGP VPNv4', 'display bgp vpnv4 all peer', 'bgp', ['ROUTER']),
    _svc('router-bgp-vpnv6', 'BGP VPNv6', 'display bgp vpnv6 all peer', 'bgp', ['ROUTER']),
    _svc('router-ospf-peer', 'OSPF Vizinhos', 'display ospf peer', 'ospf', ['ROUTER']),
    _svc('router-ospf-routes', 'OSPF Rotas', 'display ospf routing-table', 'ospf', ['ROUTER']),
    _svc('router-ospf-lsdb', 'OSPF LSDB', 'display ospf lsdb', 'ospf', ['ROUTER']),
    _svc('router-ospf-interface', 'OSPF Interfaces', 'display ospf interface', 'ospf', ['ROUTER']),
    _svc('router-ospf-error', 'OSPF Erros / Contadores', 'display ospf error', 'ospf', ['ROUTER']),
    _svc('router-isis-peer', 'IS-IS Vizinhos', 'display isis peer', 'isis', ['ROUTER']),
    _svc('router-isis-lsdb', 'IS-IS LSDB', 'display isis lsdb', 'isis', ['ROUTER']),
    _svc('router-isis-route', 'IS-IS Rotas', 'display isis routing-table', 'isis', ['ROUTER']),
    _svc('router-mpls-ldp', 'MPLS LDP Sessões', 'display mpls ldp peer', 'mpls', ['ROUTER']),
    _svc('router-mpls-lsp', 'MPLS LSP', 'display mpls lsp', 'mpls', ['ROUTER']),
    _svc('router-mpls-te', 'MPLS TE Tunnel', 'display mpls te tunnel', 'mpls', ['ROUTER']),
    _svc('router-mpls-vpn', 'MPLS L3VPN', 'display ip vpn-instance', 'mpls', ['ROUTER']),
    _svc('router-interface-brief', 'Sumário de Interfaces', 'display interface brief', 'interface', ['ROUTER']),
    _svc('router-interface-desc', 'Descrição de Interfaces', 'display interface description', 'interface', ['ROUTER']),
    _svc('router-interface-ip', 'IP de Interfaces', 'display ip interface brief', 'interface', ['ROUTER']),
    _svc('router-interface-stats', 'Estatísticas de Interface', 'display counters interface', 'interface', ['ROUTER']),
    _svc('router-vrf', 'VRF Instâncias', 'display ip vpn-instance', 'vrf', ['ROUTER']),
    _svc('router-vrf-route', 'Roteamento por VRF', 'display ip routing-table vpn-instance', 'vrf', ['ROUTER']),
    _svc('router-vrf-brief', 'VRF Resumo', 'display ip vpn-instance brief', 'vrf', ['ROUTER']),
    _svc('router-qos-policy', 'QoS Policy', 'display qos policy', 'qos', ['ROUTER']),
    _svc('router-qos-queue', 'QoS Filas', 'display qos queue statistics', 'qos', ['ROUTER']),
    _svc('router-qos-cir', 'QoS CIR/PIR', 'display qos car', 'qos', ['ROUTER']),
    _svc('router-acl', 'ACLs', 'display acl all', 'acl', ['ROUTER']),
    _svc('router-nat-session', 'Sessões NAT', 'display nat session', 'nat', ['ROUTER']),
    _svc('router-nat-rule', 'Regras NAT', 'display nat outbound', 'nat', ['ROUTER']),
    _svc('router-nat-server', 'NAT Server', 'display nat server', 'nat', ['ROUTER']),
    _svc('router-vrrp', 'VRRP Status', 'display vrrp', 'security', ['ROUTER']),
    _svc('router-bfd', 'BFD Sessões', 'display bfd session', 'security', ['ROUTER']),
    _svc('router-nqa', 'NQA Resultados', 'display nqa results', 'troubleshoot', ['ROUTER']),
    _svc('router-ping', 'Ping', 'ping diagnóstico', 'troubleshoot', ['ROUTER'],
         cmds=['ping 10.0.0.1']),
    _svc('router-tracert', 'Traceroute', 'tracert diagnóstico', 'troubleshoot', ['ROUTER'],
         cmds=['tracert 10.0.0.1']),
    _svc('router-log', 'Log do Sistema', 'display logbuffer', 'troubleshoot', ['ROUTER']),
    _svc('router-debug', 'Debug Info', 'display debugging', 'troubleshoot', ['ROUTER']),
    _svc('router-config-nat-outbound', 'NAT Outbound',
         'nat outbound <acl> address-group <id>', 'config-nat', ['ROUTER'],
         cmds=['nat outbound 2000 address-group 1'],
         config=True),
    _svc('router-config-nat-inbound', 'NAT Inbound', 'nat inbound <acl> address-group <id>', 'config-nat', ['ROUTER'],
         cmds=['nat inbound 3000 address-group 1'],
         config=True),
    _svc('router-config-nat-server', 'NAT Server',
         'nat server protocol tcp global <ip> <port> inside <ip> <port>', 'config-nat', ['ROUTER'],
         cmds=['nat server protocol tcp global 10.0.0.1 80 inside 192.168.1.10 80'],
         config=True),
    _svc('router-config-nat-static', 'NAT Static', 'nat static global <ip> inside <ip>', 'config-nat', ['ROUTER'],
         cmds=['nat static global 10.0.0.1 inside 192.168.1.1'],
         config=True),
    _svc('router-config-nat-address-group', 'NAT Address-Group',
         'nat address-group <id> <start> <end>', 'config-nat', ['ROUTER'],
         cmds=['nat address-group 1 10.0.0.1 10.0.0.254'],
         config=True),
    _svc('router-config-interface', 'Interface GigabitEthernet',
         'interface GigabitEthernet <x/x/x>', 'config-interface', ['ROUTER'],
         cmds=['interface GigabitEthernet0/0/0'],
         config=True),
    _svc('router-config-ip-address', 'IP Address', 'ip address <ip> <mask>', 'config-interface', ['ROUTER'],
         cmds=['ip address 10.0.0.1 255.255.255.0'],
         config=True),
    _svc('router-config-description', 'Description', 'description <text>', 'config-interface', ['ROUTER'],
         cmds=['description LINK-REDE'],
         config=True),
    _svc('router-config-shutdown', 'Shutdown / No Shutdown', 'shutdown | undo shutdown', 'config-interface', ['ROUTER'],
         cmds=['shutdown'],
         config=True),
    _svc('router-config-undo-shutdown', 'Undo Shutdown', 'undo shutdown', 'config-interface', ['ROUTER'],
         config=True),
    _svc('router-config-acl-number', 'ACL Number', 'acl number <id>', 'config-acl', ['ROUTER'],
         cmds=['acl number 3000'],
         config=True),
    _svc('router-config-acl-rule', 'ACL Rule',
         'rule <id> permit/deny ip source <ip> <wildcard>', 'config-acl', ['ROUTER'],
         cmds=['rule 5 permit ip source 10.0.0.0 0.0.0.255'],
         config=True),
    _svc('router-config-bgp', 'BGP', 'bgp <asn>', 'config-bgp', ['ROUTER'],
         cmds=['bgp 65000'],
         config=True),
    _svc('router-config-bgp-router-id', 'BGP Router-ID', 'router-id <id>', 'config-bgp', ['ROUTER'],
         cmds=['router-id 1.1.1.1'],
         config=True),
    _svc('router-config-bgp-peer', 'BGP Peer', 'peer <ip> as-number <asn>', 'config-bgp', ['ROUTER'],
         cmds=['peer 10.0.0.2 as-number 65001'],
         config=True),
    _svc('router-config-bgp-network', 'BGP Network', 'network <prefix>', 'config-bgp', ['ROUTER'],
         cmds=['network 10.0.0.0 255.255.255.0'],
         config=True),
    _svc('router-config-ospf', 'OSPF', 'ospf <id>', 'config-ospf', ['ROUTER'],
         cmds=['ospf 1'],
         config=True),
    _svc('router-config-ospf-area', 'OSPF Area', 'area <id>', 'config-ospf', ['ROUTER'],
         cmds=['area 0'],
         config=True),
    _svc('router-config-ospf-network', 'OSPF Network',
         'network <prefix> <wildcard> area <id>', 'config-ospf', ['ROUTER'],
         cmds=['network 10.0.0.0 0.0.0.255 area 0'],
         config=True),
    _svc('router-config-vlan-batch', 'VLAN Batch', 'vlan batch <start> to <end>', 'config-vlan', ['ROUTER', 'SWITCH'],
         cmds=['vlan batch 10 to 20'],
         config=True),
    _svc('router-config-vlan-port-type', 'Port Link-Type',
         'port link-type <access|trunk|hybrid>', 'config-vlan', ['ROUTER', 'SWITCH'],
         cmds=['port link-type trunk'],
         config=True),
    _svc('router-config-vlan-default', 'Port Default VLAN',
         'port default vlan <id>', 'config-vlan', ['ROUTER', 'SWITCH'],
         cmds=['port default vlan 10'],
         config=True),
    _svc('switch-vlan', 'VLANs', 'display vlan', 'vlan', ['SWITCH']),
    _svc('switch-vlan-all', 'Todas as VLANs', 'display vlan all', 'vlan', ['SWITCH']),
    _svc('switch-vlan-if', 'Interface VLAN', 'display vlan brief', 'vlan', ['SWITCH']),
    _svc('switch-stp', 'STP Status', 'display stp brief', 'stp', ['SWITCH']),
    _svc('switch-stp-detail', 'STP Detalhado', 'display stp', 'stp', ['SWITCH']),
    _svc('switch-rstp', 'RSTP/MSTP', 'display stp region-configuration', 'stp', ['SWITCH']),
    _svc('switch-lacp', 'Link Aggregation', 'display link-aggregation summary', 'lacp', ['SWITCH']),
    _svc('switch-lacp-verbose', 'LACP Detalhado', 'display link-aggregation verbose', 'lacp', ['SWITCH']),
    _svc('switch-mac', 'Tabela MAC', 'display mac-address', 'mac', ['SWITCH']),
    _svc('switch-mac-dynamic', 'MAC Dinâmicas', 'display mac-address dynamic', 'mac', ['SWITCH']),
    _svc('switch-mac-static', 'MAC Estáticas', 'display mac-address static', 'mac', ['SWITCH']),
    _svc('switch-lldp', 'LLDP Vizinhos', 'display lldp neighbor brief', 'lldp', ['SWITCH']),
    _svc('switch-lldp-all', 'LLDP Todos', 'display lldp neighbor', 'lldp', ['SWITCH']),
    _svc('switch-poe', 'PoE Status', 'display poe power-state', 'poe', ['SWITCH']),
    _svc('switch-poe-detail', 'PoE Detalhado', 'display poe power-state interface', 'poe', ['SWITCH']),
    _svc('switch-igmp', 'IGMP Snooping', 'display igmp-snooping', 'igmp', ['SWITCH']),
    _svc('switch-dhcp-snoop', 'DHCP Snooping', 'display dhcp snooping', 'dhcp', ['SWITCH']),
    _svc('switch-int-brief', 'Sumário de Interfaces', 'display interface brief', 'interface', ['SWITCH']),
    _svc('switch-int-desc', 'Descrição Interfaces', 'display interface description', 'interface', ['SWITCH']),
    _svc('switch-port-sec', 'Port Security', 'display port-security', 'security', ['SWITCH']),
    _svc('switch-storm', 'Storm Control', 'display storm-control', 'security', ['SWITCH']),
    _svc('switch-arp', 'Tabela ARP', 'display arp', 'security', ['SWITCH']),
    _svc('switch-stack', 'Stack Info', 'display stack', 'system', ['SWITCH']),
    _svc('switch-device', 'Info do Dispositivo', 'display device', 'system', ['SWITCH']),
    _svc('switch-log', 'Logbuffer', 'display logbuffer', 'troubleshoot', ['SWITCH']),
    _svc('fw-security-policy', 'Security Policy', 'display security-policy', 'policy', ['FIREWALL']),
    _svc('fw-security-policy-stats', 'Policy Hit Count', 'display security-policy statistics', 'policy', ['FIREWALL']),
    _svc('fw-session-table', 'Tabela de Sessões', 'display firewall session table', 'policy', ['FIREWALL']),
    _svc('fw-session-stat', 'Estatísticas de Sessão', 'display firewall session statistics', 'policy', ['FIREWALL']),
    _svc('fw-nat-policy', 'NAT Policy', 'display nat-policy', 'nat', ['FIREWALL']),
    _svc('fw-nat-session', 'Sessões NAT', 'display nat session', 'nat', ['FIREWALL']),
    _svc('fw-ipsec', 'IPSec Policy', 'display ipsec policy', 'vpn', ['FIREWALL']),
    _svc('fw-ike', 'IKE Proposal', 'display ike proposal', 'vpn', ['FIREWALL']),
    _svc('fw-ike-sa', 'IKE SA', 'display ike sa', 'vpn', ['FIREWALL']),
    _svc('fw-ipsec-sa', 'IPSec SA', 'display ipsec sa', 'vpn', ['FIREWALL']),
    _svc('fw-l2tp', 'L2TP Tunnel', 'display l2tp tunnel', 'vpn', ['FIREWALL']),
    _svc('fw-vpn-instance', 'VPN Instâncias', 'display vpn-instance', 'vpn', ['FIREWALL']),
    _svc('fw-ips', 'IPS Status', 'display ips status', 'ips', ['FIREWALL']),
    _svc('fw-ips-signature', 'IPS Assinaturas', 'display ips signature', 'ips', ['FIREWALL']),
    _svc('fw-antivirus', 'Anti-Virus Status', 'display antivirus status', 'antivirus', ['FIREWALL']),
    _svc('fw-url-filter', 'URL Filter Stats', 'display url-filter statistics', 'url-filter', ['FIREWALL']),
    _svc('fw-zone', 'Zonas de Segurança', 'display firewall zone', 'zone', ['FIREWALL']),
    _svc('fw-hrp', 'HRP (HA) Status', 'display hrp status', 'ha', ['FIREWALL']),
    _svc('fw-cpu', 'CPU Usage', 'display firewall cpu-usage', 'system', ['FIREWALL']),
    _svc('fw-mem', 'Memory Usage', 'display memory-usage', 'system', ['FIREWALL']),
    _svc('fw-context', 'Contextos (VSYS)', 'display vsys', 'system', ['FIREWALL']),
    _svc('fw-log', 'Logbuffer', 'display logbuffer', 'troubleshoot', ['FIREWALL']),
    _svc('fw-firewall-stat', 'Firewall Statistics', 'display firewall statistics', 'troubleshoot', ['FIREWALL']),
    _svc('fw-interface-stat', 'Interface Stats', 'display interface brief', 'troubleshoot', ['FIREWALL']),
    _svc('slb-service-group', 'Service Groups', 'display slb service-group', 'slb', ['LOAD-BALANCER']),
    _svc('slb-virtual-server', 'Virtual Servers', 'display slb virtual-server', 'slb', ['LOAD-BALANCER']),
    _svc('slb-real-server', 'Real Servers', 'display slb real-server', 'slb', ['LOAD-BALANCER']),
    _svc('slb-health', 'Health Checks', 'display slb health', 'health', ['LOAD-BALANCER']),
    _svc('slb-stats', 'Estatísticas SLB', 'display slb statistics', 'statistics', ['LOAD-BALANCER']),
    _svc('slb-sticky', 'Sticky Sessions', 'display sticky', 'slb', ['LOAD-BALANCER']),
    _svc('wanac-optimization', 'Otimização WAN', 'display wan-optimization status', 'optimization', ['WAN-ACCEL']),
    _svc('wanac-flow', 'Fluxos Ativos', 'display wan-optimization flow', 'optimization', ['WAN-ACCEL']),
    _svc('wanac-compression', 'Compressão', 'display wan-optimization compression', 'optimization', ['WAN-ACCEL']),
    _svc('wanac-stats', 'Estatísticas', 'display wan-optimization statistics', 'statistics', ['WAN-ACCEL']),
    _svc('wanac-interface', 'Interfaces', 'display interface brief', 'system', ['WAN-ACCEL']),
    _svc('ap-wireless', 'Status Wireless', 'display wireless status', 'wireless', ['AP']),
    _svc('ap-client', 'Clientes Conectados', 'display station', 'client', ['AP']),
    _svc('ap-radio', 'Rádio Status', 'display radio all', 'radio', ['AP']),
    _svc('ap-ssid', 'SSIDs', 'display ssid', 'wireless', ['AP']),
    _svc('ap-ap-list', 'APs Gerenciados', 'display ap all', 'wireless', ['AP']),
    _svc('ap-int-brief', 'Interfaces', 'display interface brief', 'system', ['AP']),
    _svc('sys-version', 'Versão do Sistema', 'display version', 'system', _T_ALL),
    _svc('sys-cpu', 'CPU Usage', 'display cpu-usage', 'system', ['ROUTER', 'SWITCH', 'WAN-ACCEL', 'AP']),
    _svc('sys-mem', 'Memory Usage', 'display memory-usage', 'system', ['ROUTER', 'SWITCH', 'WAN-ACCEL', 'AP']),
    _svc('sys-date', 'Relógio do Sistema', 'display clock', 'system', _T_ALL),
    _svc('sys-uptime', 'Uptime', 'display system uptime', 'system', _T_ALL),
    _svc('sys-config', 'Configuração Atual', 'display current-configuration', 'system', _T_ALL),
    _svc('sys-config-last', 'Últimas Alterações',
         'display current-configuration | include sysname', 'system', ['ROUTER', 'SWITCH']),
    _svc('sys-diagnose', 'Diagnóstico do Sistema', 'display diagnostic-information', 'troubleshoot', _T_ALL),
    _svc('sys-license', 'Licenças', 'display license', 'system', ['ROUTER', 'SWITCH', 'FIREWALL']),
    _svc('sys-hardware', 'Hardware', 'display device', 'system', ['ROUTER', 'SWITCH']),
    _svc('sys-power', 'Fonte de Alimentação', 'display power', 'system', ['ROUTER', 'SWITCH']),
    _svc('sys-fan', 'Ventoinhas', 'display fan', 'system', ['ROUTER', 'SWITCH']),
    _svc('sys-temperature', 'Temperatura', 'display temperature all', 'system', ['ROUTER', 'SWITCH']),
]


# ═══════════════════════════════════════════════════════════════════════
#  SERVICE ACCESS FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def get_services_for(vnf_type: str, category: str | None = None) -> list[ServiceDef]:
    """Retorna serviços disponíveis para um tipo de VNF, opcionalmente filtrados por categoria."""
    results = [s for s in SERVICE_REGISTRY if vnf_type.upper() in s.vnf_types]
    if category:
        results = [s for s in results if s.category == category]
    return results


def get_categories_for(vnf_type: str) -> list[str]:
    """Retorna categorias disponíveis para um tipo de VNF."""
    cats: dict[str, bool] = {}
    for s in SERVICE_REGISTRY:
        if vnf_type.upper() in s.vnf_types:
            cats[s.category] = True
    return list(cats.keys())


def get_service_by_id(svc_id: str) -> ServiceDef | None:
    """Busca um serviço pelo ID."""
    for s in SERVICE_REGISTRY:
        if s.id == svc_id:
            return s
    return None


def get_all_show_commands() -> list[tuple[str, str]]:
    """Retorna todos os comandos SHOW únicos do catálogo, como pares (nome, comando)."""
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for svc in SERVICE_REGISTRY:
        if svc.config_mode:
            continue
        cmd = svc.cli_commands[0] if svc.cli_commands else svc.description
        if cmd not in seen:
            seen.add(cmd)
            result.append((svc.name, cmd))
    return sorted(result, key=lambda x: x[1])


def parse_params(service: ServiceDef) -> list[tuple[str, str]]:
    """Extrai pares (nome_param, valor_default) da description de um serviço config.

    Examina placeholders <nome> na description e mapeia para os valores
    correspondentes em cli_commands[0] pela posição.
    """
    params: list[tuple[str, str]] = []
    if not service.config_mode:
        return params
    desc = service.description
    default_cmd = service.cli_commands[0] if service.cli_commands else desc
    names = re.findall(r"<([^>]+)>", desc)
    if not names:
        return params
    parts = re.split(r"<[^>]+>", desc)
    tokens = default_cmd.split()
    idx = 0
    for name in names:
        label = name.replace("|", "/")
        default = ""
        template_before = parts[len(params)].strip()
        before_tokens = template_before.split() if template_before else []
        idx += len(before_tokens)
        if idx < len(tokens):
            default = tokens[idx]
            idx += 1
        params.append((label, default))
    return params


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
    buf.write(f"  [{datetime.now(UTC).isoformat()}]\n")
    return buf.getvalue()


def _generate_mock_output(service: ServiceDef) -> str:
    """Gera saída simulada baseada no tipo/categoria do serviço."""
    svc_id = service.id
    name = service.name
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    templates = {
        # ── ROUTER ────────────────────────────────────────────────
        "router-routing-table": (
            """Protocolo  Pref   Destino               Próximo Hop        Interface
  OSPF     10     10.0.1.0/24          10.0.0.2           GigabitEthernet0/0/1
  OSPF     10     10.0.2.0/24          10.0.0.3           GigabitEthernet0/0/2
  BGP      256    192.168.0.0/16       10.0.0.254         GigabitEthernet0/0/0
  Static   60     172.16.0.0/12        10.0.0.1           GigabitEthernet0/0/0
  Direct   0      10.0.0.0/24          10.0.0.1           GigabitEthernet0/0/0
  Direct   0      192.168.1.0/24       192.168.1.1        GigabitEthernet0/0/3

Total: 6 rotas, 4 protocolos"""),

        "router-bgp-summary": """BGP local router ID : 192.168.1.1
Local AS number    : 65001
Total peers        : 3
Peers in established: 2

  Peer          AS     MsgRcvd  MsgSent  Up/Down    State
  10.0.0.254    65000  124580   112450   02:15:30   Established
  10.0.1.254    65002  45890    46780    01:45:22   Established
  192.168.2.1   65100  0        0        00:00:05   Active""",

        "router-bgp-routes": """BGP Local router ID: 192.168.1.1
  Network            NextHop        MED        LocPrf    PrefVal Path/Ogn
*> 10.10.0.0/16      10.0.0.254               0                  65000i
*> 10.20.0.0/16      10.0.0.254               0                  65000 65100i
*> 172.16.0.0/12     10.0.1.254               0                  65002i
*> 192.168.0.0/16    10.0.0.254               100                65000i

Total number of routes: 4""",

        "router-ospf-peer": """OSPF Process 1 with Router ID 192.168.1.1
  Neighbor ID     Pri   State              Dead Time   Interface
  10.0.0.2        1     Full/DR            00:00:34    GigabitEthernet0/0/1
  10.0.0.3        1     Full/BDR           00:00:32    GigabitEthernet0/0/2

Area: 0.0.0.0 (Backbone)""",

        "router-mpls-lsp": """LSP Information:
  Tipo        Destino         InLabel  OutLabel  Interface
  Static      10.0.1.0/24     1024     2048      GE0/0/1
  LDP         10.0.2.0/24     1025     2049      GE0/0/2
  LDP         10.0.3.0/24     1026     2050      GE0/0/1
  BGP-ILABEL  192.168.0.0/16  1027     2051      GE0/0/0""",

        "router-interface-brief": """Interface                   IP Address        Status  Protocol
GigabitEthernet0/0/0        10.0.0.1/24       up      up
GigabitEthernet0/0/1        10.0.1.1/24       up      up
GigabitEthernet0/0/2        10.0.2.1/24       up      up
GigabitEthernet0/0/3        192.168.1.1/24    up      up
LoopBack0                    1.1.1.1/32        up      up(s)""",

        "router-vrf": """VPN-Instance                    RD              Interfaces
  VRF-CLIENTES               65001:100        GE0/0/3.100
  VRF-SERVIDORES             65001:200        GE0/0/3.200
  VRF-DMZ                    65001:300        GE0/0/3.300""",

        "router-nat-session": """NAT Session Table:
  Protocol    Source              Dest                VPN
  TCP         192.168.1.100:45000 203.0.113.5:80      VRF-CLIENTES
  TCP         192.168.1.101:45001 203.0.113.10:443    VRF-CLIENTES
  UDP         192.168.1.102:53000 8.8.8.8:53          VRF-CLIENTES

Total sessions: 1247""",

        "router-acl": """ACL 3000 (Advanced):
  rule 5 permit tcp 192.168.1.0 0.0.0.255 any eq 80
  rule 10 permit tcp 192.168.1.0 0.0.0.255 any eq 443
  rule 15 deny ip any any

ACL 3001 (Advanced):
  rule 5 permit ip 10.0.0.0 0.255.255.255 any""",

        # ── SWITCH ─────────────────────────────────────────────────
        "switch-vlan": """VLAN ID  Name                        Status
  1       default                    active
  10      CLIENTES                   active
  20      SERVIDORES                 active
  30      DMZ                        active
  100     MANAGEMENT                 active
  200     VOIP                       active""",

        "switch-stp": """MSTID  Port                Role  State      Cost    Priority
  0     GigabitEthernet0/0/1   ROOT  FORWARDING  20000   128
  0     GigabitEthernet0/0/2   ALTN  DISCARDING  20000   128
  0     GigabitEthernet0/0/3   DESG  FORWARDING  20000   128
  0     GigabitEthernet0/0/4   DESG  FORWARDING  20000   128""",

        "switch-lacp": """Interface        Bond Mode    Status
  GigabitEthernet0/0/1  Eth-Trunk1  Active  Selected
  GigabitEthernet0/0/2  Eth-Trunk1  Active  Selected
  GigabitEthernet0/0/3  Eth-Trunk2  Active  Selected
  GigabitEthernet0/0/4  Eth-Trunk2  Active  Selected

Eth-Trunk1: 2 ports, 2 Gbps, LACP mode
Eth-Trunk2: 2 ports, 2 Gbps, LACP mode""",

        "switch-mac": """MAC Address        VLAN  Learned-By          Interface
  0001.2345.6789     10    Dynamic             GE0/0/1
  0001.2345.6790     10    Dynamic             GE0/0/1
  0001.2345.6791     20    Dynamic             GE0/0/2
  aaaa.bbbb.cccc     100   Static              GE0/0/24

Total MAC entries: 243""",

        "switch-lldp": """Local Interface  Neighbor Interface  Neighbor Device
  GE0/0/1           GE0/0/3             CORE-SWITCH
  GE0/0/2           GE0/0/4             CORE-SWITCH
  GE0/0/5           GE0/0/1             ACCESS-SWITCH-F1
  GE0/0/6           GE0/0/1             ACCESS-SWITCH-F2""",

        "switch-arp": """ARP Table:
  IP Address        MAC Address        Interface          Type
  192.168.1.1       0001.2345.6001     GE0/0/0            static
  192.168.1.5       0001.2345.6005     GE0/0/0            dynamic
  192.168.1.10      0001.2345.6010     GE0/0/0            dynamic
  10.0.0.1          aaaa.bbbb.0001     VLAN 10            dynamic""",

        "switch-stack": """Stack Status: Stacking enabled
  Member ID  Role       MAC               Priority  Status
  1          Master     0001.2345.6100    150       Active
  2          Standby    0001.2345.6101    100       Active
  3          Slave      0001.2345.6102    50        Active""",

        # ── FIREWALL ───────────────────────────────────────────────
        "fw-security-policy": """Security Policy:
  Name               Source Zone    Dest Zone     Action  Hit
  permit-lan-wan     trust          untrust       permit  152340
  deny-wan-lan       untrust        trust         deny    45210
  permit-dmz-wan     dmz            untrust       permit  23450
  deny-all           any            any           deny    67890

Total rules: 12""",

        "fw-session-table": """Firewall Session Table:
  Protocol  Source:Port         Dest:Port           App       State
  TCP       192.168.1.100:35000 203.0.113.5:80      HTTP      ESTABLISHED
  TCP       192.168.1.101:35001 203.0.113.10:443    HTTPS     ESTABLISHED
  UDP       10.0.0.5:53         8.8.8.8:53          DNS       ACTIVE

Total sessions: 4520""",

        "fw-ipsec": """IPSec Policy: IPSEC-POLICY-1
  Profile:         PROFILE-CORP
  Mode:            Tunnel
  Local IP:        200.100.50.1
  Remote IP:       200.100.50.2
  Proposal:        esp-aes256 esp-sha256
  PFS:             dh14
  Status:          Active""",

        "fw-zone": """Security Zones:
  Zone            Interfaces                    Type
  trust           GE0/0/0, GE0/0/1, GE0/0/2    Layer3
  untrust         GE0/0/3                       Layer3
  dmz             GE0/0/4                       Layer3
  management      GE0/0/7                       Layer3

Total zones: 4""",

        # ── LOAD-BALANCER ──────────────────────────────────────────
        "slb-service-group": """SLB Service Groups:
  Name            Protocol  Type      Members
  WEB-SERVERS     TCP       http      192.168.10.10:80, 192.168.10.11:80
  APP-SERVERS     TCP       http      192.168.10.20:8080, 192.168.10.21:8080
  DB-SERVERS      TCP       mysql     192.168.10.30:3306, 192.168.10.31:3306""",

        "slb-virtual-server": """Virtual Servers:
  Name            VIP               Port    Type      Pool
  WEB-VIP         203.0.113.10      80/443  HTTP/HTTPS WEB-SERVERS
  APP-VIP         203.0.113.11      8080    HTTP      APP-SERVERS
  DB-VIP          10.0.0.100        3306    MySQL     DB-SERVERS""",

        # ── SYSTEM COMMON ──────────────────────────────────────────
        "sys-version": """Huawei Versatile Routing Platform Software
VRP (R) Software, Version 8.021
Copyright (C) 2012-2025 Huawei Technologies Co., Ltd.
  NE8000-M8  uptime: 45 days, 12 hours, 30 minutes
  Memory: 16 GB total, 12 GB free
  CPU: 8 cores @ 2.1 GHz""",

        "sys-cpu": """CPU Usage:
  CPU0: 12.5%
  CPU1: 8.3%
  CPU2: 15.7%
  CPU3: 5.2%
  Average: 10.4%""",

        "sys-mem": """Memory Usage:
  Total:  16384 MB
  Used:   4096 MB (25%)
  Free:   12288 MB (75%)""",

        "sys-temperature": """Temperature Information:
  Slot  Sensor         Current  Lower    Upper    Status
  1     CPU            45°C     0°C      85°C     Normal
  1     Board          38°C     0°C      75°C     Normal
  2     CPU            42°C     0°C      85°C     Normal
  2     Board          36°C     0°C      75°C     Normal""",

        # ── WIRELESS ───────────────────────────────────────────────
        "ap-client": """Station Information:
  MAC Address       VLAN  Radio  RSSI  SNR  Status
  aa:bb:cc:00:11:01 10    1      -45   35   Associated
  aa:bb:cc:00:11:02 10    1      -55   30   Associated
  aa:bb:cc:00:11:03 20    2      -60   28   Associated

Total stations: 3""",

        "ap-radio": """Radio Information:
  ID  Band           Channel  Power(dBm)  Status
  1   2.4 GHz        6        20          Active
  2   5 GHz          36       20          Active
  3   5 GHz          149      17          Active""",

        "ap-ap-list": """Managed APs:
  AP ID  Name          MAC               Model              Status  Users
  1      AP-F1-01      aabb.ccdd.0001    AirEngine 8760     online  12
  2      AP-F1-02      aabb.ccdd.0002    AirEngine 8760     online  8
  3      AP-F2-01      aabb.ccdd.0003    AirEngine 8760     offline 0
  4      AP-F2-02      aabb.ccdd.0004    AirEngine 8760     online  15""",

        "sys-license": """License Information:
  Feature             Status     Expiry
  MPLS L3VPN          Active     2026-12-31
  BGP EVPN            Active     2026-12-31
  Segment Routing     Active     2026-12-31
  NetStream           Active     2026-12-31
  VXLAN               Not Licensed""",
    }

    default = (
        f"  {name} executado com sucesso.\n"
        f"  Timestamp: {ts}\n"
        f"  Resultado simulado para modo de demonstração."
    )
    result = templates.get(svc_id, default)
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
        log.error("execute_service CLI falhou: %s", e)
        return f"✘  Erro CLI: {e}"



