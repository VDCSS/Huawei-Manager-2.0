"""Testes do registry de abas — Fase 0 (fundação TabModule).

Cobre: build_registry (ordem da sidebar, keys únicas, min_role, fail-fast
sem builder), tab_by_key, visible_tabs (RBAC via authz.role_meets +
fail-closed de papel desconhecido), LegacyTabAdapter e CommandRegistry
(da palette — registro vivo por aba).
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from huawei_manager.tabs import build_registry, tab_by_key, visible_tabs
from huawei_manager.tabs._contract import LegacyTabAdapter
from huawei_manager.widgets.command_palette import Command, CommandRegistry

_EXPECTED_KEYS = [
    "home", "topology", "config", "route", "arp",
    "info", "cmd", "backup", "services", "manutencao",
]
_EXPECTED_GROUPS = [
    "DASHBOARD",
    "DISPOSITIVOS", "DISPOSITIVOS", "DISPOSITIVOS", "DISPOSITIVOS", "DISPOSITIVOS",
    "FERRAMENTAS", "FERRAMENTAS", "FERRAMENTAS",
    "ADMINISTRACAO",
]


def _host() -> MagicMock:
    """Host falso: MagicMock devolve builder callable para qualquer atributo."""
    return MagicMock()


class TestBuildRegistry:
    def test_has_ten_tabs_in_sidebar_order(self) -> None:
        tabs = build_registry(_host())
        assert [td.key for td in tabs] == _EXPECTED_KEYS

    def test_keys_are_unique(self) -> None:
        keys = [td.key for td in build_registry(_host())]
        assert len(set(keys)) == len(keys) == 10

    def test_min_role_valid(self) -> None:
        for td in build_registry(_host()):
            assert td.min_role in ("user", "tecnico", "admin")

    def test_groups_follow_sidebar_order(self) -> None:
        tabs = build_registry(_host())
        assert [td.group for td in tabs] == _EXPECTED_GROUPS

    def test_labels_and_shortcuts_present(self) -> None:
        for td in build_registry(_host()):
            assert td.label, f"{td.key} sem label"
            assert td.description, f"{td.key} sem description na palette"

    def test_missing_builder_fails_fast(self) -> None:
        # topology é a única aba ainda sem module_factory — sem o builder
        # legado no host, o registry falha fechado (F2-services completou
        # a migração de services).
        host = MagicMock(spec=[])  # nenhum builder
        with pytest.raises(RuntimeError, match="builder legado"):
            build_registry(host)


class TestTabByKey:
    def test_finds_existing(self) -> None:
        tabs = build_registry(_host())
        td = tab_by_key(tabs, "cmd")
        assert td is not None
        assert td.label == "Editor de Comandos"

    def test_returns_none_for_unknown(self) -> None:
        assert tab_by_key(build_registry(_host()), "nope") is None


class TestVisibleTabs:
    def test_all_visible_when_everyone_can(self) -> None:
        tabs = build_registry(_host())
        assert len(visible_tabs(tabs, "user")) == 10
        assert len(visible_tabs(tabs, "admin")) == 10

    def test_admin_only_hidden_for_user(self) -> None:
        restricted = [replace(td, min_role="admin") for td in build_registry(_host())]
        assert visible_tabs(restricted, "user") == []
        assert len(visible_tabs(restricted, "admin")) == 10

    def test_unknown_role_fails_closed_to_user(self) -> None:
        restricted = [replace(td, min_role="admin") for td in build_registry(_host())]
        # Papel desconhecido cai em "user" (mínimo) — nada admin visível.
        assert visible_tabs(restricted, "root") == []


class TestLegacyTabAdapter:
    def test_build_calls_builder_and_returns_none(self) -> None:
        builder = MagicMock()
        adapter = LegacyTabAdapter(builder)
        assert adapter.build(MagicMock()) is None
        builder.assert_called_once()

    def test_dispose_is_noop(self) -> None:
        assert LegacyTabAdapter(MagicMock()).dispose() is None


def _cmd(cmd_id: str) -> Command:
    return Command(id=cmd_id, label=cmd_id, description="", category="t",
                   shortcut=None, action=lambda: None)


class TestCommandRegistry:
    def test_register_mutates_live_list(self) -> None:
        live: list[Command] = []
        reg = CommandRegistry(live)
        reg.register(_cmd("a"))
        assert [c.id for c in live] == ["a"]

    def test_register_same_id_replaces(self) -> None:
        live: list[Command] = []
        reg = CommandRegistry(live)
        reg.register(_cmd("a"))
        reg.register(_cmd("a"))
        assert [c.id for c in live] == ["a"]

    def test_unregister_is_idempotent(self) -> None:
        live = [_cmd("a"), _cmd("b")]
        reg = CommandRegistry(live)
        reg.unregister("a")
        reg.unregister("a")
        assert [c.id for c in live] == ["b"]

    def test_commands_returns_copy(self) -> None:
        reg = CommandRegistry([_cmd("a")])
        out = reg.commands()
        out.clear()
        assert len(reg.commands()) == 1
