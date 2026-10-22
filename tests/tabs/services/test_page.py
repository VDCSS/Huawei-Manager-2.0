"""Testes da aba Serviços — ServicesTab (tabs/services/page.py).

Migrados de tests/test_services_page.py (F2-services do plano
plano-abas-independentes). Testa _on_service_select, _on_svc_cat_changed,
_clear_detail_panel e o ciclo build/dispose do módulo TabModule.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from huawei_manager.tabs._contract import TabContext
from huawei_manager.tabs.services.page import ServicesTab


def _make_svc(**overrides):
    svc = MagicMock()
    svc.name = overrides.get("name", "TestService")
    svc.description = overrides.get("description", "test cmd <p1>")
    svc.category = overrides.get("category", "config-bgp")
    svc.config_mode = overrides.get("config_mode", True)
    svc.device_types = overrides.get("device_types", ["ROUTER"])
    return svc


def _make_detail_frame():
    """Cria mock de detail_frame com layout vazio (count=0)."""
    frame = MagicMock()
    layout = MagicMock()
    layout.count.return_value = 0  # evita loop infinito em _clear_detail_panel
    layout.takeAt.return_value = None
    frame.layout.return_value = layout
    return frame, layout


def _fake_ctx(**overrides) -> TabContext:
    """TabContext fake com todos os 29 campos; overrides por teste."""
    drv = overrides.pop("drv", MagicMock())
    fields: dict = dict(
        sb=MagicMock(),
        audit=None,
        event_bus=MagicMock(),
        role=lambda: "admin",
        device=lambda: None,
        dispatch=lambda fn: fn() if callable(fn) else None,
        require_access=lambda level: True,
        spawn_io=lambda fn, *a: fn(*a),
        spawn_cpu=lambda fn, *a: fn(*a),
        watcher=MagicMock(),
        is_mock=lambda: False,
        toggle_mock=lambda: False,
        show_auth_dialog=lambda: None,
        watcher_results=lambda: None,
        set_watcher_results=MagicMock(),
        session=MagicMock(),
        run=MagicMock(),
        set_status=MagicMock(),
        touch_session=MagicMock(),
        cmd_validator=None,
        dry_run=None,
        get_last_config_command=MagicMock(return_value=None),
        set_last_config_command=MagicMock(),
        drv=lambda: drv,
        devices=lambda: [],
        show_page=MagicMock(),
        svc_mode=lambda: "mock",
        ui_bridge=lambda: None,
        ensure_device_ready=MagicMock(return_value=None),
    )
    fields.update(overrides)
    return TabContext(**fields)


def _make_tab(**attrs) -> ServicesTab:
    """Tab com estado preenchido (widgets mock) e ctx anexado."""
    tab = ServicesTab()
    tab.attach(_fake_ctx())
    frame, _layout = _make_detail_frame()
    defaults = dict(
        services=[],
        current_svc=None,
        detail_frame=frame,
        cat_var="Todas as Categorias",
        cat_cb=MagicMock(),
        listbox=MagicMock(),
        device_lbl=MagicMock(),
        type_lbl=MagicMock(),
        status_lbl=MagicMock(),
        param_entries={},
        output=MagicMock(),
    )
    for k, v in attrs.items():
        defaults[k] = v
    for k, v in defaults.items():
        setattr(tab.state, k, v)
    return tab


class TestClearDetailPanel:
    def test_clears_entries(self):
        tab = _make_tab(param_entries={"p1": MagicMock()})
        tab._clear_detail_panel()
        assert len(tab.state.param_entries) == 0

    def test_clears_current_svc(self):
        tab = _make_tab(current_svc=_make_svc())
        tab._clear_detail_panel()
        assert tab.state.current_svc is None


class TestOnServiceSelect:
    def test_sets_current_svc(self):
        svc = _make_svc()
        tab = _make_tab(services=[svc])
        # stub — detail rendering (Qt real) tested no build abaixo
        tab._show_service_detail = lambda s: None  # type: ignore[method-assign]
        tab._on_service_select(0)
        assert tab.state.current_svc is svc

    def test_negative_row_clears(self):
        tab = _make_tab()
        tab._on_service_select(-1)
        assert tab.state.current_svc is None

    def test_out_of_range_clears(self):
        tab = _make_tab(services=[_make_svc()])
        tab._on_service_select(5)
        assert tab.state.current_svc is None


class TestOnSvcCatChanged:
    def test_updates_var(self):
        tab = _make_tab()
        tab._on_svc_cat_changed("new_cat")
        assert tab.state.cat_var == "new_cat"


class TestBuildDispose:
    def test_build_returns_services_page(self):
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        tab = ServicesTab()
        page = tab.build(_fake_ctx())
        assert page.objectName() == "page_services"
        assert tab.state.output is not None
        assert tab.state.listbox is not None
        assert app is not None  # QApplication mantido vivo durante o teste

    def test_dispose_zera_refs(self):
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        tab = ServicesTab()
        tab.build(_fake_ctx())
        tab.dispose()
        assert tab.state.output is None
        assert tab.state.listbox is None
        assert tab.state.detail_frame is None
        assert tab.state.cat_var == "Todas as Categorias"
        assert app is not None

    def test_out_widget_reflete_state(self):
        tab = _make_tab()
        assert tab.out_widget() is tab.state.output
