"""Regressões do catálogo de serviços (params, allowlist e substituição).

Cobre bugs comprovados: defaults vazios quando o placeholder está colado ao
literal, placeholders repetidos colapsando no dict de UI, máscara perdida,
`|` tratado como alternância quebrando comandos com filtro de CLI e
substituição por label em vez do texto real do placeholder.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock

from huawei_manager.tabs.services.handlers import (
    ServicesHandlers,
    _build_service_allow_patterns,
)
from huawei_manager.services import get_service_by_id, parse_params
from huawei_manager.services_data import SERVICE_REGISTRY, ServiceDef


def _validate(svc: ServiceDef, cmds: list[str]) -> list[tuple[str, str]]:
    """validate_service não toca ctx/state — handler mínimo."""
    return ServicesHandlers(MagicMock(), MagicMock()).validate_service(
        svc, cmds)


def _params(sid: str) -> list[tuple[str, str]]:
    svc = get_service_by_id(sid)
    assert svc is not None
    return parse_params(svc)


class TestParseParamsDefaults:
    def test_interface_placeholder_glued_to_literal(self) -> None:
        """`interface GigabitEthernet0/0/0` não pode gerar default vazio."""
        assert _params("router-config-interface") == [("interface-number", "0/0/0")]

    def test_bgp_network_captures_mask(self) -> None:
        assert _params("router-config-bgp-network") == [
            ("network", "10.0.0.0"),
            ("mask", "255.255.255.0"),
        ]

    def test_acl_rule_action_is_parameterized(self) -> None:
        assert [p[0] for p in _params("router-config-acl-rule")] == [
            "id", "permit/deny", "ip", "wildcard",
        ]

    def test_nat_server_labels_are_unique(self) -> None:
        labels = [p[0] for p in _params("router-config-nat-server")]
        assert len(set(labels)) == len(labels) == 4

    def test_no_config_service_has_blank_default(self) -> None:
        blanks = [
            (svc.id, label)
            for svc in SERVICE_REGISTRY
            if svc.config_mode
            for label, default in parse_params(svc)
            if not default
        ]
        assert blanks == []

    def test_config_service_labels_never_repeat(self) -> None:
        """Labels repetidos colapsam no dict `_svc_param_entries` da UI."""
        repeated = [
            svc.id
            for svc in SERVICE_REGISTRY
            if svc.config_mode
            for labels in [[p[0] for p in parse_params(svc)]]
            if len(set(labels)) != len(labels)
        ]
        assert repeated == []


class TestAllowlistCoversOwnCommands:
    def test_every_service_allows_its_own_commands(self) -> None:
        """Nenhum serviço pode ser bloqueado pela própria allowlist."""
        bad = [
            (svc.id, cmd)
            for svc in SERVICE_REGISTRY
            for cmd in svc.cli_commands
            if not any(p.search(cmd) for p in _build_service_allow_patterns(svc))
        ]
        assert bad == []

    def test_pipe_filter_command_is_allowed(self) -> None:
        """`|` de filtro de CLI não é alternância (ex.: `| include sysname`)."""
        cmd = "display current-configuration | include sysname"
        svc = ServiceDef(
            id="t-pipe", name="Pipe", description=cmd,
            category="system", device_types=["ROUTER"], cli_commands=[cmd],
        )
        assert _validate(svc, [cmd]) == []

    def test_alternation_still_supported(self) -> None:
        svc = ServiceDef(
            id="t-alt", name="Alt", description="shutdown | undo shutdown",
            category="config-interface", device_types=["ROUTER"],
            cli_commands=["shutdown", "undo shutdown"],
        )
        assert _validate(svc, ["shutdown"]) == []
        assert _validate(svc, ["undo shutdown"]) == []


def _apply_placeholders(svc: ServiceDef, values: list[str]) -> str:
    """Reproduz a substituição posicional feita por run_service."""
    cmd = svc.description
    for placeholder, value in zip(re.findall(r"<[^>]+>", cmd), values):
        cmd = cmd.replace(placeholder, value, 1)
    return cmd


class TestParamSubstitution:
    def test_pipe_placeholder_uses_real_placeholder_text(self) -> None:
        """`<permit|deny>` tem label `permit/deny` na UI — deve ser trocado."""
        svc = get_service_by_id("router-config-acl-rule")
        assert svc is not None
        cmd = _apply_placeholders(svc, ["10", "deny", "192.168.0.0", "0.0.255.255"])
        assert cmd == "rule 10 deny ip source 192.168.0.0 0.0.255.255"
        assert _validate(svc, [cmd]) == []

    def test_repeated_placeholder_gets_distinct_values(self) -> None:
        svc = get_service_by_id("router-config-nat-server")
        assert svc is not None
        cmd = _apply_placeholders(
            svc, ["203.0.113.9", "8080", "192.168.1.10", "443"])
        assert cmd == (
            "nat server protocol tcp global 203.0.113.9 8080 "
            "inside 192.168.1.10 443"
        )
        assert _validate(svc, [cmd]) == []

    def test_vlan_port_type_placeholder_substituted(self) -> None:
        svc = get_service_by_id("router-config-vlan-port-type")
        assert svc is not None
        cmd = _apply_placeholders(svc, ["access"])
        assert cmd == "port link-type access"
        assert _validate(svc, [cmd]) == []
