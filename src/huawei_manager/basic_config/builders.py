"""Builders de blocos de configuração VRP.

Cada builder declara ``ParamSpec`` tipados e um ``ConfigTemplate`` que produz
o bloco hierárquico completo (incluindo ``quit``). A UI só coleta strings;
a validação/normalização acontece no renderizador tipado.
"""
from __future__ import annotations

from huawei_manager.basic_config.params import (
    ConfigTemplate,
    ParamKind,
    ParamSpec,
)

# ── Hostname / sistema ────────────────────────────────────────────────
HOSTNAME_SPECS = (
    ParamSpec("hostname", "Hostname", ParamKind.HOSTNAME, max_len=64),
)
HOSTNAME_TEMPLATE = ConfigTemplate(("sysname {hostname}",))


# ── Interface L3 ──────────────────────────────────────────────────────
INTERFACE_L3_SPECS = (
    ParamSpec("interface", "Interface", ParamKind.INTERFACE),
    ParamSpec("ip", "Endereço IP", ParamKind.IPV4),
    ParamSpec("mask", "Máscara", ParamKind.MASK),
    ParamSpec("description", "Descrição", ParamKind.TEXT, required=False,
              max_len=128),
    ParamSpec("state", "Estado", ParamKind.ENUM, default="undo shutdown",
              choices=("undo shutdown", "shutdown")),
    ParamSpec("portswitch", "Portswitch", ParamKind.TEXT, required=False,
              max_len=32, help="Use 'undo portswitch' apenas em porta L3 de switch"),
)
INTERFACE_L3_TEMPLATE = ConfigTemplate((
    "interface {interface}",
    "[[{portswitch}]]",
    "[[description {description}]]",
    "ip address {ip} {mask}",
    "[[{state}]]",
    "quit",
))


# ── L2 access + Vlanif ────────────────────────────────────────────────
L2_ACCESS_SPECS = (
    ParamSpec("vlan_id", "VLAN ID", ParamKind.VLAN_ID, minimum=1, maximum=4094),
    ParamSpec("interface", "Interface de acesso", ParamKind.INTERFACE),
    ParamSpec("ip", "IP da Vlanif", ParamKind.IPV4),
    ParamSpec("mask", "Máscara da Vlanif", ParamKind.MASK),
    ParamSpec("vlan_description", "Descrição da VLAN", ParamKind.TEXT,
              required=False, max_len=128),
    ParamSpec("interface_description", "Descrição da interface", ParamKind.TEXT,
              required=False, max_len=128),
    ParamSpec("vlanif_description", "Descrição da Vlanif", ParamKind.TEXT,
              required=False, max_len=128),
)
L2_ACCESS_TEMPLATE = ConfigTemplate((
    "vlan {vlan_id}",
    "[[description {vlan_description}]]",
    "quit",
    "interface {interface}",
    "port link-type access",
    "port default vlan {vlan_id}",
    "[[description {interface_description}]]",
    "undo shutdown",
    "quit",
    "interface Vlanif {vlan_id}",
    "ip address {ip} {mask}",
    "[[description {vlanif_description}]]",
    "undo shutdown",
    "quit",
))


# ── SSH / VTY / AAA ───────────────────────────────────────────────────
SSH_SPECS = (
    ParamSpec("username", "Usuário SSH", ParamKind.USERNAME),
    ParamSpec("password", "Senha", ParamKind.PASSWORD, secret=True),
    ParamSpec("vty_range", "Faixa VTY", ParamKind.VTY_RANGE, default="0 4"),
)
SSH_TEMPLATE = ConfigTemplate((
    "stelnet server enable",
    "ssh user {username} authentication-type password",
    "ssh user {username} service-type stelnet",
    "aaa",
    "local-user {username} password irreversible-cipher {password}",
    "local-user {username} privilege level 15",
    "local-user {username} service-type ssh terminal http",
    "quit",
    "user-interface vty {vty_range}",
    "authentication-mode aaa",
    "protocol inbound ssh",
    "quit",
))

# VRP5: sintaxe de ``ssh user`` e ``local-user`` pode diferir de VRP8.
# Mantemos a mesma estrutura, mas o ``local-user`` usa ``simple`` (não
# ``irreversible-cipher``) e o operador é avisado na prévia para revisar
# antes de aplicar.
SSH_TEMPLATE_VRP5 = ConfigTemplate((
    "stelnet server enable",
    "ssh user {username} authentication-type password",
    "ssh user {username} service-type stelnet",
    "aaa",
    "local-user {username} password simple {password}",
    "local-user {username} privilege level 15",
    "local-user {username} service-type ssh terminal http",
    "quit",
    "user-interface vty {vty_range}",
    "authentication-mode aaa",
    "protocol inbound ssh",
    "quit",
))


