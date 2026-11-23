"""TDD do gerador de CLI da feature de bloqueio (``block_cli``).

Módulo puro: converte o perfil em valores do formulário ACL e devolve os
blocos ``apply`` / ``unapply`` / ``delete`` reusando o renderer canônico.

A aplicação usa a **cadeia traffic policy** (classifier → behavior →
policy), não o ``traffic-filter`` direto — ver
``huawei_manager.services.traffic_policy``.
"""
from __future__ import annotations

import pytest

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_presets import AclBlockProfile
from huawei_manager.services.block_cli import (
    absence_check,
    anchors_for,
    apply_block,
    chain_absence,
    chain_anchors,
    delete_block,
    delete_chain_lines,
    policy_steps,
    preview_lines,
    preview_site_lines,
    profile_to_form_values,
    rollback_for,
    site_anchors,
    site_form_values,
    site_policy_steps,
    site_rollback,
    suggested_chain,
    unapply_block,
    update_chain_lines,
)
from huawei_manager.services.traffic_policy import TrafficPolicyChain, render_chain


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


def _names(prefix: str, number: int) -> tuple[str, str, str]:
    """Nomes determinísticos da cadeia traffic policy."""
    base = f"{prefix}_{number}"
    return f"C_{base}", f"B_{base}", f"P_{base}"


class TestProfileToFormValues:
    def test_shape_matches_acl_form(self):
        values = profile_to_form_values(_profile())
        assert set(values) == {
            "identificacao", "rules", "applications", "traffic_policy",
        }
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

    def test_application_uses_traffic_policy_chain(self):
        values = profile_to_form_values(_profile())
        apps = values["applications"]
        assert len(apps) == 1
        assert apps[0]["where"] == "traffic policy"
        assert apps[0]["interface"] == "GigabitEthernet0/0/0"
        assert apps[0]["direction"] == "outbound"

    def test_traffic_policy_names_are_deterministic(self):
        classifier, behavior, policy = _names("BLOQ", 3000)
        tp = profile_to_form_values(_profile())["traffic_policy"]
        assert tp["classifier_name"] == classifier
        assert tp["behavior_name"] == behavior
        assert tp["policy_name"] == policy
        # 'permit' = o sistema respeita o permit/deny da própria ACL.
        assert tp["behavior_action"] == "permit"

    def test_direction_inbound(self):
        values = profile_to_form_values(_profile(direction="inbound"))
        assert values["applications"][0]["direction"] == "inbound"


class TestApplyBlock:
    def test_renders_acl_and_traffic_policy_chain(self):
        rendered = apply_block(_profile())
        lines = list(rendered.lines)
        _c, _b, p = _names("BLOQ", 3000)
        assert "acl number 3000" in lines
        assert any(
            ln.startswith("rule 5 deny ip") and "destination 203.0.113.10" in ln
            for ln in lines
        ), lines
        assert "interface GigabitEthernet0/0/0" in lines
        assert f"traffic-policy {p} outbound" in lines

    def test_chain_is_complete(self):
        lines = list(apply_block(_profile()).lines)
        classifier, behavior, policy = _names("BLOQ", 3000)
        assert f"traffic classifier {classifier}" in lines
        assert "if-match acl 3000" in lines
        assert f"traffic behavior {behavior}" in lines
        assert "permit" in lines
        assert f"traffic policy {policy}" in lines
        assert f"classifier {classifier} behavior {behavior}" in lines

    def test_never_uses_traffic_filter(self):
        """Regressão do pedido: a aplicação NÃO usa traffic-filter."""
        lines = list(apply_block(_profile()).lines)
        assert not any("traffic-filter" in ln for ln in lines), lines

    def test_anchors_include_rules_chain_and_binding(self):
        anchors = anchors_for(_profile(), "apply")
        classifier, behavior, policy = _names("BLOQ", 3000)
        assert any("rule 5 deny" in a for a in anchors), anchors
        assert f"traffic-policy {policy} outbound" in anchors
        assert f"traffic classifier {classifier}" in anchors
        assert "if-match acl 3000" in anchors
        assert f"classifier {classifier} behavior {behavior}" in anchors

    def test_has_rollback_builder(self):
        assert apply_block(_profile()).rollback_builder is not None

    def test_invalid_profile_raises(self):
        with pytest.raises(SdnValidationError):
            apply_block(_profile(acl_number=1000))


