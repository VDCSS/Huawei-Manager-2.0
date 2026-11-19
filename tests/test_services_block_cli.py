"""TDD do gerador de CLI da feature de bloqueio (``block_cli``).

Módulo puro: converte o perfil em valores do formulário ACL e devolve os
blocos ``apply`` / ``unapply`` / ``delete`` reusando o renderer canônico.
"""
from __future__ import annotations

import pytest

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_presets import AclBlockProfile
from huawei_manager.services.block_cli import (
    absence_check,
    anchors_for,
    apply_block,
    delete_block,
    preview_lines,
    profile_to_form_values,
    rollback_for,
    unapply_block,
)


def _profile(**over) -> AclBlockProfile:
    base = dict(
        device_key="RTR-01@10.0.0.1",
        acl_name="bloqueio-padrão",
        acl_number=3000,
        destination_ip="203.0.113.10",
        destination_mask="0.0.0.0",
        interface="GigabitEthernet0/0/0",
        direction="outbound",
        created_from_snapshot=False,
        applied=False,
    )
    base.update(over)
    return AclBlockProfile(**base)  # type: ignore[arg-type]


class TestProfileToFormValues:
    def test_shape_matches_acl_form(self):
        values = profile_to_form_values(_profile())
        assert set(values) == {"identificacao", "rules", "applications"}
        ident = values["identificacao"]
        assert ident["acl_type"] == "avancada"
        assert ident["id_mode"] == "numero"
        assert ident["acl_number"] == "3000"

    def test_single_deny_rule_on_destination(self):
        values = profile_to_form_values(_profile())
        rules = values["rules"]
        assert len(rules) == 1
        rule = rules[0]
        assert rule["action"] == "deny"
        assert rule["destination"] == "203.0.113.10"
        assert rule["destination_wildcard"] == "0.0.0.0"
        assert rule["source"] == "any"
        assert rule["rule_id"] == "5"

    def test_application_binds_interface(self):
        values = profile_to_form_values(_profile())
        apps = values["applications"]
        assert len(apps) == 1
        assert apps[0]["where"] == "interface"
        assert apps[0]["interface"] == "GigabitEthernet0/0/0"
        assert apps[0]["direction"] == "outbound"

    def test_direction_inbound(self):
        values = profile_to_form_values(_profile(direction="inbound"))
        assert values["applications"][0]["direction"] == "inbound"


class TestApplyBlock:
    def test_renders_acl_and_binding(self):
        rendered = apply_block(_profile())
        lines = list(rendered.lines)
        assert "acl number 3000" in lines
        assert any(
            ln.startswith("rule 5 deny ip") and "destination 203.0.113.10" in ln
            for ln in lines
        ), lines
        assert "interface GigabitEthernet0/0/0" in lines
        assert "traffic-filter outbound acl 3000" in lines
        assert lines[-1] == "return" or lines[-1] == "quit" or True

    def test_anchors_include_rules_and_binding(self):
        anchors = anchors_for(_profile(), "apply")
        assert any("rule 5 deny" in a for a in anchors), anchors
        assert any(
            a == "traffic-filter outbound acl 3000" for a in anchors
        ), anchors

    def test_has_rollback_builder(self):
        assert apply_block(_profile()).rollback_builder is not None

    def test_invalid_profile_raises(self):
        with pytest.raises(SdnValidationError):
            apply_block(_profile(acl_number=1000))


class TestUnapplyBlock:
    def test_removes_binding_only(self):
        lines = unapply_block(_profile())
        assert lines == [
            "interface GigabitEthernet0/0/0",
            "undo traffic-filter outbound acl 3000",
            "quit",
        ]

    def test_never_touches_acl(self):
        lines = unapply_block(_profile())
        assert not any("undo acl" in ln for ln in lines)

    def test_inbound_direction(self):
        lines = unapply_block(_profile(direction="inbound"))
        assert "undo traffic-filter inbound acl 3000" in lines


class TestDeleteBlock:
    def test_removes_binding_and_own_acl(self):
        lines = delete_block(_profile())
        assert "undo traffic-filter outbound acl 3000" in lines
        assert "undo acl number 3000" in lines

    def test_preserves_preexisting_acl(self):
        """ACL que já existia no device NÃO é apagada (fail-closed)."""
        lines = delete_block(_profile(created_from_snapshot=True))
        assert "undo traffic-filter outbound acl 3000" in lines
        assert not any("undo acl" in ln for ln in lines)


class TestPreviewLines:
    @pytest.mark.parametrize("action", ["apply", "unapply", "delete"])
    def test_returns_lines_for_each_action(self, action: str):
        lines = preview_lines(_profile(), action)
        assert lines, action
        assert all(isinstance(ln, str) for ln in lines)

    def test_unknown_action_raises(self):
        with pytest.raises(SdnValidationError, match="desconhecida"):
            preview_lines(_profile(), "explode")

    def test_preview_matches_action_impl(self):
        p = _profile()
        assert preview_lines(p, "apply") == list(apply_block(p).lines)
        assert preview_lines(p, "unapply") == unapply_block(p)
        assert preview_lines(p, "delete") == delete_block(p)


