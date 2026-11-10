"""Menu de contexto da topologia sob RBAC (plano W3, C.6.2 item 4).

Tecnico/admin veem as acoes Editar/Excluir e o handler libera
(D5 revertida); user nao ve menu e nenhum handler e acionado.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint

from huawei_manager.topology import TopologyCanvas
from huawei_manager.device_models import Device

pytestmark = pytest.mark.skipif(
    not os.environ.get("QT_QPA_PLATFORM"),
    reason="Requires Qt platform (e.g., offscreen)",
)


class _FakeMenu:
    """QMenu fake: registra acoes e devolve a escolhida em exec()."""

    def __init__(self) -> None:
        self._actions: list[object] = []
        self._exec_calls = 0
        self._return_index: int | None = None

    def setStyleSheet(self, *args, **kwargs) -> None:
        pass

    def addAction(self, text: str) -> object:
        action = object()
        self._actions.append(action)
        return action

    def exec(self, *args, **kwargs) -> object | None:
        self._exec_calls += 1
        if self._return_index is None:
            return None
        return self._actions[self._return_index]


def _make_device() -> Device:
    return Device(
        id="r1", name="R1", host="10.0.0.1", port=22,
        type="ROUTER", status="online", username="admin",
    )


def _context_event() -> MagicMock:
    ev = MagicMock()
    ev.globalPos.return_value = QPoint(0, 0)
    return ev


@pytest.fixture
def canvas(qtbot) -> TopologyCanvas:
    c = TopologyCanvas()
    qtbot.addWidget(c)
    c._access_level = "user"
    c._edit_cb = MagicMock()
    c._delete_cb = MagicMock()
    return c


class TestTopologyContextMenu:
    def test_user_nao_ve_menu(self, canvas, monkeypatch):
        fake = _FakeMenu()
        monkeypatch.setattr("huawei_manager.topology.QMenu", lambda parent=None: fake)

        canvas._access_level = "user"
        canvas._on_context_menu(_context_event(), _make_device())

        assert fake._exec_calls == 0
        canvas._edit_cb.assert_not_called()
        canvas._delete_cb.assert_not_called()

    @pytest.mark.parametrize("role", ["tecnico", "admin"])
    def test_role_ve_menu_editar_excluir(self, canvas, monkeypatch, role):
        fake = _FakeMenu()
        monkeypatch.setattr("huawei_manager.topology.QMenu", lambda parent=None: fake)

        canvas._access_level = role
        canvas._on_context_menu(_context_event(), _make_device())

        assert fake._exec_calls == 1
        assert len(fake._actions) == 2
        canvas._edit_cb.assert_not_called()
        canvas._delete_cb.assert_not_called()

    @pytest.mark.parametrize("role", ["tecnico", "admin"])
    def test_role_editar_libera_handler(self, canvas, monkeypatch, role):
        fake = _FakeMenu()
        monkeypatch.setattr("huawei_manager.topology.QMenu", lambda parent=None: fake)
        device = _make_device()

        canvas._access_level = role
        fake._return_index = 0
        canvas._on_context_menu(_context_event(), device)

        canvas._edit_cb.assert_called_once_with(device)
        canvas._delete_cb.assert_not_called()

    @pytest.mark.parametrize("role", ["tecnico", "admin"])
    def test_role_excluir_libera_handler(self, canvas, monkeypatch, role):
        fake = _FakeMenu()
        monkeypatch.setattr("huawei_manager.topology.QMenu", lambda parent=None: fake)
        device = _make_device()

        canvas._access_level = role
        fake._return_index = 1
        canvas._on_context_menu(_context_event(), device)

        canvas._delete_cb.assert_called_once_with(device)
        canvas._edit_cb.assert_not_called()