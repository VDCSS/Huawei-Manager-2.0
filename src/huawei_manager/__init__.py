# Huawei Manager

__version__ = "2.0.0"


def main():
    """Entry point: inicializa a GUI PySide6 do Huawei Manager."""
    from huawei_manager._config import init
    init()
    from huawei_manager._app import apply_theme, get_app
    from huawei_manager.app import HuaweiRouterApp

    app = get_app()
    apply_theme("dark")
    window = HuaweiRouterApp()
    window.show()
    app.exec()
