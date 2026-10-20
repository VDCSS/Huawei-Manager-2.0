"""Testes de caracterização — AppCore / HuaweiRouterApp (app.py).

Testa composição (herança), navegação e tema sem instanciar QMainWindow.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_app() -> MagicMock:
    """Cria mock de AppCore com atributos essenciais preenchidos."""
    from huawei_manager.app import AppCore
    app = MagicMock(spec=AppCore)
    app._theme = "dark"
    app._theme_toggling = False
    app._current_page = "home"
    app._active_btn = None
    app.pages = {}
    app._page_builders = {"home": MagicMock(), "cmd": MagicMock()}
    app._page_container = MagicMock()
    app._nav_buttons = {"home": MagicMock()}
    app.theme_btn = MagicMock()
    return app


class TestAppCoreComposition:
    def test_huawei_router_app_inherits_app_core(self):
        from huawei_manager.app import AppCore, HuaweiRouterApp
        assert issubclass(HuaweiRouterApp, AppCore)

    def test_app_core_inherits_qmain_window(self):
        from huawei_manager.app import AppCore
        from PySide6.QtWidgets import QMainWindow
        assert issubclass(AppCore, QMainWindow)

    def test_app_core_inherits_threading_mixin(self):
        from huawei_manager.app import AppCore
        from huawei_manager.app_threading import ThreadingMixin
        assert issubclass(AppCore, ThreadingMixin)

    def test_huawei_router_app_inherits_page_builder(self):
        from huawei_manager.app import HuaweiRouterApp
        from huawei_manager.pages import PageBuilder
        assert issubclass(HuaweiRouterApp, PageBuilder)

    def test_huawei_router_app_inherits_event_handlers(self):
        from huawei_manager.app import HuaweiRouterApp
        from huawei_manager.handlers import EventHandlers
        assert issubclass(HuaweiRouterApp, EventHandlers)


class TestShowPage:
    def test_sets_current_page(self):
        app = _make_app()
        from huawei_manager.app import AppCore
        AppCore._show_page(app, "cmd")
        assert app._current_page == "cmd"

    def test_builds_if_not_cached(self):
        app = _make_app()
        from huawei_manager.app import AppCore
        AppCore._show_page(app, "cmd")
        app._page_builders["cmd"].assert_called_once()

    def test_skips_build_if_cached(self):
        app = _make_app()
        app.pages["cmd"] = MagicMock()
        from huawei_manager.app import AppCore
        AppCore._show_page(app, "cmd")
        app._page_builders["cmd"].assert_not_called()

    def test_activate_nav_button(self):
        app = _make_app()
        from huawei_manager.app import AppCore
        AppCore._show_page(app, "home")
        app._nav_buttons["home"]._activate.assert_called_once()


class TestRebuildPage:
    def test_removes_old_and_shows_new(self):
        app = _make_app()
        old_page = MagicMock()
        app.pages["home"] = old_page
        app._current_page = "home"
        from huawei_manager.app import AppCore
        AppCore._rebuild_page(app, "home")
        app._page_container.removeWidget.assert_called_once_with(old_page)
        old_page.deleteLater.assert_called_once()

    def test_noop_if_key_not_in_pages(self):
        app = _make_app()
        from huawei_manager.app import AppCore
        with patch.object(AppCore, "_show_page") as mock_show:
            AppCore._rebuild_page(app, "nonexistent")
            mock_show.assert_not_called()


class TestTheme:
    def test_toggle_changes_theme(self):
        app = _make_app()
        app._rebuild_ui = MagicMock()
        from huawei_manager.app import AppCore
        with patch("huawei_manager.app.set_theme"), \
             patch("huawei_manager.app.apply_theme"):
            AppCore._toggle_theme(app)
        assert app._theme == "light"

    def test_toggle_blocks_if_toggling(self):
        app = _make_app()
        app._theme_toggling = True
        from huawei_manager.app import AppCore
        AppCore._toggle_theme(app)
        assert app._theme == "dark"

    def test_unlock_clears_flag(self):
        app = _make_app()
        app._theme_toggling = True
        from huawei_manager.app import AppCore
        AppCore._unlock_theme(app)
        assert app._theme_toggling is False
        app.theme_btn.setEnabled.assert_called_once_with(True)


class TestBootRegression:
    """Regressão: o app real precisa construir sem exceção (offscreen).

    Bug de 20/10/2026: ``start_alert_listeners(self._event_queue)`` ficou
    em ``_init_common_attrs()``, executado no ``__init__`` ANTES da linha
    que cria o ``EventQueue`` — ``AttributeError`` e a aplicação não abria.
    Reproduz aqui o mesmo caminho do ``main()`` sem ``app.exec()``.
    """

    def test_full_boot_wires_listeners_after_event_queue(self):
        import huawei_manager._config as cfg

        # Outros testes podem deixar o estado de _config resetado
        # (tests/test_config.py zera _INITIALIZED/_secrets/audit).
        if cfg._secrets is None or cfg.audit is None:
            cfg._INITIALIZED = False
            cfg.init()

        from huawei_manager._app import apply_theme, get_app
        qapp = get_app()
        apply_theme("dark")

        from huawei_manager.app import HuaweiRouterApp
        window = HuaweiRouterApp()
        try:
            assert window._event_queue is not None
            # Opt-in por ambiente: fora de teste não há listener ativo,
            # mas o atributo precisa existir (o _on_close depende dele).
            assert window._alert_listeners == []
        finally:
            window.close()
            qapp.processEvents()