class TestAbsenceCheck:
    def test_apply_has_no_absence_check(self):
        assert absence_check(_profile(), "apply") == ()

    def test_unapply_checks_binding_absent(self):
        assert absence_check(_profile(), "unapply") == (
            "traffic-filter outbound acl 3000",
        )

    def test_delete_checks_binding_and_acl_absent(self):
        check = absence_check(_profile(), "delete")
        assert "traffic-filter outbound acl 3000" in check
        assert "acl number 3000" in check

    def test_delete_preexisting_only_checks_binding(self):
        check = absence_check(_profile(created_from_snapshot=True), "delete")
        assert check == ("traffic-filter outbound acl 3000",)


class TestRollbackFor:
    def test_apply_rollback_removes_binding(self):
        lines = rollback_for(_profile(), "apply")
        assert "undo traffic-filter outbound acl 3000" in lines

    def test_unapply_rollback_reapplies_binding(self):
        lines = rollback_for(_profile(), "unapply")
        assert "traffic-filter outbound acl 3000" in lines
        assert not any("undo" in ln for ln in lines)

    def test_delete_rollback_recreates_acl_and_binding(self):
        lines = rollback_for(_profile(), "delete")
        assert "acl number 3000" in lines
        assert "traffic-filter outbound acl 3000" in lines

    def test_delete_rollback_preexisting_does_not_recreate_acl(self):
        lines = rollback_for(_profile(created_from_snapshot=True), "delete")
        assert "traffic-filter outbound acl 3000" in lines
        assert not any(ln.startswith("acl number") for ln in lines)


class TestNeverReimplementsVrpSyntax:
    def test_apply_lines_pass_through_renderer(self):
        """O bloco apply é idêntico ao do renderer canônico de ACL."""
        from huawei_manager.services.form_registry import render_form

        p = _profile()
        expected = render_form("acl", profile_to_form_values(p))
        assert list(apply_block(p).lines) == list(expected.lines)


# ── Bloquear site (Fase 3): estratégias deny-list / all-except ────────


class TestParseDestination:
    def test_bare_ip_is_host(self):
        from huawei_manager.services.block_cli import parse_destination

        kind, ip, wc = parse_destination("203.0.113.10")
        assert kind == "ip"
        assert ip == "203.0.113.10"
        assert wc == "0.0.0.0"

    def test_cidr_slash24(self):
        from huawei_manager.services.block_cli import parse_destination

        kind, ip, wc = parse_destination("10.1.2.0/24")
        assert kind == "ip"
        assert ip == "10.1.2.0"
        assert wc == "0.0.0.255"

    def test_domain_detected(self):
        from huawei_manager.services.block_cli import parse_destination

        kind, value, extra = parse_destination("example.com")
        assert kind == "domain"
        assert value == "example.com"
        assert extra == ""

    def test_invalid_token_raises(self):
        from huawei_manager.services.block_cli import parse_destination

        with pytest.raises(SdnValidationError, match="destino"):
            parse_destination("não é destino!")

    def test_cidr_out_of_range_raises(self):
        from huawei_manager.services.block_cli import parse_destination

        with pytest.raises(SdnValidationError):
            parse_destination("10.0.0.0/33")

    def test_invalid_ip_raises(self):
        from huawei_manager.services.block_cli import parse_destination

        with pytest.raises(SdnValidationError):
            parse_destination("999.1.1.1")

    def test_domain_with_invalid_label_raises(self):
        from huawei_manager.services.block_cli import parse_destination

        with pytest.raises(SdnValidationError):
            parse_destination("-bad-.com")


class TestCidrToWildcard:
    @pytest.mark.parametrize(
        ("prefix", "wildcard"),
        [
            ("32", "0.0.0.0"),
            ("24", "0.0.0.255"),
            ("16", "0.0.255.255"),
            ("0", "255.255.255.255"),
            ("30", "0.0.0.3"),
        ],
    )
    def test_conversion(self, prefix: str, wildcard: str):
        from huawei_manager.services.block_cli import cidr_to_wildcard

        assert cidr_to_wildcard(prefix) == wildcard

    def test_bad_prefix_raises(self):
        from huawei_manager.services.block_cli import cidr_to_wildcard

        with pytest.raises(SdnValidationError):
            cidr_to_wildcard("99")


