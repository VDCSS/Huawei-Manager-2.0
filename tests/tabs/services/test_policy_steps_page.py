"""TDD da etapa visual "Cadeia traffic policy" nos modais de bloqueio.

O passo a passo é uma página do wizard **antes** da revisão (D4 continua
obrigatório). No Bloquear Internet ele é aberto pelas ações Aplicar/
Desaplicar/Apagar regra e Excluir cadeia; no Bloquear site, pelas ações
pontuais (Excluir cadeia). O fluxo comum CONFIG → Revisão não passa por
ele — por isso os testes do site abrem a página diretamente.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from huawei_manager.services.acl_presets import AclBlockProfile
from huawei_manager.widgets.block_dialog import BlockInternetDialog, BlockSiteDialog


@pytest.fixture(autouse=True)
def _no_msgbox(monkeypatch):
    """Evita QMessageBox.modal travar os testes headless."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)


def _profile(**over) -> AclBlockProfile:
    base = dict(
        device_key="RTR-01@10.0.0.1",
        acl_name="bloqueio-padrão",
        acl_number=3000,
        destination_ip="203.0.113.10",
        destination_mask="0.0.0.0",
        interface="GigabitEthernet0/0/0",
        direction="outbound",
        created_from_snapshot=False,
        applied=False,
    )
    base.update(over)
    return AclBlockProfile(**base)  # type: ignore[arg-type]


def _button(widget: QWidget, needle: str) -> QPushButton:
    for btn in widget.findChildren(QPushButton):
        if btn.isVisible() and needle in btn.text():
            return btn
    raise AssertionError(f"botão visível '{needle}' não encontrado")


def _advance(widget: QWidget) -> QPushButton:
    """Avançar das etapas intermediárias (não o 'p/ revisão')."""
    for btn in widget.findChildren(QPushButton):
        text = btn.text()
        if (
            btn.isVisible()
            and text.strip().startswith("Avançar")
            and "revisão" not in text.lower()
        ):
            return btn
    raise AssertionError("botão 'Avançar →' visível não encontrado")


def _step(dialog: QWidget, number: int) -> QWidget:
    hits = dialog.findChildren(QWidget, f"policy_step_{number}")
    assert hits, f"passo {number} da cadeia não existe"
    return hits[0]


def _step_cli(step: QWidget) -> str:
    return "\n".join(
        box.toPlainText()
        for box in step.findChildren(QPlainTextEdit, "policy_step_cli")
    )


def _step_hint(step: QWidget) -> str:
    from PySide6.QtWidgets import QLabel

    labels = step.findChildren(QLabel, "policy_step_hint")
    return labels[0].text() if labels else ""


def _show(qtbot, dialog) -> None:
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)


class TestInternetStepsPage:
    def test_apply_opens_five_steps(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)

        _button(dialog, "Aplicar regra").click()

        assert "acl number 3000" in _step_cli(_step(dialog, 1))
        assert "traffic classifier C_BLOQ_3000" in _step_cli(_step(dialog, 2))
        assert "traffic behavior B_BLOQ_3000" in _step_cli(_step(dialog, 3))
        assert "traffic policy P_BLOQ_3000" in _step_cli(_step(dialog, 4))
        assert "traffic-policy P_BLOQ_3000 outbound" in _step_cli(
            _step(dialog, 5)
        )

    def test_back_returns_to_manage_page(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)
        _button(dialog, "Aplicar regra").click()

        _button(dialog, "← Voltar").click()

        assert _button(dialog, "Apagar regra").isVisible()

    def test_advance_goes_to_mandatory_review(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)
        _button(dialog, "Aplicar regra").click()

        _button(dialog, "Avançar p/ revisão").click()

        assert _button(dialog, "Salvar/Enviar").isVisible()

    def test_confirm_blocked_before_review(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)
        _button(dialog, "Aplicar regra").click()

        dialog._on_confirm()

        assert dialog.result() != QDialog.DialogCode.Accepted

    def test_unapply_shows_only_binding_step(self, qtbot):
        dialog = BlockInternetDialog(
            profile=_profile(applied=True), applied=True
        )
        _show(qtbot, dialog)

        _button(dialog, "Desaplicar regra").click()

        assert "undo traffic-policy P_BLOQ_3000 outbound" in _step_cli(
            _step(dialog, 5)
        )
        assert not dialog.findChildren(QWidget, "policy_step_1")
        assert "permanec" in _step_hint(_step(dialog, 5)).lower()

    def test_delete_shows_removal_in_reverse_order(self, qtbot):
        dialog = BlockInternetDialog(profile=_profile())
        _show(qtbot, dialog)

        _button(dialog, "Apagar regra").click()

        assert "undo traffic-policy P_BLOQ_3000 outbound" in _step_cli(
            _step(dialog, 5)
        )
        assert "undo acl number 3000" in _step_cli(_step(dialog, 1))
        assert all(
            any("undo" in line for line in _step_cli(_step(dialog, n)).splitlines())
            for n in (1, 2, 3, 4, 5)
        )

    def test_delete_preserves_preexisting_acl_step(self, qtbot):
        dialog = BlockInternetDialog(
            profile=_profile(created_from_snapshot=True)
        )
        _show(qtbot, dialog)

        _button(dialog, "Apagar regra").click()

        assert not dialog.findChildren(QWidget, "policy_step_1")
        assert _step(dialog, 5).isVisible()


