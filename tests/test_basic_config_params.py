"""TDD do núcleo de parametrização tipada (F0)."""
from __future__ import annotations

import pytest

from huawei_manager.basic_config.params import (
    ConfigTemplate,
    ParamKind,
    ParamSpec,
    normalize_values,
    validate_value,
)
from huawei_manager.exceptions import SdnValidationError


def _spec(kind: ParamKind, **kw) -> ParamSpec:
    return ParamSpec(key=kw.pop("key", "v"), label=kw.pop("label", "Valor"),
                     kind=kind, **kw)


class TestParamValidation:
    def test_ipv4_normalizes(self):
        assert validate_value(_spec(ParamKind.IPV4), " 10.0.0.1 ") == "10.0.0.1"

    def test_ipv4_rejects_invalid(self):
        with pytest.raises(SdnValidationError):
            validate_value(_spec(ParamKind.IPV4), "999.1.1.1")

    @pytest.mark.parametrize("raw,expected", [
        ("255.255.255.0", "255.255.255.0"),
        ("/24", "255.255.255.0"),
        ("24", "255.255.255.0"),
        ("/30", "255.255.255.252"),
    ])
    def test_mask_accepts_dotted_and_prefix(self, raw, expected):
        assert validate_value(_spec(ParamKind.MASK), raw) == expected

    def test_mask_rejects_non_contiguous(self):
        with pytest.raises(SdnValidationError):
            validate_value(_spec(ParamKind.MASK), "255.0.255.0")

    def test_interface_accepts_huawei_names(self):
        spec = _spec(ParamKind.INTERFACE)
        assert validate_value(spec, "GigabitEthernet0/0/0") == "GigabitEthernet0/0/0"
        assert validate_value(spec, "Vlanif10") == "Vlanif10"
        assert validate_value(spec, "Eth-Trunk1") == "Eth-Trunk1"
        assert validate_value(spec, "Ethernet1/0/1") == "Ethernet1/0/1"
        assert validate_value(spec, "MultiGE1/0/1") == "MultiGE1/0/1"
        assert validate_value(spec, "Multi-GE1/0/1") == "Multi-GE1/0/1"
        assert validate_value(spec, "XGigabitEthernet1/0/1") == "XGigabitEthernet1/0/1"
        assert validate_value(spec, "GE1/0/1") == "GE1/0/1"
        assert validate_value(spec, "XGE1/0/1") == "XGE1/0/1"
        assert validate_value(spec, "LoopBack0") == "LoopBack0"

    @pytest.mark.parametrize("raw", [
        "GigabitEthernet0/0/0\rshutdown",
        "GigabitEthernet0/0/0\nshutdown",
        "GigabitEthernet 0/0/0",
        "interface GigabitEthernet0/0/0",
        "GE0/0/0;shutdown",
    ])
    def test_interface_rejects_injection(self, raw):
        with pytest.raises(SdnValidationError):
            validate_value(_spec(ParamKind.INTERFACE), raw)

    def test_acl_range(self):
        spec = _spec(ParamKind.ACL_ID)
        assert validate_value(spec, "2000") == "2000"
        assert validate_value(spec, "3999") == "3999"
        for bad in ("1999", "4000", "abc"):
            with pytest.raises(SdnValidationError):
                validate_value(spec, bad)

    @pytest.mark.parametrize("raw", [
        "short", "com espaço", "senha;shutdown", "senha|filter",
        "senha\r\nshutdown", 'senha"quote',
    ])
    def test_password_rejects_unsafe_values(self, raw):
        with pytest.raises(SdnValidationError):
            validate_value(_spec(ParamKind.PASSWORD), raw)

    def test_password_accepts_strong_value(self):
        value = "S3nh@ForteCom12"
        assert validate_value(_spec(ParamKind.PASSWORD), value) == value

    def test_required_empty_rejected(self):
        with pytest.raises(SdnValidationError):
            validate_value(_spec(ParamKind.TEXT), "")

    def test_optional_empty_allowed(self):
        assert validate_value(_spec(ParamKind.TEXT, required=False), "") == ""

    def test_text_rejects_command_separators(self):
        for bad in ("a;b", "a\rb", "a\nb", "a`b", "a$(b)"):
            with pytest.raises(SdnValidationError):
                validate_value(_spec(ParamKind.TEXT), bad)

    def test_unknown_parameter_rejected(self):
        with pytest.raises(SdnValidationError, match="desconhecido"):
            normalize_values([_spec(ParamKind.IPV4, key="ip")], {"ip": "10.0.0.1",
                                                               "x": "y"})