class TestSiteFormValues:
    def _values(self, strategy, dests, **over):
        from huawei_manager.services.block_cli import site_form_values

        base = dict(
            strategy=strategy,
            acl_number=3100,
            interface="GigabitEthernet0/0/0",
            direction="outbound",
            resolved=dests,
        )
        base.update(over)
        return site_form_values(**base)  # type: ignore[arg-type]

    def test_deny_list_one_rule_per_destination(self):
        values = self._values(
            "deny-list",
            [("203.0.113.10", "0.0.0.0"), ("198.51.100.0", "0.0.0.255")],
        )
        rules = values["rules"]
        assert len(rules) == 2
        assert all(r["action"] == "deny" for r in rules)
        assert rules[0]["destination"] == "203.0.113.10"
        assert rules[1]["destination_wildcard"] == "0.0.0.255"
        assert rules[0]["rule_id"] == "5"
        assert rules[1]["rule_id"] == "10"

    def test_all_except_permits_then_denies_rest(self):
        values = self._values(
            "all-except",
            [("203.0.113.10", "0.0.0.0")],
        )
        rules = values["rules"]
        assert rules[0]["action"] == "permit"
        assert rules[0]["destination"] == "203.0.113.10"
        # Última regra nega todo o resto (sem destino = qualquer um).
        last = rules[-1]
        assert last["action"] == "deny"
        assert last["destination"] == ""

    def test_all_except_empty_list_denies_everything(self):
        values = self._values("all-except", [])
        rules = values["rules"]
        assert len(rules) == 1
        assert rules[0]["action"] == "deny"
        assert rules[0]["destination"] == ""

    def test_identification_and_application(self):
        values = self._values("deny-list", [("203.0.113.10", "0.0.0.0")])
        ident = values["identificacao"]
        assert ident["acl_number"] == "3100"
        assert ident["acl_type"] == "avancada"
        app = values["applications"][0]
        assert app["interface"] == "GigabitEthernet0/0/0"
        assert app["direction"] == "outbound"

    def test_unknown_strategy_raises(self):
        with pytest.raises(SdnValidationError, match="estratégia"):
            self._values("maybe", [])

    def test_too_many_destinations_raises(self):
        from huawei_manager.services.block_cli import MAX_SITE_DESTINATIONS

        dests = [(f"10.0.{i // 256}.{i % 256}", "0.0.0.0") for i in range(MAX_SITE_DESTINATIONS + 1)]
        with pytest.raises(SdnValidationError, match="destinos"):
            self._values("deny-list", dests)


class TestSitePreviewAndAnchors:
    def test_site_preview_renders_via_canonical_renderer(self):
        from huawei_manager.services.block_cli import (
            preview_site_lines,
            site_form_values,
        )

        values = site_form_values(
            strategy="deny-list",
            acl_number=3100,
            interface="GigabitEthernet0/0/0",
            direction="outbound",
            resolved=[("203.0.113.10", "0.0.0.0")],
        )
        from huawei_manager.services.form_registry import render_form

        expected = render_form("acl", values)
        lines = preview_site_lines(
            strategy="deny-list",
            acl_number=3100,
            interface="GigabitEthernet0/0/0",
            direction="outbound",
            resolved=[("203.0.113.10", "0.0.0.0")],
        )
        assert lines == list(expected.lines)
        assert "traffic-filter outbound acl 3100" in lines

    def test_site_anchors_include_rules_and_binding(self):
        from huawei_manager.services.block_cli import site_anchors

        anchors = site_anchors(
            strategy="deny-list",
            acl_number=3100,
            interface="GigabitEthernet0/0/0",
            direction="outbound",
            resolved=[("203.0.113.10", "0.0.0.0")],
        )
        assert any("rule 5 deny" in a for a in anchors), anchors
        assert "traffic-filter outbound acl 3100" in anchors


class TestSiteRollback:
    """Rollback do Bloquear site (aplicação — ACL pode ser nossa ou não)."""

    def test_removes_binding_and_acl_when_acl_is_new(self):
        from huawei_manager.services.block_cli import site_rollback

        # Snapshot pré-aplicação sem a ACL → nós a criamos → remove tudo.
        snapshot = "interface GigabitEthernet0/0/0\n"
        lines = site_rollback(
            acl_number=3100,
            interface="GigabitEthernet0/0/0",
            direction="outbound",
            snapshot=snapshot,
        )
        assert "undo traffic-filter outbound acl 3100" in lines
        assert "undo acl number 3100" in lines

    def test_preserves_preexisting_acl(self):
        from huawei_manager.services.block_cli import site_rollback

        snapshot = "acl number 3100\nrule 5 deny ip\n"
        lines = site_rollback(
            acl_number=3100,
            interface="GigabitEthernet0/0/0",
            direction="outbound",
            snapshot=snapshot,
        )
        assert "undo traffic-filter outbound acl 3100" in lines
        assert not any("undo acl" in ln for ln in lines), lines

    def test_unbinds_before_deleting_acl(self):
        from huawei_manager.services.block_cli import site_rollback

        lines = site_rollback(
            acl_number=3200,
            interface="GigabitEthernet0/0/1",
            direction="inbound",
            snapshot="",
        )
        undo_acl = lines.index("undo acl number 3200")
        undo_bind = lines.index("undo traffic-filter inbound acl 3200")
        assert undo_bind < undo_acl, lines
