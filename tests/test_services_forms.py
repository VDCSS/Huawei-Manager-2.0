"""TDD dos formulários compostos de ACL e rota estática (Fases 2–3)."""
from __future__ import annotations

import pytest

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_form import SUPPORTS_ACL_NUMBER_AND_NAME
from huawei_manager.services.form_registry import (
    check_anchors,
    get_form_spec,
    render_form,
    rollback_lines,
)
from huawei_manager.services.form_spec import FormSpec


def _acl_values(**over):
    base = {
        "identificacao": {
            "acl_type": "avancada",
            "id_mode": "numero",
            "acl_number": "3000",
            "acl_name": "",
        },
        "rules": [
            {
                "rule_id": "5",
                "action": "permit",
                "protocol": "ip",
                "source": "10.0.0.0",
                "source_wildcard": "0.0.0.255",
                "destination": "",
                "destination_wildcard": "",
                "destination_port": "",
            },
        ],
        "applications": [],
    }
    base.update(over)
    return base


def _route_values(**over):
    base = {
        "routes": [
            {
                "destination": "0.0.0.0",
                "mask": "0.0.0.0",
                "interface": "",
                "next_hop": "10.0.12.2",
                "preference": "",
                "description": "",
            },
        ],
    }
    base.update(over)
    return base


class TestFormSpecLookup:
    def test_acl_spec_is_registered(self):
        spec = get_form_spec("acl")
        assert isinstance(spec, FormSpec)
        assert spec.kind == "acl"
        assert [s.key for s in spec.sections] == [
            "identificacao", "rules", "applications"]

    def test_static_route_spec_is_registered(self):
        spec = get_form_spec("static_route")
        assert spec.kind == "static_route"
        assert [s.key for s in spec.sections] == ["routes"]

    def test_unknown_kind_raises(self):
        with pytest.raises(SdnValidationError):
            get_form_spec("inexistente")


class TestAclRender:
    def test_numbered_advanced_acl(self):
        out = render_form("acl", _acl_values())
        assert out.lines == (
            "acl number 3000",
            "rule 5 permit ip source 10.0.0.0 0.0.0.255",
            "quit",
        )

    def test_named_basic_acl(self):
        values = _acl_values(identificacao={
            "acl_type": "basica",
            "id_mode": "nome",
            "acl_number": "",
            "acl_name": "MGT",
        })
        out = render_form("acl", values)
        assert out.lines[0] == "acl name MGT basic"

    def test_named_advanced_acl_uses_advance_suffix(self):
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "nome",
            "acl_number": "",
            "acl_name": "MGT",
        })
        out = render_form("acl", values)
        assert out.lines[0] == "acl name MGT advance"

    def test_number_and_name_together_is_rejected(self):
        """'acl number <n> name <x>' é recusado pelo device → modo bloqueado."""
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "ambos",
            "acl_number": "3000",
            "acl_name": "MGT",
        })
        with pytest.raises(SdnValidationError, match="não é suportado"):
            render_form("acl", values)

    def test_basic_acl_rejects_destination(self):
        values = _acl_values(identificacao={
            "acl_type": "basica",
            "id_mode": "numero",
            "acl_number": "2000",
            "acl_name": "",
        })
        values["rules"][0]["destination"] = "10.1.0.0"
        values["rules"][0]["destination_wildcard"] = "0.0.0.255"
        with pytest.raises(SdnValidationError, match="ACL básica"):
            render_form("acl", values)

    def test_basic_acl_number_out_of_range(self):
        values = _acl_values(identificacao={
            "acl_type": "basica",
            "id_mode": "numero",
            "acl_number": "3000",
            "acl_name": "",
        })
        with pytest.raises(SdnValidationError, match="faixa"):
            render_form("acl", values)

    def test_advanced_number_out_of_range(self):
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "numero",
            "acl_number": "2000",
            "acl_name": "",
        })
        with pytest.raises(SdnValidationError, match="faixa"):
            render_form("acl", values)

    def test_missing_number_raises(self):
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "numero",
            "acl_number": "",
            "acl_name": "",
        })
        with pytest.raises(SdnValidationError, match="número"):
            render_form("acl", values)

    def test_missing_name_raises(self):
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "nome",
            "acl_number": "",
            "acl_name": "",
        })
        with pytest.raises(SdnValidationError, match="nome"):
            render_form("acl", values)

    def test_no_rules_raises(self):
        values = _acl_values(rules=[])
        with pytest.raises(SdnValidationError, match="regra"):
            render_form("acl", values)

    def test_duplicate_rule_id_raises(self):
        values = _acl_values(rules=[
            {"rule_id": "5", "action": "permit", "protocol": "ip",
             "source": "10.0.0.0", "source_wildcard": "0.0.0.255",
             "destination": "", "destination_wildcard": "",
             "destination_port": ""},
            {"rule_id": "5", "action": "deny", "protocol": "ip",
             "source": "10.1.0.0", "source_wildcard": "0.0.0.255",
             "destination": "", "destination_wildcard": "",
             "destination_port": ""},
        ])
        with pytest.raises(SdnValidationError, match="duplicado"):
            render_form("acl", values)

    def test_advanced_rule_with_destination_and_port(self):
        values = _acl_values(rules=[{
            "rule_id": "10", "action": "deny", "protocol": "tcp",
            "source": "any", "source_wildcard": "",
            "destination": "192.168.1.0", "destination_wildcard": "0.0.0.255",
            "destination_port": "443",
        }])
        out = render_form("acl", values)
        assert out.lines[1] == (
            "rule 10 deny tcp source any destination 192.168.1.0 0.0.0.255 "
            "destination-port eq 443"
        )

    def test_port_without_tcp_udp_raises(self):
        values = _acl_values(rules=[{
            "rule_id": "10", "action": "deny", "protocol": "ip",
            "source": "any", "source_wildcard": "",
            "destination": "192.168.1.0", "destination_wildcard": "0.0.0.255",
            "destination_port": "443",
        }])
        with pytest.raises(SdnValidationError, match="tcp/udp"):
            render_form("acl", values)

    def test_source_without_wildcard_raises(self):
        values = _acl_values(rules=[{
            "rule_id": "10", "action": "deny", "protocol": "ip",
            "source": "10.0.0.1", "source_wildcard": "",
            "destination": "", "destination_wildcard": "",
            "destination_port": "",
        }])
        with pytest.raises(SdnValidationError, match="máscara da origem"):
            render_form("acl", values)