class TestUnapplyBlock:
    def test_removes_binding_only(self):
        _c, _b, p = _names("BLOQ", 3000)
        lines = unapply_block(_profile())
        assert lines == [
            "interface GigabitEthernet0/0/0",
            f"undo traffic-policy {p} outbound",
            "quit",
        ]

    def test_never_touches_acl_or_chain(self):
        lines = unapply_block(_profile())
        assert not any("undo acl" in ln for ln in lines), lines
        assert not any("undo traffic " in ln for ln in lines), lines

    def test_inbound_direction(self):
        _c, _b, p = _names("BLOQ", 3000)
        lines = unapply_block(_profile(direction="inbound"))
        assert f"undo traffic-policy {p} inbound" in lines


class TestDeleteBlock:
    def test_removes_binding_chain_and_own_acl(self):
        classifier, behavior, policy = _names("BLOQ", 3000)
        lines = delete_block(_profile())
        assert f"undo traffic-policy {policy} outbound" in lines
        assert f"undo traffic policy {policy}" in lines
        assert f"undo traffic behavior {behavior}" in lines
        assert f"undo traffic classifier {classifier}" in lines
        assert "undo acl number 3000" in lines

    def test_preserves_preexisting_acl_and_chain(self):
        """ACL/cadeia que já existiam no device NÃO são apagadas."""
        lines = delete_block(_profile(created_from_snapshot=True))
        assert not any("undo acl" in ln for ln in lines), lines
        assert not any("undo traffic " in ln for ln in lines), lines


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
        _c, _b, p = _names("BLOQ", 3000)
        assert absence_check(_profile(), "unapply") == (
            f"traffic-policy {p} outbound",
        )

    def test_delete_checks_binding_acl_and_chain_absent(self):
        classifier, behavior, policy = _names("BLOQ", 3000)
        check = absence_check(_profile(), "delete")
        assert f"traffic-policy {policy} outbound" in check
        assert "acl number 3000" in check
        assert f"traffic classifier {classifier}" in check
        assert f"traffic behavior {behavior}" in check
        assert f"traffic policy {policy}" in check

    def test_delete_preexisting_only_checks_binding(self):
        _c, _b, p = _names("BLOQ", 3000)
        check = absence_check(_profile(created_from_snapshot=True), "delete")
        assert check == (f"traffic-policy {p} outbound",)


class TestRollbackFor:
    def test_apply_rollback_removes_binding_chain_and_acl(self):
        classifier, behavior, policy = _names("BLOQ", 3000)
        lines = rollback_for(_profile(), "apply", snapshot="")
        assert f"undo traffic-policy {policy} outbound" in lines
        assert f"undo traffic policy {policy}" in lines
        assert f"undo traffic behavior {behavior}" in lines
        assert f"undo traffic classifier {classifier}" in lines
        assert "undo acl number 3000" in lines

    def test_apply_rollback_preserves_preexisting_acl(self):
        snapshot = "acl number 3000\nrule 9 permit ip\n"
        lines = rollback_for(_profile(), "apply", snapshot=snapshot)
        assert not any("undo acl" in ln for ln in lines), lines

    def test_unapply_rollback_reapplies_binding(self):
        _c, _b, p = _names("BLOQ", 3000)
        lines = rollback_for(_profile(), "unapply", snapshot="")
        assert f"traffic-policy {p} outbound" in lines
        assert not any("undo" in ln for ln in lines), lines

    def test_delete_rollback_recreates_acl_chain_and_binding(self):
        classifier, behavior, policy = _names("BLOQ", 3000)
        lines = rollback_for(_profile(), "delete", snapshot="")
        assert "acl number 3000" in lines
        assert f"traffic classifier {classifier}" in lines
        assert f"traffic-policy {policy} outbound" in lines

    def test_delete_rollback_preexisting_does_not_recreate_acl(self):
        _c, _b, p = _names("BLOQ", 3000)
        lines = rollback_for(_profile(created_from_snapshot=True), "delete",
                             snapshot="")
        assert f"traffic-policy {p} outbound" in lines
        assert not any(ln.startswith("acl number") for ln in lines), lines


