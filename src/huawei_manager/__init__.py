# Huawei Manager

__version__ = "2.0.0"


def main():
    """Entry point: inicializa a GUI Tkinter do Huawei Manager."""
    import sys
    from pathlib import Path

    # agents/ e data/ ficam na raiz do projeto — precisam estar no sys.path
    _root = Path(__file__).resolve().parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    import tkinter as tk

    from huawei_manager.app import HuaweiRouterApp
    root = tk.Tk()
    HuaweiRouterApp(root)
    root.mainloop()

