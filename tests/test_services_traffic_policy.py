"""TDD da cadeia ``traffic policy`` (alternativa ao ``traffic-filter``).

Cobre o passo a passo canônico do Huawei:

1. ``acl number 3000`` + regras + ``quit``;
2. ``traffic classifier C_BLOQUEIO`` / ``if-match acl 3000`` / ``quit``;
3. ``traffic behavior B_ACAO`` / ``permit`` / ``quit``;
4. ``traffic policy P_FILTRO_INTERFACE`` /
   ``classifier C_BLOQUEIO behavior B_ACAO`` / ``quit``;
5. ``interface GigabitEthernet0/0/1`` /
   ``traffic-policy P_FILTRO_INTERFACE inbound`` / ``quit``.

Regras de segurança cobertas: fail-closed (nomes exigidos, valores
resíduos rejeitados), ordem obrigatória dos blocos, rollback que preserva
o estado pré-existente do snapshot e política (allowlist/confirm).
"""
from __future__ import annotations

import pytest

from huawei_manager.basic_config.params import ParamKind
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.form_registry import (
    check_anchors,
    get_form_spec,
    render_form,
    rollback_lines,
)

_CHAIN_NAMES = {
    "classifier_name": "C_BLOQUEIO",
    "behavior_name": "B_ACAO",
    "policy_name": "P_FILTRO_INTERFACE",
    "behavior_action": "permit",
}


def _values(*, where="traffic policy", names=None, applications=None, **over):
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
                "action": "deny",
                "protocol": "ip",
                "source": "192.168.10.50",
                "source_wildcard": "0",
                "destination": "",
                "destination_wildcard": "",
                "destination_port": "",
            },
            {
                "rule_id": "10",
                "action": "permit",
                "protocol": "ip",
                "source": "any",
                "source_wildcard": "",
                "destination": "",
                "destination_wildcard": "",
                "destination_port": "",
            },
        ],
        "traffic_policy": dict(names if names is not None else _CHAIN_NAMES),
        "applications": applications if applications is not None else [
            {
                "where": where,
                "interface": "GigabitEthernet0/0/1",
                "direction": "inbound",
                "vty_range": "",
            },
        ],
    }
    base.update(over)
    return base


class TestTrafficPolicyBlock:
    def test_renders_the_canonical_block(self):
        """Bloco completo na ordem canônica do CLI VRP."""
        rendered = render_form("acl", _values())
        assert rendered.lines == (
            "acl number 3000",
            "rule 5 deny ip source 192.168.10.50 0.0.0.0",
            "rule 10 permit ip source any",
            "quit",
            "traffic classifier C_BLOQUEIO",
            "if-match acl 3000",
            "quit",
            "traffic behavior B_ACAO",
            "permit",
            "quit",
            "traffic policy P_FILTRO_INTERFACE",
            "classifier C_BLOQUEIO behavior B_ACAO",
            "quit",
            "interface GigabitEthernet0/0/1",
            "traffic-policy P_FILTRO_INTERFACE inbound",
            "quit",
        )

    def test_chain_precedes_the_interface_application(self):
        """A cadeia é criada **antes** da aplicação na interface."""
        lines = render_form("acl", _values()).lines
        assert lines.index("traffic policy P_FILTRO_INTERFACE") < lines.index(
            "interface GigabitEthernet0/0/1"
        )
        assert lines.index("acl number 3000") < lines.index(
            "traffic classifier C_BLOQUEIO"
        )

    def test_behavior_deny_is_rendered(self):
        """Behavior 'deny' bloqueia tudo que casar com a ACL."""
        names = dict(_CHAIN_NAMES, behavior_action="deny")
        lines = render_form("acl", _values(names=names)).lines
        assert "deny" in lines
        assert lines[lines.index("traffic behavior B_ACAO") + 1] == "deny"

    def test_named_acl_is_referenced_by_name(self):
        """ACL nomeada → ``if-match acl <nome>``."""
        values = _values()
        values["identificacao"] = {
            "acl_type": "avancada",
            "id_mode": "nome",
            "acl_number": "",
            "acl_name": "BLOCOIO",
        }
        lines = render_form("acl", values).lines
        assert "acl name BLOCOIO advance" in lines
        assert "if-match acl BLOCOIO" in lines

    def test_outbound_direction(self):
        values = _values(applications=[{
            "where": "traffic_policy",
            "interface": "GigabitEthernet0/0/1",
            "direction": "outbound",
            "vty_range": "",
        }])
        lines = render_form("acl", values).lines
        assert "traffic-policy P_FILTRO_INTERFACE outbound" in lines