class TestNeverReimplementsVrpSyntax:
    def test_apply_lines_pass_through_renderer(self):
        """O bloco apply é idêntico ao do renderer canônico de ACL."""
        from huawei_manager.services.form_registry import render_form

        p = _profile()
        expected = render_form("acl", profile_to_form_values(p))
        assert list(apply_block(p).lines) == list(expected.lines)


# ── Bloquear site: estratégias deny-list / all-except ────────


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
        assert app["where"] == "traffic policy"
        assert app["interface"] == "GigabitEthernet0/0/0"
        assert app["direction"] == "outbound"

    def test_traffic_policy_names_are_deterministic(self):
        classifier, behavior, policy = _names("SITE", 3100)
        tp = self._values("deny-list", [("203.0.113.10", "0.0.0.0")])[
            "traffic_policy"
        ]
        assert tp["classifier_name"] == classifier
        assert tp["behavior_name"] == behavior
        assert tp["policy_name"] == policy

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
        _c, _b, p = _names("SITE", 3100)
        assert f"traffic-policy {p} outbound" in lines
        assert not any("traffic-filter" in ln for ln in lines), lines

    def test_site_anchors_include_rules_chain_and_binding(self):
        from huawei_manager.services.block_cli import site_anchors

        anchors = site_anchors(
            strategy="deny-list",
            acl_number=3100,
            interface="GigabitEthernet0/0/0",
            direction="outbound",
            resolved=[("203.0.113.10", "0.0.0.0")],
        )
        assert any("rule 5 deny" in a for a in anchors), anchors
        _c, _b, p = _names("SITE", 3100)
        assert f"traffic-policy {p} outbound" in anchors
        assert f"traffic classifier {_c}" in anchors


class TestSiteRollback:
    """Rollback do Bloquear site (aplicação — ACL pode ser nossa ou não)."""

    _KW = dict(
        strategy="deny-list",
        acl_number=3100,
        interface="GigabitEthernet0/0/0",
        direction="outbound",
        resolved=(("203.0.113.10", "0.0.0.0"),),
    )

    def test_removes_binding_chain_and_acl_when_acl_is_new(self):
        from huawei_manager.services.block_cli import site_rollback

        lines = site_rollback(snapshot="interface GigabitEthernet0/0/0\n",
                              **self._KW)
        _c, _b, p = _names("SITE", 3100)
        assert f"undo traffic-policy {p} outbound" in lines
        assert f"undo traffic policy {p}" in lines
        assert f"undo traffic classifier {_c}" in lines
        assert "undo acl number 3100" in lines

    def test_preserves_preexisting_acl(self):
        from huawei_manager.services.block_cli import site_rollback

        snapshot = "acl number 3100\nrule 5 deny ip\n"
        lines = site_rollback(snapshot=snapshot, **self._KW)
        assert not any("undo acl" in ln for ln in lines), lines

    def test_unbinds_before_deleting_acl(self):
        from huawei_manager.services.block_cli import site_rollback

        lines = site_rollback(snapshot="", **self._KW)
        undo_acl = lines.index("undo acl number 3100")
        _c, _b, p = _names("SITE", 3100)
        undo_bind = lines.index(f"undo traffic-policy {p} outbound")
        assert undo_bind < undo_acl, lines


