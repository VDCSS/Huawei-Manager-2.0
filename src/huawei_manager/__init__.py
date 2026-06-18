# Huawei Manager

__version__ = "2.0.0"


def main():
    import tkinter as tk

    from huawei_manager.app import HuaweiRouterApp
    root = tk.Tk()
    HuaweiRouterApp(root)
    root.mainloop()

