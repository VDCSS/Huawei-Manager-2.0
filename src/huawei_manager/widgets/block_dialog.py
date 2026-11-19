"""Modais da feature de bloqueio da aba Serviços.

Dois diálogos modais no padrão de :class:`DeviceDialog` (``QDialog``
modal, ``get_*()`` lança se não confirmado):

* :class:`BlockInternetDialog` — perfil padrão de bloqueio por device.
  Sem perfil → formulário de criação. Com perfil → 3 ações, com o
  primeiro botão **dinâmico**: ``Aplicar regra`` quando a regra ainda não
  está na interface, ``Desaplicar regra`` quando está.
* :class:`BlockSiteDialog` — Bloquear site em 4 etapas (estratégia →
  destinos → aplicação → revisão).

Nenhum dos diálogos fala com o device: eles apenas coletam/validam e
devolvem uma decisão; a execução fica nos handlers da aba.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import huawei_manager.constants as C
from huawei_manager.exceptions import SdnValidationError
from huawei_manager.services.acl_presets import (
    ACL_BLOCK_RANGE,
    AclBlockProfile,
    validate_profile,
)
from huawei_manager.services.block_cli import (
    parse_destination,
    preview_lines,
    preview_site_lines,
    resolve_destinations,
)

# ── Helpers de estilo (mesmo padrão de device_dialog.py) ───────────────


def _style_label(text: str, fixed_width: int = 130) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY}; "
        f"min-width: {fixed_width}px;"
    )
    lbl.setFixedWidth(fixed_width)
    return lbl


def _style_input(placeholder: str = "") -> QLineEdit:
    entry = QLineEdit()
    entry.setPlaceholderText(placeholder)
    entry.setStyleSheet(
        f"background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
        f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
        f"padding: 4px 8px; font: 12px {C.FONT_UI_FAMILY};"
    )
    return entry


def _style_combo() -> QComboBox:
    cb = QComboBox()
    cb.setStyleSheet(
        f"QComboBox {{ background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
        f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
        f"padding: 4px 8px; font: 12px {C.FONT_UI_FAMILY}; }}"
        f"QComboBox::drop-down {{ border: none; }}"
        f"QComboBox QAbstractItemView {{ background: {C.BG_INPUT}; "
        f"color: {C.NEON_CYAN}; "
        f"selection-background-color: {C.NEON_PURP}; }}"
    )
    return cb


def _mark_invalid(entry: QLineEdit) -> None:
    entry.setStyleSheet(
        f"background: {C.BG_INPUT}; color: {C.NEON_RED}; "
        f"border: 1px solid {C.NEON_RED}; border-radius: 3px; "
        f"padding: 4px 8px; font: 12px {C.FONT_UI_FAMILY};"
    )
    entry.setFocus()


def _clear_invalid(entry: QLineEdit) -> None:
    entry.setStyleSheet(
        f"background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
        f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
        f"padding: 4px 8px; font: 12px {C.FONT_UI_FAMILY};"
    )


def _button(text: str, color: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(
        f"background: transparent; color: {color}; border: 1px solid {color}; "
        f"border-radius: 3px; padding: 6px 14px; "
        f"font: 12px {C.FONT_UI_FAMILY};"
    )
    return btn


def _read_only_block(text: str, height: int = 160) -> QPlainTextEdit:
    box = QPlainTextEdit()
    box.setReadOnly(True)
    box.setMaximumHeight(height)
    box.setPlainText(text)
    box.setStyleSheet(
        f"background: {C.BG_BASE}; color: {C.FG_CODE}; "
        f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
        f"font-family: {C.FONT_LARGE[0]}; font-size: 11px;"
    )
    return box


def _param_grid(rows: list[tuple[str, str]]) -> QFrame:
    """Grade de rótulo/valor usada na tela de revisão."""
    frame = QFrame()
    frame.setStyleSheet(
        f"background: {C.BG_INPUT}; border: 1px solid {C.BORDER_NRM}; "
        "border-radius: 4px;"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(3)
    for label, value in rows:
        row = QWidget(frame)
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        key = QLabel(label, row)
        key.setStyleSheet(
            f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY}; "
            "min-width: 150px;"
        )
        key.setFixedWidth(150)
        val = QLabel(value or "—", row)
        val.setStyleSheet(
            f"color: {C.NEON_CYAN}; font: 11px {C.FONT_UI_FAMILY};"
        )
        val.setWordWrap(True)
        row_l.addWidget(key)
        row_l.addWidget(val, stretch=1)
        lay.addWidget(row)
    return frame


@dataclass(frozen=True)
class BlockInternetDecision:
    """Resultado confirmado do :class:`BlockInternetDialog`.

    Attributes:
        action: ``apply`` | ``unapply`` | ``delete``.
        profile: perfil validado (parâmetros da ACL padrão).
        save: persistir na startup-config (D3 — só se ``True``).
    """

    action: str
    profile: AclBlockProfile
    save: bool


class BlockInternetDialog(QDialog):
    """Modal "Bloquear Internet" — criação/gerência do perfil por device.

    Args:
        parent: widget pai.
        profile: perfil existente do device (``None`` = 1ª vez).
        applied: estado do binding **detectado** no device (ou cache).
        applied_source: ``"device"`` (consulta real) ou ``"cache"``
            (MOCK/offline) — exibido ao operador para não vender certeza.
        can_save: o papel atual permite salvar na startup-config (admin).
    """

    #: Páginas do QStackedWidget.
    _PAGE_FORM = 0
    _PAGE_MANAGE = 1
    _PAGE_REVIEW = 2

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        profile: AclBlockProfile | None = None,
        applied: bool = False,
        applied_source: str = "cache",
        can_save: bool = True,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._applied = applied
        self._applied_source = applied_source
        self._can_save = can_save
        self._decision: BlockInternetDecision | None = None
        self._action: str = "apply"
        self._entries: dict[str, QLineEdit] = {}
        self._direction_cb: QComboBox | None = None
        self._save_chk: QCheckBox | None = None
        self._cli_box: QPlainTextEdit | None = None
        self._summary_box: QFrame | None = None
        #: Chave do device na criação (perfil ainda não existe).
        self._device_key_override: str = ""
        #: Perfil validado em espera (preenchido antes da revisão).
        self._pending_profile: AclBlockProfile | None = None
        #: Widgets da página de revisão (criados em ``_build_review_page``).
        self._review_title: QLabel = QLabel()
        self._review_grid: QFrame = QFrame()

        self._build_ui()
        self.setModal(True)

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        creating = self._profile is None
        self.setWindowTitle(
            "Bloquear Internet — nova regra"
            if creating
            else "Bloquear Internet — regra existente"
        )
        self.setMinimumSize(560, 520)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setStyleSheet(f"background: {C.BG_CARD};")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_form_page())
        self._stack.addWidget(self._build_manage_page())
        self._stack.addWidget(self._build_review_page())

        self._stack.setCurrentIndex(
            self._PAGE_MANAGE if self._profile is not None else self._PAGE_FORM
        )

    def _build_form_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        intro = QLabel(
            "Informe os parâmetros da ACL padrão de bloqueio deste device. "
            "Ela será criada uma única vez e reutilizada nas próximas vezes."
        )
        intro.setStyleSheet(f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY};")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        fields: list[tuple[str, str, str]] = [
            ("acl_name", "Nome da ACL:", "bloqueio-padrão"),
            ("acl_number", "Número da ACL:", str(ACL_BLOCK_RANGE[0])),
            ("destination_ip", "IP de destino:", "203.0.113.10"),
            ("destination_mask", "Máscara destino:", "0.0.0.0"),
            ("interface", "Interface:", "GigabitEthernet0/0/0"),
        ]
        for key, label, default in fields:
            row = QWidget(page)
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.addWidget(_style_label(label))
            entry = _style_input(default)
            entry.setText(default)
            entry.textChanged.connect(lambda _t, e=entry: _clear_invalid(e))
            self._entries[key] = entry
            row_l.addWidget(entry, stretch=1)
            lay.addWidget(row)

        # Direção
        dir_row = QWidget(page)
        dir_l = QHBoxLayout(dir_row)
        dir_l.setContentsMargins(0, 0, 0, 0)
        dir_l.addWidget(_style_label("Direção:"))
        self._direction_cb = _style_combo()
        self._direction_cb.addItems(["outbound", "inbound"])
        dir_l.addWidget(self._direction_cb, stretch=1)
        lay.addWidget(dir_row)

        hint = QLabel(
            "IP de destino = host alvo do bloqueio (máscara 0.0.0.0 = "
            "host único). Direção outbound bloqueia a saída para a WAN."
        )
        hint.setStyleSheet(f"color: {C.FG_DIM}; font: 10px {C.FONT_UI_FAMILY};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addStretch()

        bar = QWidget(page)
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(0, 0, 0, 0)
        review_btn = _button("Revisar…", C.NEON_CYAN)
        review_btn.clicked.connect(self._on_review_from_form)
        bar_l.addWidget(review_btn)
        bar_l.addSpacing(8)
        cancel_btn = _button("Cancelar", C.NEON_PURP)
        cancel_btn.clicked.connect(self.reject)
        bar_l.addWidget(cancel_btn)
        bar_l.addStretch()
        lay.addWidget(bar)
        return page

    def _build_manage_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        title = QLabel("Regra de bloqueio já criada para este device")
        title.setStyleSheet(
            f"color: {C.NEON_AMBER}; font: 12px {C.FONT_UI_FAMILY}; bold;"
        )
        lay.addWidget(title)

        self._summary_box = _param_grid(self._summary_rows())
        lay.addWidget(self._summary_box)

        state = self._state_text()
        state_lbl = QLabel(state)
        color = C.NEON_CYAN if self._applied else C.FG_DIM
        state_lbl.setStyleSheet(
            f"color: {color}; font: 11px {C.FONT_UI_FAMILY};"
        )
        state_lbl.setWordWrap(True)
        lay.addWidget(state_lbl)

        if self._applied_source != "device":
            warn = QLabel(
                "aviso Estado estimado (modo MOCK/offline) — não foi possível "
                "consultar o device agora."
            )
            warn.setStyleSheet(
                f"color: {C.NEON_AMBER}; font: 10px {C.FONT_UI_FAMILY};"
            )
            warn.setWordWrap(True)
            lay.addWidget(warn)

        lay.addStretch()

        # ── 3 ações ────────────────────────────────────────────────
        bar = QWidget(page)
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(0, 0, 0, 0)

        # Dinâmico: aplicar ⇄ desaplicar conforme o binding na interface.
        if self._applied:
            toggle = _button("Desaplicar regra", C.NEON_AMBER)
            self._action = "unapply"
        else:
            toggle = _button("Aplicar regra", C.NEON_CYAN)
            self._action = "apply"
        toggle.clicked.connect(
            lambda: self._goto_review(self._action)
        )
        bar_l.addWidget(toggle)

        edit_btn = _button("Editar e salvar/enviar", C.NEON_CYAN)
        edit_btn.clicked.connect(
            lambda: self._stack.setCurrentIndex(self._PAGE_FORM)
        )
        bar_l.addWidget(edit_btn)

        del_btn = _button("Apagar regra", C.NEON_RED)
        del_btn.clicked.connect(lambda: self._goto_review("delete"))
        bar_l.addWidget(del_btn)

        bar_l.addStretch()
        lay.addWidget(bar)

        cancel_btn = _button("Cancelar", C.NEON_PURP)
        cancel_btn.clicked.connect(self.reject)
        lay.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._review_title = QLabel("Revisão")
        self._review_title.setStyleSheet(
            f"color: {C.NEON_AMBER}; font: 12px {C.FONT_UI_FAMILY}; bold;"
        )
        lay.addWidget(self._review_title)

        header = QLabel("Parâmetros selecionados")
        header.setStyleSheet(
            f"color: {C.FG_DIM}; font: 10px {C.FONT_UI_FAMILY}; bold;"
        )
        lay.addWidget(header)
        self._review_grid = _param_grid([])
        lay.addWidget(self._review_grid)

        cli_header = QLabel("BLOCO QUE SERÁ ENVIADO AO DEVICE")
        cli_header.setStyleSheet(
            f"color: {C.FG_DIM}; font: 10px {C.FONT_UI_FAMILY}; bold;"
        )
        lay.addWidget(cli_header)
        self._cli_box = _read_only_block("", height=170)
        lay.addWidget(self._cli_box)

        self._save_chk = QCheckBox(
            "Salvar na startup-config (persistir após reboot)", page
        )
        self._save_chk.setChecked(False)
        self._save_chk.setEnabled(self._can_save)
        self._save_chk.setStyleSheet(
            f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY};"
        )
        if not self._can_save:
            self._save_chk.setToolTip(
                "Exige papel admin para persistir no device."
            )
        lay.addWidget(self._save_chk)

        bar = QWidget(page)
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(0, 0, 0, 0)
        back_btn = _button("← Voltar", C.NEON_PURP)
        back_btn.clicked.connect(self._go_back_from_review)
        bar_l.addWidget(back_btn)
        bar_l.addSpacing(8)
        send_btn = _button("Salvar/Enviar", C.NEON_CYAN)
        send_btn.clicked.connect(self._on_confirm)
        bar_l.addWidget(send_btn)
        bar_l.addStretch()
        lay.addWidget(bar)
        return page

    # ── Dados / ações ───────────────────────────────────────────────
    def _summary_rows(self) -> list[tuple[str, str]]:
        p = self._profile
        if p is None:
            return []
        return [
            ("Nome da ACL", p.acl_name),
            ("Número da ACL", str(p.acl_number)),
            ("IP de destino", p.destination_ip),
            ("Máscara destino", p.destination_mask),
            ("Interface", p.interface),
            ("Direção", p.direction),
        ]

    def _state_text(self) -> str:
        if self._applied:
            return (
                "Estado: APLICADA na interface — o botão oferece "
                "'Desaplicar regra' (a ACL permanece no device)."
            )
        return (
            "Estado: criada, mas AINDA NÃO aplicada na interface — o botão "
            "oferece 'Aplicar regra'."
        )

    def _validate_form(self) -> AclBlockProfile | None:
        """Valida campo a campo, pintando de vermelho o que falhar."""
        bad = False
        for key, entry in self._entries.items():
            if key == "acl_number":
                try:
                    num = int(entry.text().strip() or "0")
                    low, high = ACL_BLOCK_RANGE
                    if not low <= num <= high:
                        raise ValueError
                except ValueError:
                    _mark_invalid(entry)
                    bad = True
                    continue
            if not entry.text().strip():
                _mark_invalid(entry)
                bad = True
        if bad:
            return None

        device_key = (
            self._profile.device_key
            if self._profile is not None
            else self._device_key_override or ""
        )
        if not device_key:
            return None
        direction = (
            self._direction_cb.currentText()
            if self._direction_cb is not None
            else "outbound"
        )
        raw = AclBlockProfile(
            device_key=device_key,
            acl_name=self._entries["acl_name"].text().strip(),
            acl_number=int(self._entries["acl_number"].text().strip()),
            destination_ip=self._entries["destination_ip"].text().strip(),
            destination_mask=self._entries["destination_mask"].text().strip(),
            interface=self._entries["interface"].text().strip(),
            direction=direction,
            created_from_snapshot=(
                self._profile.created_from_snapshot
                if self._profile is not None
                else False
            ),
            applied=self._applied,
        )
        try:
            return validate_profile(raw)
        except SdnValidationError as exc:
            msg = str(exc)
            # Pinta o campo culpado quando dá para identificar.
            for entry in self._entries.values():
                if entry.text().strip() and entry.text().strip() in msg:
                    _mark_invalid(entry)
                    break
            self._show_error(msg)
            return None

    def _show_error(self, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self, "Bloquear Internet", message)

    def _on_review_from_form(self) -> None:
        profile = self._validate_form()
        if profile is None:
            return
        self._pending_profile = profile
        self._goto_review("apply")

    def _goto_review(self, action: str) -> None:
        profile = self._pending_profile
        if profile is None:
            profile = self._profile
        if profile is None:
            return
        self._action = action
        self._pending_profile = profile

        labels = {
            "apply": "Aplicar regra (criar/alterar ACL e fixar na interface)",
            "unapply": "Desaplicar regra (remover só o binding — ACL fica)",
            "delete": "Apagar regra (remover binding e, se nossa, a ACL)",
        }
        self._review_title.setText(f"Revisão — {labels[action]}")

        # Reconstroi a grade de parâmetros.
        old = self._review_grid
        rows = self._summary_rows_for(profile, action)
        new_grid = _param_grid(rows)
        self._layout_replace(old, new_grid)
        self._review_grid = new_grid

        try:
            lines = preview_lines(profile, action)
        except SdnValidationError as exc:
            self._show_error(str(exc))
            return
        if self._cli_box is not None:
            self._cli_box.setPlainText("\n".join(lines))

        if self._save_chk is not None:
            self._save_chk.setChecked(False)

        self._stack.setCurrentIndex(self._PAGE_REVIEW)

    def _summary_rows_for(
        self, profile: AclBlockProfile, action: str
    ) -> list[tuple[str, str]]:
        rows = [
            ("Ação", action),
            ("Nome da ACL", profile.acl_name),
            ("Número da ACL", str(profile.acl_number)),
            ("IP de destino", profile.destination_ip),
            ("Máscara destino", profile.destination_mask),
            ("Interface", profile.interface),
            ("Direção", profile.direction),
            (
                "ACL pré-existente no device",
                "sim (será preservada)"
                if profile.created_from_snapshot
                else "não (será removida no apagar)",
            ),
        ]
        return rows

    def _layout_replace(self, old: QWidget, new: QWidget) -> None:
        """Troca um widget por outro mantendo a posição no layout."""
        parent_widget = old.parentWidget()
        if parent_widget is None:
            return
        parent_layout = parent_widget.layout()
        if not isinstance(parent_layout, QVBoxLayout):
            return
        index = parent_layout.indexOf(old)
        if index < 0:
            return
        parent_layout.removeWidget(old)
        old.deleteLater()
        parent_layout.insertWidget(index, new)

    def _go_back_from_review(self) -> None:
        target = (
            self._PAGE_MANAGE
            if self._profile is not None
            else self._PAGE_FORM
        )
        self._stack.setCurrentIndex(target)

    def _on_confirm(self) -> None:
        profile = self._pending_profile or self._profile
        if profile is None:
            return
        save = bool(self._save_chk.isChecked()) if self._save_chk else False
        self._decision = BlockInternetDecision(
            action=self._action, profile=profile, save=save
        )
        self.accept()

    def set_device_key(self, key: str) -> None:
        """Define a chave do device na criação (antes de exec())."""
        self._device_key_override = key

    def get_decision(self) -> BlockInternetDecision:
        """Decisão confirmada.

        Raises:
            RuntimeError: chamado antes de ``exec()`` ou com diálogo
                rejeitado.
        """
        if self.result() != QDialog.DialogCode.Accepted:
            raise RuntimeError(
                "get_decision() chamado antes de exec() ou diálogo rejeitado."
            )
        if self._decision is None:
            raise RuntimeError("decisão ausente após aceitação.")
        return self._decision


@dataclass(frozen=True)
class BlockSiteDecision:
    """Resultado confirmado do :class:`BlockSiteDialog`.

    Attributes:
        strategy: ``deny-list`` ou ``all-except``.
        acl_number: número da ACL (3000–3999).
        interface / direction: binding do traffic-filter.
        destinations: destinos como digitados pelo operador.
        resolved: pares ``(ip, wildcard)`` já resolvidos (DNS dos
            domínios aplicado) — o handler não precisa de rede.
        save: persistir na startup-config (D3 — só se ``True``).
    """

    strategy: str
    acl_number: int
    interface: str
    direction: str
    destinations: tuple[str, ...]
    resolved: tuple[tuple[str, str], ...]
    save: bool


class BlockSiteDialog(QDialog):
    """Modal "Bloquear site" — assistente de 4 etapas.

    Estratégia → destinos → aplicação → **revisão obrigatória** (D4).
    A decisão só é produzida na revisão: não existe atalho para
    ``accept()`` sem passar por ela.

    Args:
        parent: widget pai.
        can_save: o papel atual permite salvar na startup-config (admin).
        resolver: resolve um domínio em IPv4 — injetável em testes; por
            padrão usa o DNS do sistema (fail-closed se não resolver).
    """

    _PAGE_STRATEGY = 0
    _PAGE_DESTINATIONS = 1
    _PAGE_APPLICATION = 2
    _PAGE_REVIEW = 3

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        can_save: bool = True,
        resolver: Callable[[str], Sequence[str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._can_save = can_save
        self._resolver = resolver
        self._strategy = "deny-list"
        self._destinations: list[str] = []
        self._resolved: tuple[tuple[str, str], ...] = ()
        self._decision: BlockSiteDecision | None = None
        self._entries: dict[str, QLineEdit] = {}
        self._direction_cb: QComboBox | None = None
        self._save_chk: QCheckBox | None = None
        self._cli_box: QPlainTextEdit | None = None
        self._strategy_btns: dict[str, QPushButton] = {}
        self._dest_list: QListWidget | None = None
        self._dest_entry: QLineEdit | None = None
        self._review_title: QLabel = QLabel()
        self._review_grid: QFrame = QFrame()

        self._build_ui()
        self.setModal(True)

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.setWindowTitle("Bloquear site")
        self.setMinimumSize(580, 540)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setStyleSheet(f"background: {C.BG_CARD};")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_strategy_page())
        self._stack.addWidget(self._build_destinations_page())
        self._stack.addWidget(self._build_application_page())
        self._stack.addWidget(self._build_review_page())
        self._stack.setCurrentIndex(self._PAGE_STRATEGY)

    def _build_strategy_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        intro = QLabel("Escolha a estratégia de bloqueio:")
        intro.setStyleSheet(
            f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY};"
        )
        lay.addWidget(intro)

        descriptions = {
            "deny-list": (
                "deny-list — bloquear apenas os destinos listados."
            ),
            "all-except": (
                "all-except — bloquear tudo, exceto os destinos listados."
            ),
        }
        for key in ("deny-list", "all-except"):
            btn = _button(key, C.NEON_CYAN)
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda _checked=False, k=key: self._select_strategy(k)
            )
            self._strategy_btns[key] = btn
            lay.addWidget(btn)
            desc = QLabel(descriptions[key])
            desc.setStyleSheet(
                f"color: {C.FG_DIM}; font: 10px {C.FONT_UI_FAMILY};"
            )
            desc.setWordWrap(True)
            lay.addWidget(desc)
        self._refresh_strategy_style()

        lay.addStretch()
        lay.addWidget(
            self._nav_bar(
                back=None,
                next_label="Avançar →",
                next_slot=self._goto_destinations,
            )
        )
        return page

    def _build_destinations_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        intro = QLabel(
            "Adicione os destinos a bloquear: IPv4 (203.0.113.10), "
            "IPv4/máscara (10.1.2.0/24) ou domínio (example.com)."
        )
        intro.setStyleSheet(
            f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY};"
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)

        row = QWidget(page)
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        self._dest_entry = QLineEdit()
        self._dest_entry.setPlaceholderText(
            "Digite o destino (IPv4[/máscara] ou domínio)"
        )
        self._dest_entry.setStyleSheet(
            f"background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
            f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
            f"padding: 4px 8px; font: 12px {C.FONT_UI_FAMILY};"
        )
        self._dest_entry.textChanged.connect(
            lambda _t: _clear_invalid(self._dest_entry)
            if self._dest_entry is not None
            else None
        )
        self._dest_entry.returnPressed.connect(self._add_destination)
        row_l.addWidget(self._dest_entry, stretch=1)
        add_btn = _button("Adicionar", C.NEON_CYAN)
        add_btn.clicked.connect(self._add_destination)
        row_l.addWidget(add_btn)
        lay.addWidget(row)

        self._dest_list = QListWidget()
        self._dest_list.setMinimumHeight(160)
        self._dest_list.setStyleSheet(
            f"background: {C.BG_INPUT}; color: {C.NEON_CYAN}; "
            f"border: 1px solid {C.BORDER_NRM}; border-radius: 3px; "
            f"font: 12px {C.FONT_UI_FAMILY};"
        )
        lay.addWidget(self._dest_list, stretch=1)

        remove_btn = _button("Remover selecionado", C.NEON_RED)
        remove_btn.clicked.connect(self._remove_destination)
        lay.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        lay.addStretch()
        lay.addWidget(
            self._nav_bar(
                back="← Voltar",
                back_slot=self._goto_strategy,
                next_label="Avançar →",
                next_slot=self._goto_application,
            )
        )
        return page

    def _build_application_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        intro = QLabel(
            "Onde a regra será aplicada (traffic-filter na interface):"
        )
        intro.setStyleSheet(
            f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY};"
        )
        lay.addWidget(intro)

        fields: list[tuple[str, str, str]] = [
            ("acl_number", "Número da ACL:", "3100"),
            ("interface", "Interface:", "GigabitEthernet0/0/0"),
        ]
        for key, label, default in fields:
            row = QWidget(page)
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.addWidget(_style_label(label))
            entry = _style_input(default)
            entry.setText(default)
            entry.textChanged.connect(lambda _t, e=entry: _clear_invalid(e))
            self._entries[key] = entry
            row_l.addWidget(entry, stretch=1)
            lay.addWidget(row)

        dir_row = QWidget(page)
        dir_l = QHBoxLayout(dir_row)
        dir_l.setContentsMargins(0, 0, 0, 0)
        dir_l.addWidget(_style_label("Direção:"))
        self._direction_cb = _style_combo()
        self._direction_cb.addItems(["outbound", "inbound"])
        dir_l.addWidget(self._direction_cb, stretch=1)
        lay.addWidget(dir_row)

        hint = QLabel(
            "Direção outbound bloqueia a saída para a WAN; inbound, a "
            "chegada. ACL avançada usa número 3000–3999."
        )
        hint.setStyleSheet(
            f"color: {C.FG_DIM}; font: 10px {C.FONT_UI_FAMILY};"
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addStretch()
        lay.addWidget(
            self._nav_bar(
                back="← Voltar",
                back_slot=self._goto_destinations,
                next_label="Avançar →",
                next_slot=self._goto_review,
            )
        )
        return page

    def _build_review_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._review_title.setText("Revisão — Bloquear site")
        self._review_title.setStyleSheet(
            f"color: {C.NEON_AMBER}; font: 12px {C.FONT_UI_FAMILY}; bold;"
        )
        lay.addWidget(self._review_title)

        header = QLabel("Parâmetros selecionados")
        header.setStyleSheet(
            f"color: {C.FG_DIM}; font: 10px {C.FONT_UI_FAMILY}; bold;"
        )
        lay.addWidget(header)
        self._review_grid = _param_grid([])
        lay.addWidget(self._review_grid)

        cli_header = QLabel("BLOCO QUE SERÁ ENVIADO AO DEVICE")
        cli_header.setStyleSheet(
            f"color: {C.FG_DIM}; font: 10px {C.FONT_UI_FAMILY}; bold;"
        )
        lay.addWidget(cli_header)
        self._cli_box = _read_only_block("", height=170)
        lay.addWidget(self._cli_box)

        self._save_chk = QCheckBox(
            "Salvar na startup-config (persistir após reboot)", page
        )
        self._save_chk.setChecked(False)
        self._save_chk.setEnabled(self._can_save)
        self._save_chk.setStyleSheet(
            f"color: {C.FG_DIM}; font: 11px {C.FONT_UI_FAMILY};"
        )
        if not self._can_save:
            self._save_chk.setToolTip(
                "Exige papel admin para persistir no device."
            )
        lay.addWidget(self._save_chk)

        bar = QWidget(page)
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(0, 0, 0, 0)
        back_btn = _button("← Voltar", C.NEON_PURP)
        back_btn.clicked.connect(self._goto_application)
        bar_l.addWidget(back_btn)
        bar_l.addSpacing(8)
        send_btn = _button("Salvar/Enviar", C.NEON_CYAN)
        send_btn.clicked.connect(self._on_confirm)
        bar_l.addWidget(send_btn)
        bar_l.addSpacing(8)
        cancel_btn = _button("Cancelar", C.NEON_PURP)
        cancel_btn.clicked.connect(self.reject)
        bar_l.addWidget(cancel_btn)
        bar_l.addStretch()
        lay.addWidget(bar)
        return page

    def _nav_bar(
        self,
        *,
        back: str | None,
        next_label: str,
        next_slot: Callable[[], None],
        back_slot: Callable[[], None] | None = None,
    ) -> QWidget:
        """Barra padrão Voltar/Avançar/Cancelar das etapas intermediárias."""
        bar = QWidget()
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(0, 0, 0, 0)
        if back is not None:
            back_btn = _button(back, C.NEON_PURP)
            back_btn.clicked.connect(
                back_slot if back_slot is not None else self.reject
            )
            bar_l.addWidget(back_btn)
            bar_l.addSpacing(8)
        next_btn = _button(next_label, C.NEON_CYAN)
        next_btn.clicked.connect(next_slot)
        bar_l.addWidget(next_btn)
        bar_l.addSpacing(8)
        cancel_btn = _button("Cancelar", C.NEON_PURP)
        cancel_btn.clicked.connect(self.reject)
        bar_l.addWidget(cancel_btn)
        bar_l.addStretch()
        return bar

    # ── Estratégia ──────────────────────────────────────────────────
    def _select_strategy(self, key: str) -> None:
        self._strategy = key
        self._refresh_strategy_style()

    def _refresh_strategy_style(self) -> None:
        for key, btn in self._strategy_btns.items():
            selected = key == self._strategy
            color = C.NEON_CYAN if selected else C.FG_DIM
            bg = C.BG_INPUT if selected else "transparent"
            border = 2 if selected else 1
            btn.setStyleSheet(
                f"background: {bg}; color: {color}; "
                f"border: {border}px solid {color}; border-radius: 3px; "
                f"padding: 8px 14px; text-align: left; "
                f"font: bold 12px {C.FONT_UI_FAMILY};"
            )
            btn.setChecked(selected)

    # ── Destinos ────────────────────────────────────────────────────
    def _add_destination(self) -> None:
        if self._dest_entry is None or self._dest_list is None:
            return
        raw = self._dest_entry.text().strip()
        try:
            parse_destination(raw)
        except SdnValidationError as exc:
            if self._dest_entry is not None:
                _mark_invalid(self._dest_entry)
            self._show_error(str(exc))
            return
        if raw in self._destinations:
            self._show_error(f"Destino duplicado: '{raw}'")
            return
        self._destinations.append(raw)
        self._dest_list.addItem(raw)
        self._dest_entry.clear()
        if self._dest_entry is not None:
            _clear_invalid(self._dest_entry)

    def _remove_destination(self) -> None:
        if self._dest_list is None:
            return
        row = self._dest_list.currentRow()
        if row < 0:
            return
        self._dest_list.takeItem(row)
        del self._destinations[row]

    # ── Navegação ───────────────────────────────────────────────────
    def _goto_strategy(self) -> None:
        self._stack.setCurrentIndex(self._PAGE_STRATEGY)

    def _goto_destinations(self) -> None:
        self._stack.setCurrentIndex(self._PAGE_DESTINATIONS)

    def _goto_application(self) -> None:
        if not self._destinations:
            self._show_error("Adicione ao menos um destino.")
            return
        self._stack.setCurrentIndex(self._PAGE_APPLICATION)

    def _validate_application(self) -> bool:
        entry = self._entries.get("acl_number")
        if entry is not None:
            try:
                num = int(entry.text().strip() or "0")
                low, high = ACL_BLOCK_RANGE
                if not low <= num <= high:
                    raise ValueError
            except ValueError:
                _mark_invalid(entry)
                self._show_error(
                    f"Número da ACL deve estar entre "
                    f"{ACL_BLOCK_RANGE[0]} e {ACL_BLOCK_RANGE[1]}."
                )
                return False
        iface = self._entries.get("interface")
        if iface is not None and not iface.text().strip():
            _mark_invalid(iface)
            self._show_error("Informe a interface.")
            return False
        return True

    def _goto_review(self) -> None:
        """Valida, resolve os domínios e monta a revisão (etapa final)."""
        if not self._validate_application():
            return
        if not self._destinations:
            self._show_error("Adicione ao menos um destino.")
            return
        acl_number = int(self._entries["acl_number"].text().strip())
        interface = self._entries["interface"].text().strip()
        direction = (
            self._direction_cb.currentText()
            if self._direction_cb is not None
            else "outbound"
        )
        try:
            resolved = resolve_destinations(
                self._destinations, self._resolver
            )
            lines = preview_site_lines(
                strategy=self._strategy,
                acl_number=acl_number,
                interface=interface,
                direction=direction,
                resolved=resolved,
            )
        except SdnValidationError as exc:
            self._show_error(str(exc))
            return

        self._resolved = resolved
        self._review_title.setText(
            f"Revisão — Bloquear site ({self._strategy})"
        )
        rows: list[tuple[str, str]] = [
            ("Estratégia", self._strategy),
            ("Destinos", ", ".join(self._destinations)),
            ("Destinos resolvidos", str(len(resolved))),
            ("Número da ACL", str(acl_number)),
            ("Interface", interface),
            ("Direção", direction),
        ]
        new_grid = _param_grid(rows)
        self._layout_replace(self._review_grid, new_grid)
        self._review_grid = new_grid

        if self._cli_box is not None:
            self._cli_box.setPlainText("\n".join(lines))
        if self._save_chk is not None:
            self._save_chk.setChecked(False)

        self._stack.setCurrentIndex(self._PAGE_REVIEW)

    def _layout_replace(self, old: QWidget, new: QWidget) -> None:
        """Troca um widget por outro mantendo a posição no layout."""
        parent_widget = old.parentWidget()
        if parent_widget is None:
            return
        parent_layout = parent_widget.layout()
        if not isinstance(parent_layout, QVBoxLayout):
            return
        index = parent_layout.indexOf(old)
        if index < 0:
            return
        parent_layout.removeWidget(old)
        old.deleteLater()
        parent_layout.insertWidget(index, new)

    # ── Confirmação ─────────────────────────────────────────────────
    def _show_error(self, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self, "Bloquear site", message)

    def _on_confirm(self) -> None:
        """Só é alcançável a partir da página de revisão (D4)."""
        if self._stack.currentIndex() != self._PAGE_REVIEW:
            return
        entry = self._entries.get("acl_number")
        iface = self._entries.get("interface")
        if entry is None or iface is None:
            return
        try:
            acl_number = int(entry.text().strip())
        except ValueError:
            return
        save = bool(self._save_chk.isChecked()) if self._save_chk else False
        self._decision = BlockSiteDecision(
            strategy=self._strategy,
            acl_number=acl_number,
            interface=iface.text().strip(),
            direction=(
                self._direction_cb.currentText()
                if self._direction_cb is not None
                else "outbound"
            ),
            destinations=tuple(self._destinations),
            resolved=self._resolved,
            save=save,
        )
        self.accept()

    def get_decision(self) -> BlockSiteDecision:
        """Decisão confirmada.

        Raises:
            RuntimeError: chamado antes de ``exec()`` ou com diálogo
                rejeitado.
        """
        if self.result() != QDialog.DialogCode.Accepted:
            raise RuntimeError(
                "get_decision() chamado antes de exec() ou diálogo rejeitado."
            )
        if self._decision is None:
            raise RuntimeError("decisão ausente após aceitação.")
        return self._decision