class TestAclApplications:
    def test_interface_application(self):
        values = _acl_values(applications=[{
            "where": "interface",
            "interface": "GigabitEthernet0/0/0",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        out = render_form("acl", values)
        assert out.lines[-3:] == (
            "interface GigabitEthernet0/0/0",
            "traffic-filter inbound acl 3000",
            "quit",
        )

    def test_vty_application(self):
        values = _acl_values(applications=[{
            "where": "vty",
            "interface": "",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        out = render_form("acl", values)
        assert out.lines[-3:] == (
            "user-interface vty 0 4",
            "acl 3000 inbound",
            "quit",
        )

    def test_named_acl_application_uses_name_as_reference(self):
        values = _acl_values(
            identificacao={
                "acl_type": "avancada",
                "id_mode": "nome",
                "acl_number": "",
                "acl_name": "MGT",
            },
            applications=[{
                "where": "interface",
                "interface": "GigabitEthernet0/0/0",
                "direction": "outbound",
                "vty_range": "0 4",
            }],
        )
        out = render_form("acl", values)
        assert "traffic-filter outbound acl MGT" in out.lines

    def test_interface_application_requires_interface(self):
        values = _acl_values(applications=[{
            "where": "interface",
            "interface": "",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        with pytest.raises(SdnValidationError, match="interface"):
            render_form("acl", values)


class TestAclAnchors:
    def test_anchors_contain_rules_and_applications(self):
        values = _acl_values(applications=[{
            "where": "interface",
            "interface": "GigabitEthernet0/0/0",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        out = render_form("acl", values)
        assert "rule 5 permit ip source 10.0.0.0 0.0.0.255" in out.anchors
        assert "traffic-filter inbound acl 3000" in out.anchors
        # o cabeçalho da ACL não é âncora (o device pode normalizá-lo)
        assert "acl number 3000" not in out.anchors

    def test_check_anchors_detects_missing(self):
        values = _acl_values()
        out = render_form("acl", values)
        running = "acl number 3000\n rule 5 permit ip source 10.0.0.0 0.0.0.255\n"
        assert check_anchors(running, out.anchors) == []

    def test_check_anchors_reports_absent(self):
        values = _acl_values()
        out = render_form("acl", values)
        assert check_anchors("acl number 3000", out.anchors) == [
            "rule 5 permit ip source 10.0.0.0 0.0.0.255"]


class TestAclRollback:
    def test_new_acl_is_removed_entirely(self):
        values = _acl_values(applications=[{
            "where": "interface",
            "interface": "GigabitEthernet0/0/0",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        out = render_form("acl", values)
        undo = rollback_lines(out, "sysname RTR\n")
        assert undo == [
            "interface GigabitEthernet0/0/0",
            "undo traffic-filter inbound acl 3000",
            "quit",
            "undo acl number 3000",
        ]

    def test_existing_acl_only_undoes_rules(self):
        values = _acl_values()
        out = render_form("acl", values)
        snapshot = "acl number 3000\n rule 1 deny ip any any\n"
        undo = rollback_lines(out, snapshot)
        assert undo == [
            "acl number 3000",
            "undo rule 5",
            "quit",
        ]

    def test_existing_named_acl_only_undoes_rules(self):
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "nome",
            "acl_number": "",
            "acl_name": "MGT",
        })
        out = render_form("acl", values)
        undo = rollback_lines(out, "acl name MGT advance\n rule 1 deny ip any any\n")
        assert undo == [
            "acl name MGT advance",
            "undo rule 5",
            "quit",
        ]

    def test_vty_application_is_undone_first(self):
        values = _acl_values(applications=[{
            "where": "vty",
            "interface": "",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        out = render_form("acl", values)
        undo = rollback_lines(out, "sysname RTR\n")
        assert undo[:3] == [
            "user-interface vty 0 4",
            "undo acl inbound",
            "quit",
        ]


class TestFormSpecMetadata:
    def test_acl_spec_has_consult_command(self):
        assert get_form_spec("acl").consult_command == "display acl all"

    def test_static_route_spec_has_consult_command(self):
        assert get_form_spec("static_route").consult_command == (
            "display ip routing-table")

    def test_acl_spec_has_no_both_mode(self):
        """O modo 'ambos' não existe — a VRP recusa 'acl number N name X'."""
        id_mode = get_form_spec("acl").field("id_mode")
        assert id_mode is not None
        assert id_mode.choices == ("numero", "nome")
        assert SUPPORTS_ACL_NUMBER_AND_NAME is False


class TestRouteRender:
    def test_next_hop_only(self):
        out = render_form("static_route", _route_values())
        assert out.lines == ("ip route-static 0.0.0.0 0.0.0.0 10.0.12.2",)

    def test_interface_and_next_hop(self):
        values = _route_values(routes=[{
            "destination": "10.10.0.0", "mask": "/16",
            "interface": "GigabitEthernet0/0/0",
            "next_hop": "10.0.12.2",
            "preference": "100", "description": "backbone",
        }])
        out = render_form("static_route", values)
        assert out.lines == (
            "ip route-static 10.10.0.0 255.255.0.0 GigabitEthernet0/0/0 "
            "10.0.12.2 preference 100 description backbone",
        )

    def test_interface_only(self):
        values = _route_values(routes=[{
            "destination": "10.10.0.0", "mask": "255.255.0.0",
            "interface": "NULL0", "next_hop": "",
            "preference": "", "description": "",
        }])
        out = render_form("static_route", values)
        assert out.lines == ("ip route-static 10.10.0.0 255.255.0.0 NULL0",)

    def test_requires_next_hop_or_interface(self):
        values = _route_values(routes=[{
            "destination": "10.10.0.0", "mask": "255.255.0.0",
            "interface": "", "next_hop": "",
            "preference": "", "description": "",
        }])
        with pytest.raises(SdnValidationError, match="next-hop"):
            render_form("static_route", values)

    def test_no_routes_raises(self):
        with pytest.raises(SdnValidationError, match="rota"):
            render_form("static_route", {"routes": []})

    def test_duplicate_route_raises(self):
        """Mesma rota (destino/máscara/interface/next-hop/preferência) é duplicata."""
        values = _route_values(routes=[
            {"destination": "10.0.0.0", "mask": "255.0.0.0", "interface": "",
             "next_hop": "10.0.12.2", "preference": "", "description": ""},
            {"destination": "10.0.0.0", "mask": "255.0.0.0", "interface": "",
             "next_hop": "10.0.12.2", "preference": "", "description": ""},
        ])
        with pytest.raises(SdnValidationError, match="duplicada"):
            render_form("static_route", values)

    def test_same_destination_with_different_next_hop_is_allowed(self):
        """ECMP/rota flutuante: mesmo destino, next-hops diferentes são válidas."""
        values = _route_values(routes=[
            {"destination": "10.0.0.0", "mask": "255.0.0.0", "interface": "",
             "next_hop": "10.0.12.2", "preference": "", "description": ""},
            {"destination": "10.0.0.0", "mask": "255.0.0.0", "interface": "",
             "next_hop": "10.0.12.3", "preference": "", "description": ""},
        ])
        out = render_form("static_route", values)
        assert len(out.lines) == 2

    def test_preference_range_is_enforced(self):
        values = _route_values(routes=[{
            "destination": "10.0.0.0", "mask": "255.0.0.0", "interface": "",
            "next_hop": "10.0.12.2", "preference": "999", "description": "",
        }])
        with pytest.raises(SdnValidationError):
            render_form("static_route", values)

    def test_anchors_are_the_rendered_lines(self):
        out = render_form("static_route", _route_values())
        assert out.anchors == out.lines

    def test_rollback_undoes_routes_in_reverse_order(self):
        values = _route_values(routes=[
            {"destination": "10.0.0.0", "mask": "255.0.0.0", "interface": "",
             "next_hop": "10.0.12.2", "preference": "", "description": ""},
            {"destination": "10.1.0.0", "mask": "255.255.0.0", "interface": "",
             "next_hop": "10.0.12.3", "preference": "100", "description": ""},
        ])
        out = render_form("static_route", values)
        undo = rollback_lines(out, "")
        # O undo não leva 'preference' (a VRP recusa) — apenas destino,
        # máscara e next-hop.
        assert undo == [
            "undo ip route-static 10.1.0.0 255.255.0.0 10.0.12.3",
            "undo ip route-static 10.0.0.0 255.0.0.0 10.0.12.2",
        ]
