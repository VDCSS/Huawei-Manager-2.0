"""Tests for RBAC framework — @require_role decorator and session timeout."""
from __future__ import annotations

import time

import pytest

from huawei_manager.exceptions import SdnAuthError, SdnValidationError
from huawei_manager.sdn_controller.authz import (
    Role,
    SessionTracker,
    require_role,
)
from tests.helpers import wait_until

# ── Test Role enum ───────────────────────────────────────────────────────────

class TestRoleEnum:
    """Role enum deve ter 3 niveis com hierarquia correta."""

    def test_values(self) -> None:
        assert Role.USER.value == "user"
        assert Role.ADMIN.value == "admin"
        assert Role.TECNICO.value == "tecnico"

    def test_hierarchy(self) -> None:
        """USER < TECNICO < ADMIN."""
        assert Role.USER.hierarchy < Role.TECNICO.hierarchy
        assert Role.TECNICO.hierarchy < Role.ADMIN.hierarchy

    def test_from_string(self) -> None:
        assert Role.from_string("user") is Role.USER
        assert Role.from_string("admin") is Role.ADMIN
        assert Role.from_string("tecnico") is Role.TECNICO

    def test_from_string_unknown(self) -> None:
        with pytest.raises(SdnValidationError, match="Unknown role: 'root'"):
            Role.from_string("root")


# ── Test require_role decorator ─────────────────────────────────────────────

class TestRequireRole:
    """@require_role deve bloquear operacoes baseado no nivel minimo."""

    def test_user_can_read(self) -> None:
        """USER pode executar operacoes de leitura."""
        @require_role(Role.USER)
        def read_device(role: str = "user") -> str:
            return "data"

        assert read_device(role="user") == "data"

    def test_user_cannot_configure(self) -> None:
        """USER nao pode executar config. Levanta PermissionError."""
        @require_role(Role.ADMIN)
        def configure_device(role: str = "user") -> str:
            return "configured"

        with pytest.raises(SdnAuthError, match="requires admin"):
            configure_device(role="user")

    def test_admin_can_configure(self) -> None:
        """ADMIN pode executar config normalmente."""
        @require_role(Role.ADMIN)
        def configure_device(role: str = "user") -> str:
            return "configured"

        assert configure_device(role="admin") == "configured"

    def test_admin_can_destroy(self) -> None:
        """ADMIN pode executar operacoes destrutivas."""
        @require_role(Role.TECNICO)
        def destroy_device(role: str = "user") -> str:
            return "destroyed"

        assert destroy_device(role="admin") == "destroyed"

    def test_tecnico_can_destroy(self) -> None:
        """TECNICO pode executar operacoes destrutivas."""
        @require_role(Role.TECNICO)
        def destroy_device(role: str = "user") -> str:
            return "destroyed"

        assert destroy_device(role="tecnico") == "destroyed"

    def test_user_cannot_destroy(self) -> None:
        """USER nao pode executar operacoes destrutivas."""
        @require_role(Role.TECNICO)
        def destroy_device(role: str = "user") -> str:
            return "destroyed"

        with pytest.raises(SdnAuthError, match="requires tecnico"):
            destroy_device(role="user")

    def test_tecnico_cannot_configure_some_operations(self) -> None:
        """TECNICO nao pode executar operacoes exclusivas de ADMIN."""
        @require_role(Role.ADMIN)
        def delete_device(role: str = "user") -> str:
            return "deleted"

        with pytest.raises(SdnAuthError, match="requires admin"):
            delete_device(role="tecnico")

    def test_default_role_user(self) -> None:
        """Sem argumento role, padrao e USER."""
        @require_role(Role.USER)
        def read_device(role: str = "user") -> str:
            return "data"

        assert read_device() == "data"

    def test_unknown_role_raises(self) -> None:
        """Role invalida no parametro levanta ValueError."""
        @require_role(Role.USER)
        def read_device(role: str = "user") -> str:
            return "data"

        with pytest.raises(SdnValidationError, match="Unknown role: 'hacker'"):
            read_device(role="hacker")

    def test_preserves_function_metadata(self) -> None:
        """Decorator preserva __name__ e __doc__."""
        @require_role(Role.USER)
        def my_func(role: str = "user") -> str:
            """My docstring."""
            return "ok"

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."

    def test_role_as_string(self) -> None:
        """@require_role aceita string em vez de Role enum."""
        @require_role("admin")
        def configure(role: str = "user") -> str:
            return "configured"

        assert configure(role="admin") == "configured"
        with pytest.raises(SdnAuthError):
            configure(role="user")


# ── Test SessionTracker ─────────────────────────────────────────────────────

class TestSessionTracker:
    """SessionTracker gerencia role corrente e timeout por inatividade."""

    def test_default_role_is_user(self) -> None:
        st = SessionTracker(timeout_secs=300)
        assert st.current_role is Role.USER

    def test_set_role(self) -> None:
        st = SessionTracker(timeout_secs=300)
        st.set_role(Role.ADMIN)
        assert st.current_role is Role.ADMIN

    def test_touch_updates_last_activity(self) -> None:
        st = SessionTracker(timeout_secs=300)
        before = st.last_activity
        time.sleep(0.01)
        st.touch()
        assert st.last_activity > before

    def test_timeout_resets_to_user(self) -> None:
        """Apos timeout de inatividade, role volta para USER."""
        st = SessionTracker(timeout_secs=0.05)  # 50ms timeout
        st.set_role(Role.ADMIN)
        assert st.current_role is Role.ADMIN
        wait_until(lambda: st.current_role is Role.USER, timeout=1.0)

    def test_touch_prevents_timeout(self) -> None:
        """Tocar dentro do timeout impede reset."""
        st = SessionTracker(timeout_secs=0.1)
        st.set_role(Role.ADMIN)
        time.sleep(0.05)
        st.touch()  # renova
        time.sleep(0.08)
        assert st.current_role is Role.ADMIN  # ainda dentro

    def test_timeout_after_inactivity(self) -> None:
        """Nao tocar por mais que timeout reseta para USER."""
        st = SessionTracker(timeout_secs=0.05)
        st.set_role(Role.TECNICO)
        wait_until(lambda: st.current_role is Role.USER, timeout=2.0)

    def test_set_role_touches(self) -> None:
        """set_role() faz touch automatico."""
        st = SessionTracker(timeout_secs=0.05)
        st.set_role(Role.ADMIN)
        time.sleep(0.03)
        st.set_role(Role.ADMIN)  # touch renova
        time.sleep(0.03)
        assert st.current_role is Role.ADMIN  # ainda dentro

    def test_is_active(self) -> None:
        st = SessionTracker(timeout_secs=300)
        assert not st.is_active
        st.set_role(Role.ADMIN)
        assert st.is_active

    def test_is_active_after_timeout(self) -> None:
        st = SessionTracker(timeout_secs=0.05)
        st.set_role(Role.ADMIN)
        wait_until(lambda: not st.is_active, timeout=2.0)

    def test_timeout_zero_disabled(self) -> None:
        """timeout_secs=0 significa sem timeout."""
        st = SessionTracker(timeout_secs=0)
        st.set_role(Role.ADMIN)
        time.sleep(0.1)
        assert st.current_role is Role.ADMIN  # nunca expira

    def test_no_touch_required_for_legacy(self) -> None:
        """Integracao: tracker pode ser usado sem touch manual."""
        st = SessionTracker(timeout_secs=0.05)
        st.set_role(Role.ADMIN)
        # Nao chama touch — timeout deve ocorrer
        wait_until(lambda: st.current_role is Role.USER, timeout=2.0)