class TestConfigTemplate:
    def test_renders_block_with_quit(self):
        specs = [
            ParamSpec("acl", "ACL", ParamKind.ACL_ID),
            ParamSpec("rule", "Regra", ParamKind.RULE_ID),
            ParamSpec("action", "Ação", ParamKind.ENUM, choices=("permit", "deny")),
            ParamSpec("source", "Origem", ParamKind.IPV4),
            ParamSpec("wildcard", "Wildcard", ParamKind.WILDCARD),
        ]
        tpl = ConfigTemplate((
            "acl number {acl}",
            "rule {rule} {action} source {source} {wildcard}",
            "quit",
        ))
        assert tpl.render(specs, {
            "acl": "2000", "rule": "5", "action": "permit",
            "source": "192.168.1.0", "wildcard": "0.0.0.255",
        }) == [
            "acl number 2000",
            "rule 5 permit source 192.168.1.0 0.0.0.255",
            "quit",
        ]

    def test_optional_block_removed_when_empty(self):
        specs = [
            ParamSpec("dst", "Destino", ParamKind.IPV4, required=False),
            ParamSpec("dst_wc", "Wildcard destino", ParamKind.WILDCARD,
                      required=False),
            ParamSpec("rule", "Regra", ParamKind.RULE_ID),
        ]
        tpl = ConfigTemplate((
            "rule {rule} permit ip[[ destination {dst} {dst_wc}]]",
        ))
        assert tpl.render(specs, {"rule": "5", "dst": "", "dst_wc": ""}) == [
            "rule 5 permit ip"
        ]
        assert tpl.render(specs, {"rule": "5", "dst": "10.0.0.0",
                                  "dst_wc": "0.0.0.255"}) == [
            "rule 5 permit ip destination 10.0.0.0 0.0.0.255"
        ]

    def test_unresolved_placeholder_rejected(self):
        specs = [ParamSpec("a", "A", ParamKind.TEXT)]
        tpl = ConfigTemplate(("x {a} {b}",))
        with pytest.raises(SdnValidationError, match="não resolvido"):
            tpl.render(specs, {"a": "ok"})

    def test_empty_render_rejected(self):
        tpl = ConfigTemplate(("[[x {a}]]",))
        specs = [ParamSpec("a", "A", ParamKind.TEXT, required=False)]
        with pytest.raises(SdnValidationError, match="vazia"):
            tpl.render(specs, {"a": ""})


