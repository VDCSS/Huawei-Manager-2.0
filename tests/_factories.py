"""Shared test factories used across test modules."""
from unittest.mock import MagicMock


def make_vnf(**overrides):
    """Factory for creating VNF instances with sensible defaults."""
    from huawei_manager.vnf_models import VNF

    defaults = dict(
        id="vnf-001-test",
        name="test-device",
        host="10.0.0.1",
        port=22,
        type="ROUTER",
        username="admin",
        password="secret",
        ssh_key="",
        location="lab",
        status="unknown",
    )
    defaults.update(overrides)
    return VNF(**defaults)


def make_dispatch():
    """Standardized dispatch mock that executes the callable and tracks calls."""
    def _dispatch(fn):
        if callable(fn):
            return fn()
        return None
    return MagicMock(side_effect=_dispatch)