# ── Cadeia traffic policy customizada (nomes/ação injetados) ──────────


def _custom_chain(action: str = "deny") -> TrafficPolicyChain:
    """Cadeia com nomes fora do padrão BLOQ/SITE (override do chamador)."""
    return TrafficPolicyChain(
        classifier="C_CUSTOM_9",
        behavior="B_CUSTOM_9",
        policy="P_CUSTOM_9",
        action=action,
    )


def _old_chain() -> TrafficPolicyChain:
    return TrafficPolicyChain(
        classifier="C_OLD", behavior="B_OLD", policy="P_OLD"
    )


def _new_chain() -> TrafficPolicyChain:
    return TrafficPolicyChain(
        classifier="C_NEW", behavior="B_NEW", policy="P_NEW", action="deny"
    )


class TestSuggestedChain:
    def test_matches_deterministic_default(self):
        assert suggested_chain("BLOQ", 3000) == TrafficPolicyChain(
            classifier="C_BLOQ_3000",
            behavior="B_BLOQ_3000",
            policy="P_BLOQ_3000",
            action="permit",
        )

    def test_site_prefix(self):
        assert suggested_chain("SITE", 3100).policy == "P_SITE_3100"


class TestCustomChainOverrides:
    def test_profile_to_form_values_uses_custom_names_and_action(self):
        chain = _custom_chain()
        tp = profile_to_form_values(_profile(), chain=chain)["traffic_policy"]
        assert tp == {
            "classifier_name": "C_CUSTOM_9",
            "behavior_name": "B_CUSTOM_9",
            "policy_name": "P_CUSTOM_9",
            "behavior_action": "deny",
        }

    def test_default_profile_still_uses_bloq(self):
        tp = profile_to_form_values(_profile())["traffic_policy"]
        assert tp["classifier_name"] == "C_BLOQ_3000"
        assert tp["behavior_action"] == "permit"

    def test_apply_block_anchors_and_absence_use_custom_chain(self):
        chain = _custom_chain()
        p = _profile()
        lines = list(apply_block(p, chain=chain).lines)
        assert f"traffic classifier {chain.classifier}" in lines
        assert f"traffic behavior {chain.behavior}" in lines
        assert f"traffic policy {chain.policy}" in lines
        assert f"classifier {chain.classifier} behavior {chain.behavior}" in lines
        assert "deny" in lines
        assert f"traffic-policy {chain.policy} outbound" in lines
        assert not any("P_BLOQ_3000" in ln for ln in lines)

        anchors = anchors_for(p, "apply", chain=chain)
        assert f"traffic classifier {chain.classifier}" in anchors
        assert f"traffic-policy {chain.policy} outbound" in anchors

        assert absence_check(p, "unapply", chain=chain) == (
            f"traffic-policy {chain.policy} outbound",
        )
        absence = absence_check(p, "delete", chain=chain)
        assert f"traffic classifier {chain.classifier}" in absence
        assert f"traffic behavior {chain.behavior}" in absence
        assert f"traffic policy {chain.policy}" in absence

    @pytest.mark.parametrize("action", ["apply", "unapply", "delete"])
    def test_preview_lines_uses_custom_chain(self, action: str):
        chain = _custom_chain()
        lines = preview_lines(_profile(), action, chain=chain)
        assert lines, action
        assert any(chain.policy in ln for ln in lines), lines
        assert not any("P_BLOQ_3000" in ln for ln in lines), lines

    def test_rollback_for_apply_uses_custom_chain(self):
        chain = _custom_chain()
        lines = rollback_for(_profile(), "apply", snapshot="", chain=chain)
        assert f"undo traffic-policy {chain.policy} outbound" in lines
        assert f"undo traffic policy {chain.policy}" in lines
        assert f"undo traffic behavior {chain.behavior}" in lines
        assert f"undo traffic classifier {chain.classifier}" in lines

    def test_rollback_for_unapply_delete_uses_custom_chain(self):
        chain = _custom_chain()
        p = _profile()
        unapply = rollback_for(p, "unapply", snapshot="", chain=chain)
        assert f"traffic-policy {chain.policy} outbound" in unapply
        delete = rollback_for(p, "delete", snapshot="", chain=chain)
        assert f"traffic classifier {chain.classifier}" in delete
        assert f"traffic-policy {chain.policy} outbound" in delete