class TestTrafficPolicyFailClosed:
    def test_missing_names_are_rejected(self):
        """Aplicação via traffic policy exige os três nomes."""
        with pytest.raises(SdnValidationError, match="classifier"):
            render_form("acl", _values(names={}))

    def test_partial_names_are_rejected(self):
        names = {"classifier_name": "C_BLOQUEIO"}
        with pytest.raises(SdnValidationError, match="behavior"):
            render_form("acl", _values(names=names))

    def test_names_without_application_are_rejected(self):
        """Nomes preenchidos sem aplicação → nada é aplicado."""
        values = _values(applications=[])
        with pytest.raises(SdnValidationError, match="traffic policy"):
            render_form("acl", values)

    def test_invalid_name_is_rejected(self):
        """Nome VRP começa por letra (1ABC é inválido)."""
        names = dict(_CHAIN_NAMES, classifier_name="1ABC")
        with pytest.raises(SdnValidationError):
            render_form("acl", _values(names=names))

    def test_name_with_space_is_rejected(self):
        names = dict(_CHAIN_NAMES, policy_name="P FILTRO")
        with pytest.raises(SdnValidationError):
            render_form("acl", _values(names=names))

    def test_underscore_spelling_is_accepted(self):
        """``traffic_policy`` (com '_') também é reconhecido."""
        values = _values(applications=[{
            "where": "traffic_policy",
            "interface": "GigabitEthernet0/0/1",
            "direction": "inbound",
            "vty_range": "",
        }])
        lines = render_form("acl", values).lines
        assert "traffic classifier C_BLOQUEIO" in lines
        assert "traffic-policy P_FILTRO_INTERFACE inbound" in lines

    def test_plain_interface_application_still_works(self):
        """O caminho 'interface' (traffic-filter) segue intacto."""
        values = _values(where="interface", names={})
        lines = render_form("acl", values).lines
        assert "traffic-filter inbound acl 3000" in lines
        assert not any(line.startswith("traffic classifier") for line in lines)


class TestTrafficPolicyRollback:
    def test_undo_removes_binding_and_chain(self):
        snapshot = "#\nacl number 2999\n"
        lines = rollback_lines(render_form("acl", _values()), snapshot)
        assert "interface GigabitEthernet0/0/1" in lines
        assert "undo traffic-policy P_FILTRO_INTERFACE inbound" in lines
        assert "undo traffic policy P_FILTRO_INTERFACE" in lines
        assert "undo traffic behavior B_ACAO" in lines
        assert "undo traffic classifier C_BLOQUEIO" in lines
        assert "undo acl number 3000" in lines

    def test_undo_order_is_inverse(self):
        """Interface primeiro; depois policy → behavior → classifier."""
        lines = rollback_lines(render_form("acl", _values()), "#\n")
        idx = {
            key: lines.index(line)
            for key, line in (
                ("iface", "interface GigabitEthernet0/0/1"),
                ("policy", "undo traffic policy P_FILTRO_INTERFACE"),
                ("behavior", "undo traffic behavior B_ACAO"),
                ("classifier", "undo traffic classifier C_BLOQUEIO"),
            )
        }
        assert idx["iface"] < idx["policy"] < idx["behavior"] < idx["classifier"]

    def test_pre_existing_objects_are_preserved(self):
        """Classifier/behavior/policy já no snapshot não são removidos."""
        snapshot = (
            "#\n"
            "traffic classifier C_BLOQUEIO\n"
            "traffic behavior B_ACAO\n"
            "traffic policy P_FILTRO_INTERFACE\n"
        )
        lines = rollback_lines(render_form("acl", _values()), snapshot)
        assert "undo traffic policy P_FILTRO_INTERFACE" not in lines
        assert "undo traffic behavior B_ACAO" not in lines
        assert "undo traffic classifier C_BLOQUEIO" not in lines
        # ... mas a aplicação na interface (criada agora) é desfeita.
        assert "undo traffic-policy P_FILTRO_INTERFACE inbound" in lines

    def test_pre_existing_acl_rules_are_preserved(self):
        """ACL já existente → só as regras novas são desfeitas."""
        snapshot = "#\nacl number 3000\n rule 10 permit ip source any\n"
        lines = rollback_lines(render_form("acl", _values()), snapshot)
        assert "undo rule 5" in lines
        assert "undo rule 10" not in lines
        assert "undo acl number 3000" not in lines


