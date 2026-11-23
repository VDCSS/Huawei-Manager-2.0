"""TDD: passo a passo da cadeia traffic policy para os modais de bloqueio.

Os passos são **derivados** das linhas canônicas geradas por ``block_cli``
(que por sua vez usa o renderer de ACL): a soma das linhas dos passos tem
de ser exatamente o bloco enviado ao device — sem reimplementar sintaxe
VRP e sem ``traffic-filter``.
"""
from __future__ import annotations

import pytest

from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_presets import AclBlockProfile
from huawei_manager.services.block_cli import (
    apply_block,
    delete_block,
    policy_steps,
    preview_site_lines,
    site_policy_steps,
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


def _lines(steps) -> list[str]:
    return [line for step in steps for line in step.lines]


class TestPolicyStepsApply:
    def test_five_steps_in_creation_order(self):
        steps = policy_steps(_profile(), "apply")
        assert [step.number for step in steps] == [1, 2, 3, 4, 5]
        assert all(step.title and step.hint for step in steps)

    def test_steps_concatenate_to_canonical_block(self):
        profile = _profile()
        assert _lines(policy_steps(profile, "apply")) == list(
            apply_block(profile).lines
        )

    def test_step_1_is_the_acl(self):
        step = policy_steps(_profile(), "apply")[0]
        assert "acl number 3000" in step.lines
        assert any("rule 5 deny" in line for line in step.lines)

    def test_steps_2_to_4_are_the_chain(self):
        steps = policy_steps(_profile(), "apply")
        assert "traffic classifier C_BLOQ_3000" in steps[1].lines
        assert "if-match acl 3000" in steps[1].lines
        assert "traffic behavior B_BLOQ_3000" in steps[2].lines
        assert "permit" in steps[2].lines
        assert "traffic policy P_BLOQ_3000" in steps[3].lines
        assert "classifier C_BLOQ_3000 behavior B_BLOQ_3000" in steps[3].lines

    def test_step_5_is_the_interface_binding(self):
        step = policy_steps(_profile(), "apply")[4]
        assert "interface GigabitEthernet0/0/0" in step.lines
        assert "traffic-policy P_BLOQ_3000 outbound" in step.lines

    def test_no_traffic_filter_in_any_step(self):
        assert all(
            "traffic-filter" not in line
            for line in _lines(policy_steps(_profile(), "apply"))
        )


class TestPolicyStepsUnapply:
    def test_only_binding_step_is_shown(self):
        profile = _profile()
        steps = policy_steps(profile, "unapply")
        assert [step.number for step in steps] == [5]
        assert _lines(steps) == unapply_block(profile)
        assert "undo traffic-policy P_BLOQ_3000 outbound" in steps[0].lines

    def test_hint_says_acl_and_chain_remain(self):
        step = policy_steps(_profile(), "unapply")[0]
        assert "permanec" in step.hint.lower() or "fica" in step.hint.lower()


class TestPolicyStepsDelete:
    def test_reverse_order_removes_everything_we_created(self):
        profile = _profile()
        steps = policy_steps(profile, "delete")
        assert [step.number for step in steps] == [5, 4, 3, 2, 1]
        assert _lines(steps) == delete_block(profile)
        assert "undo traffic-policy P_BLOQ_3000 outbound" in steps[0].lines
        assert "undo acl number 3000" in steps[-1].lines

    def test_preexisting_acl_omits_undo_acl_step(self):
        profile = _profile(created_from_snapshot=True)
        steps = policy_steps(profile, "delete")
        assert [step.number for step in steps] == [5, 4, 3, 2]
        assert _lines(steps) == delete_block(profile)
        assert all("undo acl" not in line for line in _lines(steps))


class TestPolicyStepsValidation:
    def test_unknown_action_fails_closed(self):
        with pytest.raises(SdnValidationError, match="ação"):
            policy_steps(_profile(), "explodir")


_SITE_KW = dict(
    strategy="deny-list",
    acl_number=3100,
    interface="GigabitEthernet0/0/0",
    direction="outbound",
    resolved=(("203.0.113.10", "0.0.0.0"),),
)


class TestSitePolicySteps:
    def test_five_steps_concatenate_to_canonical_site_block(self):
        steps = site_policy_steps(**_SITE_KW)
        assert [s.number for s in steps] == [1, 2, 3, 4, 5]
        assert _lines(steps) == preview_site_lines(**_SITE_KW)

    def test_site_chain_names_use_site_prefix(self):
        steps = site_policy_steps(**_SITE_KW)
        assert "traffic classifier C_SITE_3100" in steps[1].lines
        assert "traffic behavior B_SITE_3100" in steps[2].lines
        assert "traffic policy P_SITE_3100" in steps[3].lines
        assert "traffic-policy P_SITE_3100 outbound" in steps[4].lines

    def test_deny_list_step_1_has_deny_rule(self):
        step = site_policy_steps(**_SITE_KW)[0]
        assert any("rule 5 deny" in line for line in step.lines)

    def test_all_except_step_1_has_final_deny_and_explains_it(self):
        steps = site_policy_steps(**{**_SITE_KW, "strategy": "all-except"})
        assert any("rule 999 deny ip source any" in line for line in steps[0].lines)
        assert "999" in steps[0].hint

    def test_unknown_strategy_fails_closed(self):
        with pytest.raises(SdnValidationError, match="estratégia"):
            site_policy_steps(**{**_SITE_KW, "strategy": "qualquer"})