class TestCustomChainPolicySteps:
    def test_apply_steps_use_custom_chain(self):
        chain = _custom_chain()
        p = _profile()
        steps = policy_steps(p, "apply", chain=chain)
        assert len(steps) == 5
        flattened = [ln for step in steps for ln in step.lines]
        assert flattened == list(apply_block(p, chain=chain).lines)
        assert f"traffic classifier {chain.classifier}" in steps[1].lines
        assert "if-match acl 3000" in steps[1].lines
        assert "deny" in steps[2].lines
        assert f"traffic policy {chain.policy}" in steps[3].lines
        assert f"traffic-policy {chain.policy} outbound" in steps[4].lines

    def test_delete_steps_use_custom_chain_in_reverse_order(self):
        chain = _custom_chain()
        steps = policy_steps(_profile(), "delete", chain=chain)
        assert [step.number for step in steps] == [5, 4, 3, 2, 1]
        assert steps[0].lines == (
            "interface GigabitEthernet0/0/0",
            f"undo traffic-policy {chain.policy} outbound",
            "quit",
        )
        assert steps[1].lines == (f"undo traffic policy {chain.policy}",)
        assert steps[2].lines == (f"undo traffic behavior {chain.behavior}",)
        assert steps[3].lines == (f"undo traffic classifier {chain.classifier}",)
        assert steps[4].lines == ("undo acl number 3000",)

    def test_unapply_step_uses_custom_chain(self):
        chain = _custom_chain()
        steps = policy_steps(_profile(), "unapply", chain=chain)
        assert len(steps) == 1
        assert f"undo traffic-policy {chain.policy} outbound" in steps[0].lines


class TestSiteCustomChain:
    _KW = dict(
        strategy="deny-list",
        acl_number=3100,
        interface="GigabitEthernet0/0/0",
        direction="outbound",
        resolved=(("203.0.113.10", "0.0.0.0"),),
    )

    def test_site_form_values_uses_custom_names_and_action(self):
        chain = _custom_chain()
        tp = site_form_values(chain=chain, **self._KW)["traffic_policy"]
        assert tp == {
            "classifier_name": "C_CUSTOM_9",
            "behavior_name": "B_CUSTOM_9",
            "policy_name": "P_CUSTOM_9",
            "behavior_action": "deny",
        }

    def test_default_site_still_uses_site(self):
        tp = site_form_values(**self._KW)["traffic_policy"]
        assert tp["policy_name"] == "P_SITE_3100"
        assert tp["behavior_action"] == "permit"

    def test_preview_site_lines_and_anchors_use_custom_chain(self):
        chain = _custom_chain()
        lines = preview_site_lines(chain=chain, **self._KW)
        assert f"traffic classifier {chain.classifier}" in lines
        assert f"traffic policy {chain.policy}" in lines
        assert f"traffic-policy {chain.policy} outbound" in lines
        assert not any("P_SITE_3100" in ln for ln in lines), lines
        anchors = site_anchors(chain=chain, **self._KW)
        assert f"traffic classifier {chain.classifier}" in anchors
        assert f"traffic-policy {chain.policy} outbound" in anchors

    def test_site_rollback_uses_custom_chain(self):
        chain = _custom_chain()
        lines = site_rollback(snapshot="", chain=chain, **self._KW)
        assert f"undo traffic-policy {chain.policy} outbound" in lines
        assert f"undo traffic policy {chain.policy}" in lines
        assert f"undo traffic classifier {chain.classifier}" in lines

    def test_site_policy_steps_use_custom_chain(self):
        chain = _custom_chain()
        steps = site_policy_steps(chain=chain, **self._KW)
        assert len(steps) == 5
        flattened = [ln for step in steps for ln in step.lines]
        assert flattened == preview_site_lines(chain=chain, **self._KW)
        assert f"traffic classifier {chain.classifier}" in steps[1].lines
        assert "deny" in steps[2].lines
        assert f"traffic policy {chain.policy}" in steps[3].lines
        assert f"traffic-policy {chain.policy} outbound" in steps[4].lines


