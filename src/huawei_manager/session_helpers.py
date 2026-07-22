from __future__ import annotations


def resolve_filter(filter_xml: str | None) -> str | None:
    if filter_xml is None:
        return None
    f = filter_xml.lower()
    if "full_config" in f or "current-configuration" in f:
        return "display current-configuration"
    if "interface" in f and "counter" not in f:
        return "display interface"
    if "interface" in f and "counter" in f:
        return "display counters interface"
    if "routing" in f or "route" in f or "network-instance" in f:
        return "display ip routing-table"
    if "bgp" in f or "huawei_bgp" in f:
        return "display bgp peer"
    if "ospf" in f:
        return "display ospf peer"
    if "vrf" in f or "vpn-instance" in f:
        return "display ip vpn-instance"
    if "lldp" in f:
        return "display lldp neighbor brief"
    if "qos" in f:
        return "display qos policy"
    if "system" in f or "cpu" in f or "mem" in f:
        return "display cpu-usage"
    if "arp" in f:
        return "display arp"
    if "mpls" in f:
        return "display mpls ldp peer"
    if "platform" in f or "component" in f or "version" in f:
        return "display version"
    return None
