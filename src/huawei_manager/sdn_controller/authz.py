"""RBAC Framework — roles, decorator e session timeout.

Fornece o decorador ``@require_role`` para proteger operacoes do
controlador SDN, o enum ``Role`` com hierarquia, e o ``SessionTracker``
para timeout de inatividade.
"""
from __future__ import annotations

import enum
import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from huawei_manager.exceptions import SdnAuthError, SdnValidationError

P = ParamSpec("P")
R = TypeVar("R")


_ROLE_HIERARCHY: dict[str, int] = {
    "user": 0,
    "tecnico": 1,
    "admin": 2,
}


class Role(enum.Enum):
    """Niveis de acesso do controlador SDN.

    A hierarquia e: ``USER < TECNICO < ADMIN``.
    """

    USER = "user"
    TECNICO = "tecnico"
    ADMIN = "admin"

    @property
    def hierarchy(self) -> int:
        """Retorna o nivel numerico para comparacao."""
        return _ROLE_HIERARCHY[self.value]

    @staticmethod
    def from_string(level: str) -> Role:
        """Converte string para Role. Levanta ``SdnValidationError`` se invalido."""
        try:
            return Role(level)
        except ValueError:
            valid = ", ".join(r.value for r in Role)
            raise SdnValidationError(
                f"Unknown role: {level!r}. Valid roles: {valid}"
            )


_ROLE_EQUIV: dict[Role, int] = {r: r.hierarchy for r in Role}


def role_meets(actual: str, required: str = "tecnico") -> bool:
    """True se ``actual`` tem hierarquia >= ``required`` (fonte unica).

    A hierarquia e definida em ``Role.hierarchy`` (``authz.py``); nenhum
    call site deve duplicar a ordem dos papeis (evita divergencia).

    Args:
        actual: Nivel de acesso corrente (``"user"``/``"tecnico"``/``"admin"``).
        required: Nivel minimo exigido. Default ``"tecnico"``.

    Returns:
        True se ``actual`` atende ao requisito. Nivel desconhecido em
        ``actual`` cai para ``Role.USER`` (fail-closed); ``required``
        desconhecido tambem cai para ``Role.USER`` para nao quebrar call
        sites existentes — nenhum call site real passa nivel invalido.
    """
    try:
        cur = Role.from_string(actual)
    except SdnValidationError:
        cur = Role.USER
    try:
        req = Role.from_string(required)
    except SdnValidationError:
        req = Role.USER
    return cur.hierarchy >= req.hierarchy


def require_role(
    min_role: Role | str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorador que exige um nivel minimo de acesso.

    A funcao decorada deve aceitar um parametro ``role: str`` (passado
    como keyword argument). Se o nivel for insuficiente, levanta
    ``PermissionError``.

    Args:
        min_role: Nivel minimo exigido (``Role`` enum ou string).
    """
    min_enum = min_role if isinstance(min_role, Role) else Role.from_string(min_role)
    min_level = _ROLE_EQUIV[min_enum]

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            raw = kwargs.get("role", "user")
            assert isinstance(raw, str), f"role must be str, got {type(raw)}"
            role_str: str = raw
            caller_enum = Role.from_string(role_str)
            caller_level = _ROLE_EQUIV[caller_enum]
            if caller_level < min_level:
                raise SdnAuthError(
                    f"Role '{role_str}' insufficient for '{func.__name__}'; "
                    f"requires {min_enum.value}"
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator


class SessionTracker:
    """Gerencia a role corrente e timeout por inatividade.

    Args:
        timeout_secs: Segundos de inatividade antes de resetar para
            ``Role.USER``. ``0`` desabilita o timeout.
    """

    def __init__(self, timeout_secs: int | float = 300) -> None:
        self._timeout_secs = timeout_secs
        self._role: Role = Role.USER
        self._last_activity: float = time.time()

    @property
    def current_role(self) -> Role:
        """Retorna a role atual, respeitando timeout."""
        if self._timeout_secs > 0:
            elapsed = time.time() - self._last_activity
            if elapsed > self._timeout_secs and self._role is not Role.USER:
                self._role = Role.USER
        return self._role

    @property
    def last_activity(self) -> float:
        """Timestamp da ultima atividade."""
        return self._last_activity

    @property
    def is_active(self) -> bool:
        """True se a role atual nao e USER."""
        return self.current_role is not Role.USER

    def set_role(self, role: Role) -> None:
        """Define a role e registra atividade."""
        self._role = role
        self._last_activity = time.time()

    def touch(self) -> None:
        """Registra atividade sem alterar a role."""
        self._last_activity = time.time()