class TestChainAnchorHelpers:
    def test_chain_anchors_are_render_chain_anchors_plus_binding(self):
        chain = _custom_chain()
        expected = (*render_chain(chain, "3000")[1],
                    "traffic-policy P_CUSTOM_9 inbound")
        assert chain_anchors(
            chain, acl_number=3000,
            interface="GigabitEthernet0/0/0", direction="inbound",
        ) == expected

    def test_chain_absence_is_render_chain_lines_plus_binding(self):
        chain = _custom_chain()
        expected = (*render_chain(chain, "")[0],
                    "traffic-policy P_CUSTOM_9 outbound")
        assert chain_absence(
            chain, interface="GigabitEthernet0/0/0", direction="outbound",
        ) == expected


class TestUpdateChainLines:
    def test_order_undo_binding_undo_chain_create_new_bind_new(self):
        old, new = _old_chain(), _new_chain()
        lines = update_chain_lines(
            old, new, acl_number=3000,
            interface="GigabitEthernet0/0/1", direction="inbound",
        )
        expected = [
            "interface GigabitEthernet0/0/1",
            "undo traffic-policy P_OLD inbound",
            "quit",
            "undo traffic policy P_OLD",
            "undo traffic behavior B_OLD",
            "undo traffic classifier C_OLD",
            *render_chain(new, "3000")[0],
            "interface GigabitEthernet0/0/1",
            "traffic-policy P_NEW inbound",
            "quit",
        ]
        assert lines == expected

    def test_no_acl_lines(self):
        lines = update_chain_lines(
            _old_chain(), _new_chain(), acl_number=3000,
            interface="Gi0/0/1", direction="inbound",
        )
        assert not any("undo acl" in ln for ln in lines), lines
        assert not any(ln.startswith("acl number") for ln in lines), lines
        assert not any(ln.startswith("rule ") for ln in lines), lines

    def test_preexisting_preserves_old_objects(self):
        lines = update_chain_lines(
            _old_chain(), _new_chain(), acl_number=3000,
            interface="Gi0/0/1", direction="inbound", preexisting=True,
        )
        assert not any("undo traffic " in ln for ln in lines), lines
        assert "undo traffic-policy P_OLD inbound" in lines
        assert "traffic classifier C_NEW" in lines
        assert "traffic-policy P_NEW inbound" in lines


class TestDeleteChainLines:
    def test_removes_binding_then_chain_without_acl(self):
        old = _old_chain()
        lines = delete_chain_lines(
            old, interface="GigabitEthernet0/0/1", direction="outbound",
        )
        assert lines == [
            "interface GigabitEthernet0/0/1",
            "undo traffic-policy P_OLD outbound",
            "quit",
            "undo traffic policy P_OLD",
            "undo traffic behavior B_OLD",
            "undo traffic classifier C_OLD",
        ]
        assert not any("undo acl" in ln for ln in lines), lines
        assert not any("acl number" in ln for ln in lines), lines

    def test_preexisting_preserves_objects(self):
        lines = delete_chain_lines(
            _old_chain(), interface="Gi0/0/1", direction="inbound",
            preexisting=True,
        )
        assert not any("undo traffic " in ln for ln in lines), lines
        assert lines == [
            "interface Gi0/0/1",
            "undo traffic-policy P_OLD inbound",
            "quit",
        ]
