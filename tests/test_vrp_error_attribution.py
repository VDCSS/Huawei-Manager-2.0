"""Atribuição dos erros da VRP ao comando que os originou.

Sem atribuição, o operador recebe N mensagens idênticas
("Error: Unrecognized command found at '^' position.") e não sabe o que
corrigir. A VRP ecoa o comando recusado depois do prompt — a atribuição
aproveita esse eco.
"""
from __future__ import annotations

from huawei_manager.sdn_controller.vrp_errors import (
    attribute_vrp_errors,
    describe_vrp_failure,
    format_vrp_errors,
    hint_for_command,
)

#: Saída real do NE40E (EVE-NG) ao recusar a cadeia traffic policy.
VRP_OUTPUT = """system-view
Enter system view, return user view with return command.
[~NE40E]acl number 3000
[*NE40E-acl4-advance-3000]rule 5 deny ip source 192.168.10.50 0.0.0.0
[*NE40E-acl4-advance-3000]quit
[~NE40E]traffic classifier C_BLOQUEIO
        ^
Error: Unrecognized command found at '^' position.
[~NE40E]if-match acl 3000
        ^
Error: Unrecognized command found at '^' position.
[~NE40E]quit
[~NE40E]traffic behavior B_ACAO
        ^
Error: Unrecognized command found at '^' position.
[~NE40E]permit
        ^
Error: Unrecognized command found at '^' position.
[~NE40E]traffic policy P_FILTRO_INTERFACE
        ^
Error: Unrecognized command found at '^' position.
[~NE40E]classifier C_BLOQUEIO behavior B_ACAO
        ^
Error: Unrecognized command found at '^' position.
"""

COMMANDS = [
    "acl number 3000",
    "rule 5 deny ip source 192.168.10.50 0.0.0.0",
    "quit",
    "traffic classifier C_BLOQUEIO",
    "if-match acl 3000",
    "quit",
    "traffic behavior B_ACAO",
    "permit",
    "quit",
    "traffic policy P_FILTRO_INTERFACE",
    "classifier C_BLOQUEIO behavior B_ACAO",
]


class TestAttribution:
    def test_each_error_is_attributed_to_its_command(self):
        errors = attribute_vrp_errors(VRP_OUTPUT, COMMANDS)
        commands = [e.command for e in errors]
        assert "traffic classifier C_BLOQUEIO" in commands
        assert "if-match acl 3000" in commands
        assert "traffic behavior B_ACAO" in commands
        assert "traffic policy P_FILTRO_INTERFACE" in commands
        assert "classifier C_BLOQUEIO behavior B_ACAO" in commands
        # Nenhum erro fica sem comando.
        assert all(e.command for e in errors)

    def test_accepted_commands_have_no_error(self):
        errors = attribute_vrp_errors(VRP_OUTPUT, COMMANDS)
        assert "acl number 3000" not in [e.command for e in errors]

    def test_error_message_is_kept(self):
        errors = attribute_vrp_errors(VRP_OUTPUT, COMMANDS)
        assert all(
            "Unrecognized command" in e.message for e in errors
        )


class TestFormatting:
    def test_message_names_the_rejected_command(self):
        msg = describe_vrp_failure(VRP_OUTPUT, COMMANDS)
        assert msg.startswith("Configuração recusada pela VRP:")
        assert "`traffic classifier C_BLOQUEIO`" in msg
        assert "Unrecognized command" in msg

    def test_message_contains_the_feature_hint(self):
        msg = describe_vrp_failure(VRP_OUTPUT, COMMANDS)
        assert "QoS" in msg
        assert "dica" in msg

    def test_hint_only_for_known_features(self):
        assert hint_for_command("traffic-policy P inbound")
        assert hint_for_command("traffic classifier C")
        assert hint_for_command("traffic-filter inbound acl 3000")
        assert hint_for_command("acl number 3000") == ""
        assert hint_for_command("") == ""

    def test_empty_errors(self):
        assert format_vrp_errors([]) == "Configuração recusada pela VRP."

    def test_fallback_without_echo(self):
        """Sem eco reconhecível, o erro é preservado (sem comando)."""
        raw = "Error: Unrecognized command found at '^' position."
        msg = describe_vrp_failure(raw, ["acl number 3000"])
        assert "Unrecognized command" in msg
        assert msg.startswith("Configuração recusada pela VRP:")
