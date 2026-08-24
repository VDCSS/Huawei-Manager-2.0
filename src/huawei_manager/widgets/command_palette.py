#!/usr/bin/env python3
"""
Command Palette (Ctrl+K) — paleta de comandos acessível de qualquer tela.

Itens navegáveis ↑↓, Enter executa, Esc fecha.
Inclui: navegar páginas, executar comandos rápidos, alternar tema,
logout, copiar IP, abrir docs.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.widgets.helpers import _css_font


@dataclass(frozen=True)
class Command:
    """Representa um comando na paleta."""
    id: str
    label: str
    description: str
    category: str
    shortcut: str | None
    action: Callable[[], None]
    enabled: bool = True


class CommandPalette(QFrame):
    """
    Overlay modal com busca fuzzy e lista de comandos.
    """

    def __init__(self, parent: QWidget, commands: list[Command]) -> None:
        super().__init__(parent)
        self.setObjectName("CommandPalette")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Armazena comandos
        self._all_commands = commands
        self._filtered_commands = commands[:]
        self._selected_index = 0

        # UI
        self._build_ui()
        self._install_shortcuts()

        # Escondido por padrão
        self.hide()

    def _build_ui(self) -> None:
        # Container principal com sombra/opacidade
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Card central
        self._card = QFrame(self)
        self._card.setObjectName("CommandPaletteCard")
        self._card.setFixedWidth(560)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Search input
        self._search = QLineEdit(self._card)
        self._search.setObjectName("CommandPaletteSearch")
        self._search.setPlaceholderText("Digite para filtrar comandos… (Ctrl+K para fechar)")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_search_changed)
        self._search.installEventFilter(self)
        card_layout.addWidget(self._search)

        # Separador
        sep = QFrame(self._card)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {C.BORDER_NRM}; border: none;")
        card_layout.addWidget(sep)

        # Lista de resultados
        self._list = QListWidget(self._card)
        self._list.setObjectName("CommandPaletteList")
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setUniformItemSizes(True)
        self._list.itemActivated.connect(self._on_item_activated)
        self._list.installEventFilter(self)
        card_layout.addWidget(self._list)

        outer_layout.addWidget(self._card, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # Estilo do card
        self._card.setStyleSheet(f"""
            #CommandPaletteCard {{
                background: {C.BG_CARD};
                border: 1px solid {C.BORDER_NRM};
                border-radius: 8px;
            }}
            #CommandPaletteSearch {{
                background: {C.BG_INPUT};
                color: {C.FG_MAIN};
                border: none;
                border-radius: 6px;
                padding: 10px 14px;
                font: {_css_font(C.FONT_UI_MEDIUM)};
                selection-background-color: {C.NEON_CYAN};
                selection-color: {C.BG_BASE};
            }}
            #CommandPaletteSearch:focus {{
                border: 2px solid {C.NEON_CYAN};
            }}
            #CommandPaletteList {{
                background: {C.BG_CARD};
                color: {C.FG_MAIN};
                border: none;
                outline: none;
                font: {_css_font(C.FONT_UI_MEDIUM)};
            }}
            #CommandPaletteList::item {{
                padding: 10px 14px;
                border-bottom: 1px solid {C.BORDER_NRM};
            }}
            #CommandPaletteList::item:selected {{
                background: {C.NEON_CYAN};
                color: {C.BG_BASE};
            }}
            #CommandPaletteList::item:last {{
                border-bottom: none;
            }}
        """)

        # Efeito de sombra sutil via opacity
        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(0.98)
        self._card.setGraphicsEffect(opacity)

    def _install_shortcuts(self) -> None:
        # Esc fecha
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self.hide)
        # Ctrl+K fecha (toggle)
        ctrl_k = QShortcut(QKeySequence("Ctrl+K"), self)
        ctrl_k.activated.connect(self.hide)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._search:
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                    self._list.setFocus()
                    return self._list.eventFilter(self._list, event)
                elif key == Qt.Key.Key_Escape:
                    self.hide()
                    return True
        elif watched is self._list:
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Escape:
                    self._search.setFocus()
                    self._search.selectAll()
                    return True
        return super().eventFilter(watched, event)

    def _on_search_changed(self, text: str) -> None:
        """Filtra comandos conforme o texto digitado (case-insensitive, substring)."""
        text = text.strip().lower()
        if not text:
            self._filtered_commands = [c for c in self._all_commands if c.enabled]
        else:
            self._filtered_commands = [
                c for c in self._all_commands
                if c.enabled and (
                    text in c.label.lower()
                    or text in c.description.lower()
                    or text in c.category.lower()
                    or (c.shortcut and text in c.shortcut.lower())
                )
            ]
        self._refresh_list()
        if self._filtered_commands:
            self._selected_index = 0
            self._list.setCurrentRow(0)

    def _refresh_list(self) -> None:
        self._list.clear()
        for cmd in self._filtered_commands:
            item = QListWidgetItem()
            # Usa widget customizado para mostrar label + description + shortcut
            item_widget = self._make_item_widget(cmd)
            item.setSizeHint(item_widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, item_widget)

    def _make_item_widget(self, cmd: Command) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        # Linha principal: label + shortcut
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(cmd.label)
        lbl.setStyleSheet(f"color: {C.FG_MAIN}; font: {_css_font(C.FONT_UI_MEDIUM)};")
        top_layout.addWidget(lbl)

        if cmd.shortcut:
            shortcut_lbl = QLabel(cmd.shortcut)
            shortcut_lbl.setStyleSheet(
                f"color: {C.FG_DIM}; font: {C.FONT_CAPTION}px '{C._FONT_UI_FAMILY}'; "
                f"background: {C.BG_INPUT}; padding: 2px 6px; border-radius: 3px;"
            )
            top_layout.addWidget(shortcut_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # Description
        if cmd.description:
            desc = QLabel(cmd.description)
            desc.setStyleSheet(f"color: {C.FG_DIM}; font: {C.FONT_CAPTION}px '{C._FONT_UI_FAMILY}';")
            layout.addWidget(desc)

        # Category badge
        cat = QLabel(cmd.category)
        cat.setStyleSheet(
            f"color: {C.NEON_CYAN}; font: {C.FONT_CAPTION}px '{C._FONT_UI_FAMILY}'; "
            f"background: {C.BG_INPUT}; padding: 1px 6px; border-radius: 3px;"
        )
        cat.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(cat, alignment=Qt.AlignmentFlag.AlignRight)

        return widget

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        idx = self._list.row(item)
        if 0 <= idx < len(self._filtered_commands):
            cmd = self._filtered_commands[idx]
            self.hide()
            cmd.action()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Centraliza na tela do parent
        parent = self.parentWidget()
        if parent:
            geo = parent.geometry()
            self.setGeometry(geo)
            # Posiciona o card no topo centralizado com margem
            self._card.move(
                (geo.width() - self._card.width()) // 2,
                40
            )
        self._search.clear()
        self._search.setFocus()
        self._filtered_commands = [c for c in self._all_commands if c.enabled]
        self._refresh_list()
        if self._filtered_commands:
            self._list.setCurrentRow(0)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        # Se o foco está na lista, Escape volta para a busca (não fecha)
        if self._list.hasFocus() and key == Qt.Key.Key_Escape:
            self._search.setFocus()
            self._search.selectAll()
            return
        # Se o foco está na busca, Enter executa, Escape fecha
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self._list.currentRow()
            if 0 <= idx < len(self._filtered_commands):
                cmd = self._filtered_commands[idx]
                self.hide()
                cmd.action()
        elif key == Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
        elif key == Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < len(self._filtered_commands) - 1:
                self._list.setCurrentRow(row + 1)
        elif key == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


def create_default_commands(app) -> list[Command]:
    """
    Cria a lista padrão de comandos para a aplicação.
    Recebe a instância do app (HuaweiRouterApp) para chamar métodos.
    """
    cmds: list[Command] = []

    # --- Navegação de páginas ---
    page_map = {
        "home": ("Dashboard", "Visão geral do sistema", "Ctrl+1"),
        "topology": ("Topologia / Devices", "Visualizar e gerenciar dispositivos", "Ctrl+2"),
        "config": ("Config Atual", "Exibir configuração atual do roteador", "Ctrl+3"),
        "route": ("Routing", "Tabela de roteamento", "Ctrl+4"),
        "arp": ("ARP Table", "Tabela ARP", "Ctrl+5"),
        "info": ("Info", "Informações do sistema", "Ctrl+6"),
        "cmd": ("Editor de Comandos", "Executar comandos personalizados", "Ctrl+7"),
        "backup": ("Backup", "Gerenciar backups de configuração", "Ctrl+8"),
        "services": ("Serviços", "Gerenciar serviços do roteador", "Ctrl+9"),
        "manutencao": ("Manutenção", "Ferramentas de manutenção", "Ctrl+0"),
    }

    for key, (label, desc, shortcut) in page_map.items():
        cmds.append(Command(
            id=f"nav:{key}",
            label=label,
            description=desc,
            category="Navegação",
            shortcut=shortcut,
            action=lambda k=key: app._show_page(k),
        ))

    # --- Comandos rápidos ---
    cmds.extend([
        Command(
            id="toggle_theme",
            label="Alternar Tema",
            description="Alterna entre tema claro e escuro",
            category="Aparência",
            shortcut="Ctrl+T",
            action=app._toggle_theme,
        ),
        Command(
            id="toggle_connection",
            label="Conectar / Desconectar",
            description="Alterna conexão com o roteador",
            category="Conexão",
            shortcut="Ctrl+D",
            action=app._toggle_connect,
        ),
        Command(
            id="clear_output",
            label="Limpar Saída",
            description="Limpa o output da página atual",
            category="Ações",
            shortcut="Ctrl+L",
            action=app._on_ctrl_l,
        ),
        Command(
            id="refresh_current",
            label="Atualizar Página Atual",
            description="Recarrega dados da página atual (F5)",
            category="Ações",
            shortcut="F5",
            action=app._on_f5,
        ),
    ])

    # --- Sessão / Auth ---
    cmds.extend([
        Command(
            id="logout",
            label="Logout / Trocar Usuário",
            description="Encerra sessão atual e abre diálogo de autenticação",
            category="Sessão",
            shortcut="Ctrl+Shift+A",
            action=app._show_auth_dialog,
        ),
        Command(
            id="copy_ip",
            label="Copiar IP do Roteador",
            description="Copia o IP configurado para a área de transferência",
            category="Sessão",
            shortcut=None,
            action=lambda: _copy_router_ip(app),
            enabled=_has_router_ip(app),
        ),
    ])

    # --- Ajuda ---
    cmds.append(Command(
        id="open_docs",
        label="Abrir Documentação",
        description="Abre a documentação online no navegador",
        category="Ajuda",
        shortcut=None,
        action=_open_docs,
    ))

    return cmds


def _copy_router_ip(app) -> None:
    """Copia o IP do roteador para o clipboard."""
    ip = getattr(app, "_router_ip", None) or getattr(app, "_secrets", {}).get("host")
    if ip:
        QApplication.clipboard().setText(ip)
        app._notify("IP copiado", f"{ip} copiado para a área de transferência", "success")


def _has_router_ip(app) -> bool:
    router_ip = getattr(app, "_router_ip", None)
    if isinstance(router_ip, str) and router_ip:
        return True
    secrets = getattr(app, "_secrets", None)
    if isinstance(secrets, dict):
        host = secrets.get("host")
        if isinstance(host, str) and host:
            return True
    return False


def _open_docs() -> None:
    """Abre a documentação no navegador padrão."""
    import webbrowser
    webbrowser.open("https://github.com/victordcss/Huawei-Manager/wiki")
