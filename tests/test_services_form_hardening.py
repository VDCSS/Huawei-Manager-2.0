"""TDD do endurecimento dos formulários compostos (pós-revisão adversarial).

Cobre as correções validadas no device (NE40E / VRP 8.180):

* ``acl number N name X`` é recusado pelo device → modo "ambos" bloqueado;
* porta de destino usa ``destination-port eq <porta>``;
* undo do VTY é ``undo acl inbound``;
* undo de rota não leva ``preference``/``description``;
* rollback não desfaz estado **pré-existente** (regras/rotas que já
  estavam no snapshot);
* campos condicionais ocultos não são aplicados.
"""
from __future__ import annotations

import pytest

from huawei_manager.basic_config.params import ParamKind, ParamSpec, validate_value
from huawei_manager.basic_config.vrp_version import VrpVersion, requires_commit
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.form_registry import (
    check_anchors,
    get_form_spec,
    render_form,
    rollback_lines,
)


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
                "destination": "10.0.0.0",
                "mask": "255.0.0.0",
                "interface": "",
                "next_hop": "10.0.12.2",
                "preference": "",
                "description": "",
            },
        ],
    }
    base.update(over)
    return base


# ── commit fail-closed ──────────────────────────────────────────────
class TestRequiresCommit:
    def test_unknown_version_requires_commit(self):
        """Sem versão identificada: commit (fail-closed)."""
        assert requires_commit(VrpVersion.UNKNOWN) is True

    def test_vrp8_requires_commit(self):
        assert requires_commit(VrpVersion.VRP8) is True

    def test_vrp5_does_not_require_commit(self):
        assert requires_commit(VrpVersion.VRP5) is False


