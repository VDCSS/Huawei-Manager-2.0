"""Testes de caracterização — PageBuilderServicesMixin (pages/services.py).

Testa _on_service_select, _on_svc_cat_changed, _clear_detail_panel.
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock

from huawei_manager.pages.services import PageBuilderServicesMixin


def _make_svc(**overrides):
    svc = MagicMock()
    svc.name = overrides.get("name", "TestService")
    svc.description = overrides.get("description", "test cmd <p1>")
    svc.category = overrides.get("category", "config-bgp")
    svc.config_mode = overrides.get("config_mode", True)
    svc.device_types = overrides.get("device_types", ["ROUTER"])
    return svc


def _make_detail_frame():
    """Cria mock de _svc_detail_frame com layout vazio (count=0)."""
    frame = MagicMock()
    layout = MagicMock()
    layout.count.return_value = 0  # evita loop infinito em _clear_detail_panel
    layout.takeAt.return_value = None
    frame.layout.return_value = layout
    return frame, layout


def _make_mixin(**attrs) -> PageBuilderServicesMixin:
    mixin = PageBuilderServicesMixin()
    frame, layout = _make_detail_frame()
    defaults = dict(
        _svc_services=[],
        _svc_current_svc=None,
        _svc_detail_frame=frame,
        _svc_cat_var="Todas as Categorias",
        _svc_cat_cb=MagicMock(),
        _svc_listbox=MagicMock(),
        _svc_device_lbl=MagicMock(),
        _svc_type_lbl=MagicMock(),
        _svc_status_lbl=MagicMock(),
        _svc_param_entries={},
        _target_device=None,
        _access_level="user",
        _page_layout=lambda p: p.layout(),
        _write=MagicMock(),
    )
    for k, v in defaults.items():
        setattr(mixin, k, v)
    for k, v in attrs.items():
        setattr(mixin, k, v)
    # Bind _clear_detail_panel properly so unbound 'self' works
    mixin._clear_detail_panel = types.MethodType(
        PageBuilderServicesMixin._clear_detail_panel, mixin
    )
    return mixin


class TestClearDetailPanel:
    def test_clears_entries(self):
        mixin = _make_mixin()
        mixin._svc_param_entries = {"p1": MagicMock()}
        mixin._clear_detail_panel()
        assert len(mixin._svc_param_entries) == 0

    def test_clears_current_svc(self):
        mixin = _make_mixin(_svc_current_svc=_make_svc())
        mixin._clear_detail_panel()
        assert mixin._svc_current_svc is None


class TestOnServiceSelect:
    def test_sets_current_svc(self):
        svc = _make_svc()
        mixin = _make_mixin(_svc_services=[svc])
        mixin._show_service_detail = lambda s: None  # stub — detail rendering tested elsewhere
        mixin._on_service_select(0)
        assert mixin._svc_current_svc is svc

    def test_negative_row_clears(self):
        mixin = _make_mixin()
        mixin._on_service_select(-1)
        assert mixin._svc_current_svc is None

    def test_out_of_range_clears(self):
        mixin = _make_mixin(_svc_services=[_make_svc()])
        mixin._on_service_select(5)
        assert mixin._svc_current_svc is None


class TestOnSvcCatChanged:
    def test_updates_var(self):
        mixin = _make_mixin()
        mixin._on_svc_cat_changed("new_cat")
        assert mixin._svc_cat_var == "new_cat"