# ── Usuário administrativo ────────────────────────────────────────────
ADMIN_USER_SPECS = (
    ParamSpec("username", "Usuário administrativo", ParamKind.USERNAME),
    ParamSpec("password", "Senha", ParamKind.PASSWORD, secret=True),
    ParamSpec("privilege", "Nível de privilégio", ParamKind.INT, default="15",
              minimum=0, maximum=15),
)
ADMIN_USER_TEMPLATE = ConfigTemplate((
    "aaa",
    "local-user {username} password irreversible-cipher {password}",
    "local-user {username} privilege level {privilege}",
    "local-user {username} service-type ssh terminal http",
    "quit",
))

# VRP5 não suporta ``irreversible-cipher`` em todos os modelos;
# usa ``simple`` (reversível) como fallback honesto. O operador vê o
# bloco na prévia e pode ajustar antes de aplicar.
ADMIN_USER_TEMPLATE_VRP5 = ConfigTemplate((
    "aaa",
    "local-user {username} password simple {password}",
    "local-user {username} privilege level {privilege}",
    "local-user {username} service-type ssh terminal http",
    "quit",
))


# ── ACLs numéricas ────────────────────────────────────────────────────
ACL_NUMBER_SPECS = (
    ParamSpec("acl", "ACL ID", ParamKind.ACL_ID),
)
ACL_NUMBER_TEMPLATE = ConfigTemplate(("acl number {acl}",))

ACL_BASIC_RULE_SPECS = (
    ParamSpec("acl", "ACL ID", ParamKind.ACL_ID),
    ParamSpec("rule", "Rule ID", ParamKind.RULE_ID, minimum=0, maximum=65534),
    ParamSpec("action", "Ação", ParamKind.ENUM, choices=("permit", "deny")),
    ParamSpec("source", "IP de origem", ParamKind.IPV4),
    ParamSpec("wildcard", "Wildcard de origem", ParamKind.WILDCARD),
)
ACL_BASIC_RULE_TEMPLATE = ConfigTemplate((
    "acl number {acl}",
    "rule {rule} {action} source {source} {wildcard}",
    "quit",
))

ACL_ADVANCED_RULE_SPECS = (
    ParamSpec("acl", "ACL ID", ParamKind.ACL_ID),
    ParamSpec("rule", "Rule ID", ParamKind.RULE_ID, minimum=0, maximum=65534),
    ParamSpec("action", "Ação", ParamKind.ENUM, choices=("permit", "deny")),
    ParamSpec("protocol", "Protocolo", ParamKind.ENUM,
              choices=("ip", "tcp", "udp", "icmp", "gre", "ospf")),
    ParamSpec("source", "IP de origem", ParamKind.IPV4),
    ParamSpec("wildcard", "Wildcard de origem", ParamKind.WILDCARD),
    ParamSpec("destination", "IP de destino", ParamKind.IPV4, required=False),
    ParamSpec("destination_wildcard", "Wildcard de destino",
              ParamKind.WILDCARD, required=False, default="0.0.0.0"),
    ParamSpec("destination_port", "Porta de destino", ParamKind.PORT,
              required=False),
)
ACL_ADVANCED_RULE_TEMPLATE = ConfigTemplate((
    "acl number {acl}",
    "rule {rule} {action} {protocol} source {source} {wildcard}"
    "[[ destination {destination} {destination_wildcard}]]"
    "[[ destination-port eq {destination_port}]]",
    "quit",
))

TRAFFIC_FILTER_SPECS = (
    ParamSpec("interface", "Interface", ParamKind.INTERFACE),
    ParamSpec("direction", "Direção", ParamKind.ENUM,
              choices=("inbound", "outbound")),
    ParamSpec("acl", "ACL ID", ParamKind.ACL_ID),
)
TRAFFIC_FILTER_TEMPLATE = ConfigTemplate((
    "interface {interface}",
    "traffic-filter {direction} acl {acl}",
    "quit",
))

VTY_ACL_SPECS = (
    ParamSpec("vty_range", "Faixa VTY", ParamKind.VTY_RANGE, default="0 4"),
    ParamSpec("acl", "ACL ID", ParamKind.ACL_ID),
)
VTY_ACL_TEMPLATE = ConfigTemplate((
    "user-interface vty {vty_range}",
    "acl {acl} inbound",
    "quit",
))
