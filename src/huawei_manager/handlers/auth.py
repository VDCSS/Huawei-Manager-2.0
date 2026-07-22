"""Auth mixin — authentication dialogs and access control."""

from __future__ import annotations

import datetime
from typing import cast

from PySide6.QtWidgets import QMessageBox, QWidget

from huawei_manager._config import ADMIN_PASSWORD, TECNICO_PASSWORD, log
from huawei_manager._protocols import AppCoreProtocol
from huawei_manager.sdn_controller.authz import Role
from huawei_manager.widgets.auth_overlay import AuthOverlay


class AuthMixin:
    """Mixin com metodos de autenticacao (admin / tecnico)."""

    # ══════════════════════════════════════════════════════════════════
    #  AUTENTICACAO
    # ══════════════════════════════════════════════════════════════════
    def _show_auth_dialog(self: AppCoreProtocol) -> None:
        if self._access_level != "user":
            self._access_level = "user"
            self._session_tracker.set_role(Role.USER)
            self._mock_mode = False
            self._watcher.stop()
            self._rebuild_page("topology")
            log.info("Acesso: deslogado")
            return

        if self._auth_overlay is not None and self._auth_overlay.isVisible():
            return

        if not ADMIN_PASSWORD or not TECNICO_PASSWORD:
            QMessageBox.warning(None, "Configuracao incompleta",
                "Defina ADMIN_PASSWORD e TECNICO_PASSWORD no .env")
            return

        now = datetime.datetime.now().timestamp()
        if now < self._admin_locked_until:
            remaining = int(self._admin_locked_until - now)
            QMessageBox.warning(None, "Acesso Bloqueado",
                f"Tentativas excedidas. Aguarde {remaining}s e tente novamente.")
            return

        def _on_result(level: str, attempts: int, locked_until: float) -> None:
            if level != "user":
                self._access_level = level
                self._session_tracker.set_role(Role.from_string(level))
                self._admin_attempts = 0
                self._admin_locked_until = 0
                self._rebuild_page("topology")
                if level == "tecnico":
                    self._watcher.start()
                else:
                    self._watcher.stop()
                log.info("Acesso: %s autenticado", level)
            else:
                self._admin_attempts = attempts
                self._admin_locked_until = locked_until
                if locked_until > 0:
                    log.warning("Acesso: lockout por %ds", self.ADMIN_LOCKOUT_SECS)

        overlay = AuthOverlay(
            parent=cast(QWidget, self.content),
            on_result=_on_result,
            admin_locked_until=self._admin_locked_until,
            admin_max_attempts=self.ADMIN_MAX_ATTEMPTS,
            admin_lockout_secs=self.ADMIN_LOCKOUT_SECS,
            attempts_so_far=self._admin_attempts,
        )
        self._auth_overlay = overlay
        overlay.show()

    def _require_access(self: AppCoreProtocol, level: str = "admin") -> bool:
        """Verifica se o nivel de acesso atual atende ao requisito.

        Returns True se permitido, False se bloqueado.
        """
        levels = {"user": 0, "admin": 1, "tecnico": 2}
        return levels.get(self._access_level, 0) >= levels.get(level, 1)
