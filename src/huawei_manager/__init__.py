# Huawei Manager

__version__ = "2.0.0"


def main():
    """Entry point: inicializa a GUI PySide6 do Huawei Manager."""
    from huawei_manager._config import init
    init()
    from huawei_manager._app import get_app
    from huawei_manager.app import HuaweiRouterApp

    app = get_app()
    # HuaweiRouterApp lê o tema salvo em QSettings e chama set_theme()/
    # apply_theme() no __init__, então não forçar "dark" aqui (isso causava
    # um flash de tema e mascarava a preferência persistida).
    window = HuaweiRouterApp()
    window.show()
    app.exec()