# ── ACL ─────────────────────────────────────────────────────────────
class TestAclHardening:
    def test_both_mode_is_rejected(self):
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "ambos",
            "acl_number": "3000",
            "acl_name": "MGT",
        })
        with pytest.raises(SdnValidationError, match="não é suportado"):
            render_form("acl", values)

    def test_reference_follows_the_identification_mode(self):
        """A aplicação referencia o mesmo identificador do cabeçalho."""
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
                "direction": "inbound",
                "vty_range": "0 4",
            }],
        )
        out = render_form("acl", values)
        assert out.lines[0] == "acl name MGT advance"
        assert "traffic-filter inbound acl MGT" in out.lines

    def test_number_mode_never_uses_the_name(self):
        """Modo número: o nome preenchido é ignorado (não vira referência)."""
        values = _acl_values(identificacao={
            "acl_type": "avancada",
            "id_mode": "numero",
            "acl_number": "3000",
            "acl_name": "MGT",
        })
        out = render_form("acl", values)
        assert out.lines[0] == "acl number 3000"
        assert not any("MGT" in line for line in out.lines)

    def test_numeric_acl_name_is_rejected(self):
        """Nome só numérico colide com a ACL numérica → erro."""
        with pytest.raises(SdnValidationError, match="numérico"):
            validate_value(
                ParamSpec(key="acl_name", label="Nome", kind=ParamKind.ACL_NAME),
                "3000",
            )

    def test_port_uses_destination_port_keyword(self):
        values = _acl_values(rules=[{
            "rule_id": "10", "action": "deny", "protocol": "tcp",
            "source": "any", "source_wildcard": "",
            "destination": "any", "destination_wildcard": "",
            "destination_port": "443",
        }])
        out = render_form("acl", values)
        assert out.lines[1] == (
            "rule 10 deny tcp source any destination any destination-port eq 443"
        )

    def test_source_any_with_wildcard_is_rejected(self):
        values = _acl_values(rules=[{
            "rule_id": "10", "action": "deny", "protocol": "ip",
            "source": "any", "source_wildcard": "0.0.0.255",
            "destination": "", "destination_wildcard": "",
            "destination_port": "",
        }])
        with pytest.raises(SdnValidationError, match="ignorada"):
            render_form("acl", values)

    def test_wildcard_any_with_specific_source_is_rejected(self):
        values = _acl_values(rules=[{
            "rule_id": "10", "action": "deny", "protocol": "ip",
            "source": "10.0.0.1", "source_wildcard": "any",
            "destination": "", "destination_wildcard": "",
            "destination_port": "",
        }])
        with pytest.raises(SdnValidationError, match="não pode ser 'any'"):
            render_form("acl", values)

    def test_null0_is_not_a_valid_application_interface(self):
        values = _acl_values(applications=[{
            "where": "interface",
            "interface": "NULL0",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        with pytest.raises(SdnValidationError, match="NULL0"):
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

    def test_existing_rule_is_not_removed_by_rollback(self):
        """Regra que já existia no snapshot é preservada no rollback."""
        values = _acl_values()
        out = render_form("acl", values)
        snapshot = (
            "acl number 3000\n"
            " rule 5 permit ip source 10.0.0.0 0.0.0.255\n"
        )
        undo = rollback_lines(out, snapshot)
        assert undo == ["acl number 3000", "quit"], (
            f"rollback não deve desfazer regra pré-existente: {undo}"
        )

    def test_new_acl_is_removed_entirely(self):
        out = render_form("acl", _acl_values())
        undo = rollback_lines(out, "sysname RTR\n")
        assert undo == ["undo acl number 3000"]

    def test_vty_undo_uses_acl_inbound(self):
        """'undo acl <n> inbound' é recusado pelo device."""
        values = _acl_values(applications=[{
            "where": "vty",
            "interface": "",
            "direction": "inbound",
            "vty_range": "0 4",
        }])
        out = render_form("acl", values)
        undo = rollback_lines(out, "sysname RTR\n")
        assert "undo acl inbound" in undo
        assert not any("undo acl 3000 inbound" in line for line in undo)


# ── Rotas ───────────────────────────────────────────────────────────
class TestRouteHardening:
    def test_undo_has_no_preference_or_description(self):
        values = _route_values(routes=[{
            "destination": "10.0.0.0", "mask": "255.0.0.0", "interface": "",
            "next_hop": "10.0.12.2", "preference": "100",
            "description": "backbone",
        }])
        out = render_form("static_route", values)
        undo = rollback_lines(out, "")
        assert undo == ["undo ip route-static 10.0.0.0 255.0.0.0 10.0.12.2"]

    def test_preexisting_route_is_preserved(self):
        """Rota que já existia no snapshot não é removida no rollback."""
        values = _route_values()
        out = render_form("static_route", values)
        snapshot = "ip route-static 10.0.0.0 255.0.0.0 10.0.12.2\n"
        assert rollback_lines(out, snapshot) == []

    def test_new_route_is_removed(self):
        out = render_form("static_route", _route_values())
        assert rollback_lines(out, "sysname RTR\n") == [
            "undo ip route-static 10.0.0.0 255.0.0.0 10.0.12.2"
        ]


# ── Verificação semântica (a VRP normaliza as regras) ──────────────
class TestAnchorSemantics:
    """A VRP normaliza ``rule 10 permit ip source any destination any``
    para ``rule 10 permit ip`` — a verificação precisa ser semântica."""

    def test_normalized_rule_is_accepted(self):
        cfg = "acl number 3999\n rule 10 permit ip\n"
        assert check_anchors(
            cfg, ("rule 10 permit ip source any destination any",)) == []

    def test_different_action_is_not_accepted(self):
        cfg = "acl number 3999\n rule 10 deny ip\n"
        assert check_anchors(
            cfg, ("rule 10 permit ip source any destination any",)) != []

    def test_different_protocol_is_not_accepted(self):
        cfg = "acl number 3999\n rule 10 permit tcp\n"
        assert check_anchors(
            cfg, ("rule 10 permit ip source any destination any",)) != []

    def test_concrete_port_is_required(self):
        cfg = "acl number 3999\n rule 10 deny tcp source any destination any\n"
        assert check_anchors(
            cfg,
            ("rule 10 deny tcp source any destination any "
             "destination-port eq 443",),
        ) != []

    def test_concrete_port_is_accepted_when_present(self):
        cfg = ("acl number 3999\n rule 10 deny tcp source any destination any "
               "destination-port eq 443\n")
        assert check_anchors(
            cfg,
            ("rule 10 deny tcp source any destination any "
             "destination-port eq 443",),
        ) == []

    def test_concrete_source_is_required(self):
        cfg = "acl number 3999\n rule 5 permit ip source 10.0.0.0 0.0.0.255\n"
        assert check_anchors(
            cfg, ("rule 5 permit ip source 10.0.0.0 0.0.0.255",)) == []
        assert check_anchors(
            cfg, ("rule 5 permit ip source 10.9.9.0 0.0.0.255",)) != []

    def test_missing_rule_is_reported(self):
        cfg = "acl number 3999\n"
        assert check_anchors(
            cfg, ("rule 10 permit ip source any destination any",)) != []


# ── Política (allowlist declarada, não tautológica) ────────────────
class TestFormPolicy:
    def test_acl_allowlist_declares_the_expected_shapes(self):
        patterns = get_form_spec("acl").allow_patterns
        assert patterns, "a ACL precisa de allowlist declarada"
        joined = " ".join(patterns)
        assert "acl" in joined and "traffic-filter" in joined

    def test_acl_confirm_patterns_cover_policy_application(self):
        patterns = get_form_spec("acl").confirm_patterns
        assert any("traffic-filter" in p for p in patterns)
        assert any("inbound" in p for p in patterns)

    def test_route_allowlist_declares_its_shapes(self):
        patterns = get_form_spec("static_route").allow_patterns
        assert any("route-static" in p for p in patterns)