class TestSiteStepsPage:
    def _goto_steps(self, qtbot, *, strategy: str | None = None):
        dialog = BlockSiteDialog(resolver=lambda host: ["203.0.113.10"])
        _show(qtbot, dialog)
        if strategy is not None:
            _button(dialog, strategy).click()
        _advance(dialog).click()
        entry = next(
            e
            for e in dialog.findChildren(QLineEdit)
            if e.isVisible() and "destino" in e.placeholderText().lower()
        )
        entry.setText("example.com")
        _button(dialog, "Adicionar").click()
        _advance(dialog).click()
        _advance(dialog).click()  # aplicação → configuração da cadeia
        # CONFIG → Revisão é o fluxo comum; os passos ficam nas ações
        # pontuais (ex.: "Excluir cadeia"). Abrimos a página diretamente
        # com o mesmo back_page da entrada real (application).
        dialog._steps_back_page = dialog._PAGE_APPLICATION
        dialog._goto_steps()
        return dialog

    def test_site_apply_shows_five_steps(self, qtbot):
        dialog = self._goto_steps(qtbot)

        assert "acl number 3100" in _step_cli(_step(dialog, 1))
        assert any(
            "rule 5 deny" in line
            for line in _step_cli(_step(dialog, 1)).splitlines()
        )
        assert "if-match acl 3100" in _step_cli(_step(dialog, 2))
        assert "traffic behavior B_SITE_3100" in _step_cli(_step(dialog, 3))
        assert "traffic policy P_SITE_3100" in _step_cli(_step(dialog, 4))
        assert "traffic-policy P_SITE_3100 outbound" in _step_cli(
            _step(dialog, 5)
        )

    def test_all_except_explains_final_deny(self, qtbot):
        dialog = self._goto_steps(qtbot, strategy="all-except")

        assert "rule 999 deny ip source any" in _step_cli(_step(dialog, 1))
        assert "999" in _step_hint(_step(dialog, 1))

    def test_back_returns_to_application(self, qtbot):
        dialog = self._goto_steps(qtbot)

        _button(dialog, "← Voltar").click()

        from PySide6.QtWidgets import QLabel

        assert any(
            label.isVisible() and "Interface:" in label.text()
            for label in dialog.findChildren(QLabel)
        )

    def test_advance_goes_to_mandatory_review_and_confirms(self, qtbot):
        dialog = self._goto_steps(qtbot)

        _button(dialog, "Avançar p/ revisão").click()
        assert _button(dialog, "Salvar/Enviar").isVisible()

        _button(dialog, "Salvar/Enviar").click()

        assert dialog.result() == QDialog.DialogCode.Accepted
        decision = dialog.get_decision()
        assert decision.strategy == "deny-list"
        assert decision.resolved == (("203.0.113.10", "0.0.0.0"),)

    def test_confirm_blocked_before_review(self, qtbot):
        dialog = self._goto_steps(qtbot)

        dialog._on_confirm()

        assert dialog.result() != QDialog.DialogCode.Accepted
