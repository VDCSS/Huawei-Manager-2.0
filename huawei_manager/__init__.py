# Huawei Manager — Netmiko + SDN + VNFs + Segurança

__version__ = "1.1.0"


def main():
    import tkinter as tk
    from huawei_manager.app import HuaweiRouterApp
    root = tk.Tk()
    HuaweiRouterApp(root)
    root.mainloop()

