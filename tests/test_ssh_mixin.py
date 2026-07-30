"""Testes de caracterização — SshMixin (handlers/ssh.py).

Testa _get_selected_vnf (puro) e caracterização dos caminhos de erro em _do_connect.
"""
from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

from _factories import make_vnf as _make_vnf
from huawei_manager.handlers.ssh import SshMixin


def _make_mixin(**attrs) -> SshMixin:
    mixin = SshMixin()
    defaults = dict(
        _topo_canvas=MagicMock(),
        _target_vnf=None,
        _sb=MagicMock(),
        _session_tracker=MagicMock(),
        _set_status=MagicMock(),
        _set_conn_btn=MagicMock(),
        _event_queue=MagicMock(),
        _dispatch=MagicMock(side_effect=lambda fn: fn() if callable(fn) else None),
        _spawn_io=MagicMock(),
        session=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    return mixin


class TestGetSelectedVnf:
    """_get_selected_vnf retorna VNF do canvas ou do target."""

    def test_returns_canvas_selection_if_exists(self):
        vnf = _make_vnf()
        canvas = MagicMock()
        canvas.get_selected.return_value = vnf
        mixin = _make_mixin(_topo_canvas=canvas, _target_vnf=None)
        assert mixin._get_selected_vnf() is vnf

    def test_returns_target_when_canvas_none(self):
        vnf = _make_vnf()
        mixin = _make_mixin(_topo_canvas=None, _target_vnf=vnf)
        assert mixin._get_selected_vnf() is vnf

    def test_returns_none_when_nothing_selected(self):
        canvas = MagicMock()
        canvas.get_selected.return_value = None
        mixin = _make_mixin(_topo_canvas=canvas, _target_vnf=None)
        assert mixin._get_selected_vnf() is None

    def test_returns_canvas_selection_over_target(self):
        canvas_vnf = _make_vnf(name="CanvasVNF")
        target_vnf = _make_vnf(name="TargetVNF")
        canvas = MagicMock()
        canvas.get_selected.return_value = canvas_vnf
        mixin = _make_mixin(_topo_canvas=canvas, _target_vnf=target_vnf)
        assert mixin._get_selected_vnf() is canvas_vnf


class TestDoConnect:
    """_do_connect error handling characterization."""

    def test_spawns_io(self):
        mixin = _make_mixin()
        mixin._do_connect("OK {sid}", "Erro")
        mixin._spawn_io.assert_called_once()

    def test_touches_session_tracker(self):
        mixin = _make_mixin()
        mixin._do_connect("OK {sid}", "Erro")
        mixin._session_tracker.touch.assert_called_once()

    def test_auth_error_sets_status(self):
        from netmiko.exceptions import NetmikoAuthenticationException
        mixin = _make_mixin()
        mixin._sb.connect.side_effect = NetmikoAuthenticationException("auth fail")

        def _capture_spawn_io(fn):
            fn()

        mixin._spawn_io = _capture_spawn_io
        mixin._do_connect("OK {sid}", "Erro")
        mixin._set_status.assert_called_with("Falha de autenticacao", ANY)

    def test_timeout_error_sets_status(self):
        from netmiko.exceptions import NetmikoTimeoutException
        mixin = _make_mixin()
        mixin._sb.connect.side_effect = NetmikoTimeoutException("timeout")

        def _capture_spawn_io(fn):
            fn()

        mixin._spawn_io = _capture_spawn_io
        mixin._do_connect("OK {sid}", "Erro")
        mixin._set_status.assert_called_with("Timeout de conexao", ANY)

    def test_value_error_sets_config_status(self):
        mixin = _make_mixin()
        mixin._sb.connect.side_effect = ValueError("bad config")

        def _capture_spawn_io(fn):
            fn()

        mixin._spawn_io = _capture_spawn_io
        mixin._do_connect("OK {sid}", "Erro")
        mixin._set_status.assert_called_with("Config: bad config", ANY)

    def test_generic_error_sets_on_error_msg(self):
        mixin = _make_mixin()
        mixin._sb.connect.side_effect = RuntimeError("oops")

        def _capture_spawn_io(fn):
            fn()

        mixin._spawn_io = _capture_spawn_io
        mixin._do_connect("OK {sid}", "Erro")
        mixin._set_status.assert_called_with("Erro", ANY)


class TestToggleConnect:
    """_toggle_connect characterization."""

    def test_disconnects_when_alive(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = True
        mixin._toggle_connect()
        mixin._sb.disconnect.assert_called_once()

    def test_connects_default_when_no_vnf(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = False
        mixin._get_selected_vnf = MagicMock(return_value=None)
        with patch.object(mixin, "_connect_default") as mock_def:
            mixin._toggle_connect()
        mock_def.assert_called_once()

    def test_connects_with_vnf_when_selected(self):
        vnf = _make_vnf()
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = False
        mixin._get_selected_vnf = MagicMock(return_value=vnf)
        with patch.object(mixin, "_connect_with_vnf") as mock_vnf:
            mixin._toggle_connect()
        mock_vnf.assert_called_once_with(vnf)