class TestTrafficPolicyAnchors:
    def test_anchors_are_found_in_running_config(self):
        rendered = render_form("acl", _values())
        running = (
            "#\n"
            "acl number 3000\n"
            " rule 5 deny ip source 192.168.10.50 0.0.0.0\n"
            " rule 10 permit ip source any\n"
            "traffic classifier C_BLOQUEIO\n"
            " if-match acl 3000\n"
            "traffic behavior B_ACAO\n"
            " permit\n"
            "traffic policy P_FILTRO_INTERFACE\n"
            " classifier C_BLOQUEIO behavior B_ACAO\n"
            "interface GigabitEthernet0/0/1\n"
            " traffic-policy P_FILTRO_INTERFACE inbound\n"
        )
        missing = check_anchors(running, rendered.anchors)
        assert missing == []


class TestTrafficPolicyPolicy:
    def test_all_block_lines_are_allowed(self):
        """Toda linha renderizada passa na allowlist declarada."""
        spec = get_form_spec("acl")
        lines = render_form("acl", _values()).lines
        import re
        allowed = [re.compile(p, re.IGNORECASE) for p in spec.allow_patterns]
        for line in lines:
            assert any(p.search(line) for p in allowed), line

    def test_interface_binding_requires_confirmation(self):
        """Aplicação da policy na interface exige confirmação explícita."""
        spec = get_form_spec("acl")
        import re
        confirm = [re.compile(p, re.IGNORECASE) for p in spec.confirm_patterns]
        line = "traffic-policy P_FILTRO_INTERFACE inbound"
        assert any(p.search(line) for p in confirm)

    def test_undo_lines_are_allowed(self):
        """As linhas de rollback também passam na allowlist."""
        spec = get_form_spec("acl")
        import re
        allowed = [re.compile(p, re.IGNORECASE) for p in spec.allow_patterns]
        undo = rollback_lines(render_form("acl", _values()), "#\n")
        for line in undo:
            assert any(p.search(line) for p in allowed), line


class TestTrafficPolicyFormClarity:
    """A UI pede **só os nomes** — o resto da cadeia é derivado.

    Classificador e policy só precisam do nome; o behavior precisa do nome
    **e** da ação. Todo o resto (``if-match acl``, ``classifier ... behavior
    ...`` e o ``traffic-policy ... inbound``) é gerado automaticamente.
    """

    def test_section_hint_explains_what_is_derived(self):
        section = get_form_spec("acl").section("traffic_policy")
        assert section is not None
        assert "nomes" in section.hint.lower()
        assert "if-match" in section.hint
        assert "gerados automaticamente" in section.hint

    def test_name_fields_are_labelled_as_names_only(self):
        spec = get_form_spec("acl")
        for key in ("classifier_name", "behavior_name", "policy_name"):
            field = spec.field(key)
            assert field is not None, key
            assert "nome" in field.label.lower(), key

    def test_behavior_action_is_the_only_non_name_field(self):
        section = get_form_spec("acl").section("traffic_policy")
        assert section is not None
        kinds = {f.key: f.kind for f in section.fields}
        assert kinds["classifier_name"] is ParamKind.VRP_NAME
        assert kinds["behavior_name"] is ParamKind.VRP_NAME
        assert kinds["policy_name"] is ParamKind.VRP_NAME
        assert kinds["behavior_action"] is ParamKind.ENUM

    def test_name_fields_accept_bare_names(self):
        """O campo aceita só o nome — sem o comando na frente."""
        rendered = render_form(
            "acl",
            _values(names={**_CHAIN_NAMES, "policy_name": "P_FILTRO_INTERFACE"}),
        )
        assert "traffic policy P_FILTRO_INTERFACE" in rendered.lines
