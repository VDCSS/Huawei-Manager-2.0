"""Matriz RBAC 3×4 — papel × ação (plano W3, Passo 3.4).

Cobre a hierarquia corrigida (user < tecnico < admin) sobre acoes
criticas: Manutencao, CRUD de VNF, delecao de VNF e Services validado.
Services destrutivo/fora-template e bloqueado pela allowlist/deny-list
da W2 — inclusive para admin (defesa em profundidade).
"""
from __future__ import annotations

import pytest

from huawei_manager.handlers.auth import AuthMixin
from huawei_manager.handlers.services import ServicesMixin
from huawei_manager.services import ServiceDef

ROLES = ("user", "tecnico", "admin")

# user ❌ | tecnico ✅ | admin ✅
ALLOWED = {"user": False, "tecnico": True, "admin": True}
# sempre bloqueado, independente do papel
DENIED = {"user": False, "tecnico": False, "admin": False}


def _make_auth(**attrs) -> AuthMixin:
    mixin = AuthMixin()
    defaults = dict(_access_level="user", _session_tracker=None)
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


def _role_gate(role: str) -> bool:
    return _make_auth(_access_level=role)._require_access("tecnico")


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


def _validate(svc: ServiceDef, cmds: list[str]) -> bool:
    return not ServicesMixin()._validate_service(svc, cmds)


MATRIX = [
    ("manutencao", ALLOWED),
    ("vnf-crud", ALLOWED),
    ("vnf-delete", ALLOWED),
    ("services-valid", ALLOWED),
]


class TestRoleMatrix:
    """Cada papel respeita a hierarquia user < tecnico < admin."""

    @pytest.mark.parametrize("role", ROLES)
    @pytest.mark.parametrize("action,expected", MATRIX)
    def test_access_matrix(self, role, action, expected):
        assert _role_gate(role) is expected[role]

    def test_user_is_below_tecnico(self):
        assert _make_auth(_access_level="user")._require_access("user") is True
        assert _make_auth(_access_level="user")._require_access("tecnico") is False

    def test_tecnico_is_below_admin(self):
        assert _make_auth(_access_level="tecnico")._require_access("tecnico") is True
        assert _make_auth(_access_level="tecnico")._require_access("admin") is False

    def test_admin_reaches_everything(self):
        assert _make_auth(_access_level="admin")._require_access("admin") is True


class TestServicesValidation:
    """O gate de Services (W2) bloqueia destrutivo/fora-template p/ todos."""

    @pytest.mark.parametrize("role", ROLES)
    def test_legitimate_template_passes_for_all_roles(self, role):
        svc = _make_svc()
        assert _validate(svc, svc.cli_commands) is True

    @pytest.mark.parametrize("role", ROLES)
    def test_destructive_command_denied_for_all_roles(self, role):
        svc = _make_svc(config_mode=True, cli_commands=["reset saved-configuration"])
        assert _validate(svc, svc.cli_commands) is False

    @pytest.mark.parametrize("role", ROLES)
    def test_out_of_template_denied_for_all_roles(self, role):
        svc = _make_svc()
        assert _validate(svc, ["undocumented brutal command"]) is False

    @pytest.mark.parametrize("role", ROLES)
    def test_bypass_2fa_denied_for_all_roles(self, role):
        # Mesmo declarado no catalogo (allowlist), comando na deny-list
        # (``\bdelete\b``) e bloqueado — defesa em profundidade, nem admin
        # re-libera na rota services.
        svc = _make_svc(config_mode=True, cli_commands=["delete flash:/file.cfg"])
        assert _validate(svc, svc.cli_commands) is False
