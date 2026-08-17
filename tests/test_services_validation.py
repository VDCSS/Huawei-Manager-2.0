"""Testes — validação de serviços (ServicesMixin._validate_service).

Cobre a allowlist derivada do template (description/cli_commands) e a
deny-list destrutiva antes da execução no dispositivo.
"""
from __future__ import annotations

import re

from huawei_manager.handlers.services import (
    ServicesMixin,
    _build_service_allow_patterns,
    _template_to_pattern,
)
from huawei_manager.services_data import ServiceDef


def _make_svc(**overrides) -> ServiceDef:
    defaults = dict(
        id="svc-001",
        name="Test Service",
        description="test command <param1>",
        category="test",
        device_types=["ROUTER"],
        cli_commands=["test command <param1>"],
        config_mode=False,
    )
    defaults.update(overrides)
    return ServiceDef(**defaults)


def _match(pattern: re.Pattern[str], cmd: str) -> bool:
    return bool(pattern.search(cmd))


class TestTemplateToPattern:
    def test_placeholder_accepts_multiword_value(self):
        pat = _template_to_pattern("test command <param1>")
        assert _match(pat, "test command hello")
        assert _match(pat, "test command hello world")

    def test_placeholder_requires_value(self):
        pat = _template_to_pattern("test command <param1>")
        assert not _match(pat, "test command")

    def test_literal_is_escaped(self):
        pat = _template_to_pattern("display version")
        assert _match(pat, "display version")
        assert not _match(pat, "display version is real")
        assert not _match(pat, "displayx version")

    def test_alternation_split(self):
        pats = _build_service_allow_patterns(
            _make_svc(description="shutdown | undo shutdown",
                      cli_commands=["shutdown", "undo shutdown"])
        )
        assert any(_match(p, "shutdown") for p in pats)
        assert any(_match(p, "undo shutdown") for p in pats)


class TestValidateService:
    def _mixin(self) -> ServicesMixin:
        return ServicesMixin()

    def test_command_from_template_is_allowed(self):
        mixin = self._mixin()
        svc = _make_svc()
        assert mixin._validate_service(svc, ["test command hello"]) == []

    def test_command_outside_template_is_rejected(self):
        mixin = self._mixin()
        svc = _make_svc()
        rejected = mixin._validate_service(svc, ["show run hidden"])
        assert len(rejected) == 1
        assert rejected[0][0] == "show run hidden"
        assert "fora do template" in rejected[0][1]

    def test_destructive_command_is_rejected(self):
        mixin = self._mixin()
        svc = _make_svc(config_mode=True,
                        cli_commands=["reset saved-configuration"])
        rejected = mixin._validate_service(svc, ["reset saved-configuration"])
        assert len(rejected) == 1
        assert "destrutivo" in rejected[0][1]

    def test_delete_word_is_rejected(self):
        mixin = self._mixin()
        svc = _make_svc(config_mode=True)
        rejected = mixin._validate_service(svc, ["test command delete flash"])
        assert len(rejected) == 1
        assert "destrutivo" in rejected[0][1]

    def test_alternation_allows_any_branch(self):
        mixin = self._mixin()
        svc = _make_svc(description="shutdown | undo shutdown",
                        cli_commands=["shutdown", "undo shutdown"])
        assert mixin._validate_service(svc, ["shutdown"]) == []
        assert mixin._validate_service(svc, ["undo shutdown"]) == []

    def test_empty_command_list_returns_empty(self):
        mixin = self._mixin()
        svc = _make_svc()
        assert mixin._validate_service(svc, []) == []
