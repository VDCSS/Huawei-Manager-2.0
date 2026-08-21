"""Testes de caracterização — SshMixin (handlers/ssh.py).

Testa _get_selected_device (puro) e caracterização dos caminhos de erro em _do_connect.
"""
from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

from ._factories import make_device as _make_device
from huawei_manager.handlers.ssh import SshMixin


def _make_mixin(**attrs) -> SshMixin:
    mixin = SshMixin()
    defaults = dict(
        _topo_canvas=MagicMock(),
        _target_device=None,
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


class TestGetSelectedDevice:
    """_get_selected_device retorna Device do canvas ou do target."""

    def test_returns_canvas_selection_if_exists(self):
        device = _make_device()
        canvas = MagicMock()
        canvas.get_selected.return_value = device
        mixin = _make_mixin(_topo_canvas=canvas, _target_device=None)
        assert mixin._get_selected_device() is device

    def test_returns_target_when_canvas_none(self):
        device = _make_device()
        mixin = _make_mixin(_topo_canvas=None, _target_device=device)
        assert mixin._get_selected_device() is device

    def test_returns_none_when_nothing_selected(self):
        canvas = MagicMock()
        canvas.get_selected.return_value = None
        mixin = _make_mixin(_topo_canvas=canvas, _target_device=None)
        assert mixin._get_selected_device() is None

    def test_returns_canvas_selection_over_target(self):
        canvas_device = _make_device(name="CanvasDevice")
        target_device = _make_device(name="TargetDevice")
        canvas = MagicMock()
        canvas.get_selected.return_value = canvas_device
        mixin = _make_mixin(_topo_canvas=canvas, _target_device=target_device)
        assert mixin._get_selected_device() is canvas_device


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

    def test_sdn_validation_error_sets_config_status(self):
        from huawei_manager.exceptions import SdnValidationError
        mixin = _make_mixin()
        mixin._sb.connect.side_effect = SdnValidationError("Credenciais incompletas")

        def _capture_spawn_io(fn):
            fn()

        mixin._spawn_io = _capture_spawn_io
        mixin._do_connect("OK {sid}", "Erro")
        mixin._set_status.assert_called_with("Config: Credenciais incompletas", ANY)

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

    def test_connects_default_when_no_device(self):
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = False
        mixin._get_selected_device = MagicMock(return_value=None)
        with patch.object(mixin, "_connect_default") as mock_def:
            mixin._toggle_connect()
        mock_def.assert_called_once()

    def test_connects_with_device_when_selected(self):
        device = _make_device()
        mixin = _make_mixin()
        mixin._sb.is_alive.return_value = False
        mixin._get_selected_device = MagicMock(return_value=device)
        with patch.object(mixin, "_connect_with_device") as mock_dev:
            mixin._toggle_connect()
        mock_dev.assert_called_once_with(device)