class TestBuilders:
    def test_hostname(self):
        from huawei_manager.basic_config.builders import HOSTNAME_SPECS, HOSTNAME_TEMPLATE
        assert HOSTNAME_TEMPLATE.render(HOSTNAME_SPECS, {"hostname": "RTR-01"}) == [
            "sysname RTR-01"
        ]

    def test_interface_l3_block(self):
        from huawei_manager.basic_config.builders import (
            INTERFACE_L3_SPECS, INTERFACE_L3_TEMPLATE,
        )
        lines = INTERFACE_L3_TEMPLATE.render(INTERFACE_L3_SPECS, {
            "interface": "GigabitEthernet0/0/0",
            "ip": "10.0.0.1", "mask": "/24",
            "description": "UPLINK", "state": "undo shutdown",
            "portswitch": "",
        })
        assert lines == [
            "interface GigabitEthernet0/0/0",
            "description UPLINK",
            "ip address 10.0.0.1 255.255.255.0",
            "undo shutdown",
            "quit",
        ]

    def test_l2_access_block(self):
        from huawei_manager.basic_config.builders import (
            L2_ACCESS_SPECS, L2_ACCESS_TEMPLATE,
        )
        lines = L2_ACCESS_TEMPLATE.render(L2_ACCESS_SPECS, {
            "vlan_id": "10", "interface": "GigabitEthernet0/0/1",
            "ip": "192.168.10.1", "mask": "24",
            "vlan_description": "", "interface_description": "ACESSO",
            "vlanif_description": "",
        })
        assert lines == [
            "vlan 10", "quit",
            "interface GigabitEthernet0/0/1",
            "port link-type access", "port default vlan 10",
            "description ACESSO", "undo shutdown", "quit",
            "interface Vlanif 10", "ip address 192.168.10.1 255.255.255.0",
            "undo shutdown", "quit",
        ]

    def test_ssh_block_has_no_plaintext_leak_in_other_fields(self):
        from huawei_manager.basic_config.builders import SSH_SPECS, SSH_TEMPLATE
        lines = SSH_TEMPLATE.render(SSH_SPECS, {
            "username": "admin", "password": "S3nh@ForteCom12",
            "vty_range": "0 4",
        })
        assert "local-user admin password irreversible-cipher S3nh@ForteCom12" in lines
        assert "stelnet server enable" in lines
        assert "authentication-mode aaa" in lines

    def test_acl_basic_block_has_no_ip_keyword(self):
        from huawei_manager.basic_config.builders import (
            ACL_BASIC_RULE_SPECS, ACL_BASIC_RULE_TEMPLATE,
        )
        lines = ACL_BASIC_RULE_TEMPLATE.render(ACL_BASIC_RULE_SPECS, {
            "acl": "2000", "rule": "5", "action": "permit",
            "source": "192.168.1.0", "wildcard": "0.0.0.255",
        })
        assert lines == [
            "acl number 2000",
            "rule 5 permit source 192.168.1.0 0.0.0.255",
            "quit",
        ]

    def test_acl_advanced_block_optional_destination(self):
        from huawei_manager.basic_config.builders import (
            ACL_ADVANCED_RULE_SPECS, ACL_ADVANCED_RULE_TEMPLATE,
        )
        lines = ACL_ADVANCED_RULE_TEMPLATE.render(ACL_ADVANCED_RULE_SPECS, {
            "acl": "3000", "rule": "5", "action": "permit", "protocol": "tcp",
            "source": "10.0.0.0", "wildcard": "0.0.0.255",
            "destination": "192.168.1.10", "destination_wildcard": "0.0.0.0",
            "destination_port": "443",
        })
        assert lines == [
            "acl number 3000",
            "rule 5 permit tcp source 10.0.0.0 0.0.0.255 "
            "destination 192.168.1.10 0.0.0.0 destination-port eq 443",
            "quit",
        ]

    def test_traffic_filter_block(self):
        from huawei_manager.basic_config.builders import (
            TRAFFIC_FILTER_SPECS, TRAFFIC_FILTER_TEMPLATE,
        )
        lines = TRAFFIC_FILTER_TEMPLATE.render(TRAFFIC_FILTER_SPECS, {
            "interface": "GigabitEthernet0/0/0", "direction": "inbound",
            "acl": "3000",
        })
        assert lines == [
            "interface GigabitEthernet0/0/0",
            "traffic-filter inbound acl 3000",
            "quit",
        ]

    def test_vty_acl_block(self):
        from huawei_manager.basic_config.builders import VTY_ACL_SPECS, VTY_ACL_TEMPLATE
        lines = VTY_ACL_TEMPLATE.render(VTY_ACL_SPECS, {
            "vty_range": "0 4", "acl": "2000",
        })
        assert lines == ["user-interface vty 0 4", "acl 2000 inbound", "quit"]
