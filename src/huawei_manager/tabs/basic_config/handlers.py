"""Handlers da aba Config Básica (lógica de negócio, validação e execução)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from huawei_manager.basic_config.models import (
    AdminUserConfig,
    BasicConfigPlan,
    HostnameConfig,
    InterfaceL3Config,
    L2AccessConfig,
    SshConfig,
)
from huawei_manager.basic_config.vrp_version import (
    VrpVersion,
    detect_vrp_version,
)
from huawei_manager.command import ConfigCommand, audit_config_op
from huawei_manager.exceptions import SdnError, SdnValidationError, SnapshotError
from huawei_manager.sdn_controller.event_queue import Event, EventType
from huawei_manager.sdn_controller.events import CommandExecutedPayload
from huawei_manager.security_redaction import redact_secrets
from huawei_manager.tabs import _ui

if TYPE_CHECKING:
    from huawei_manager.tabs._contract import TabContext
    from huawei_manager.tabs.basic_config.state import BasicConfigState

log = logging.getLogger(__name__)


class BasicConfigHandlers:
    """Controlador de ações da aba Config Básica."""

    def __init__(self, ctx: TabContext, state: BasicConfigState) -> None:
        self._ctx = ctx
        self._state = state

    def build_plan_from_ui(
        self, is_switch: bool = False
    ) -> BasicConfigPlan:
        """Coleta e valida os campos da UI, construindo o BasicConfigPlan."""
        state = self._state

        hostname_cfg: HostnameConfig | None = None
        if state.hostname_chk and state.hostname_chk.isChecked():
            h_val = state.hostname_input.text().strip() if state.hostname_input else ""
            if not h_val:
                raise SdnValidationError("Hostname marcado, mas o campo está vazio.")
            hostname_cfg = HostnameConfig(hostname=h_val)

        iface_cfg: InterfaceL3Config | None = None
        if state.iface_l3_chk and state.iface_l3_chk.isChecked():
            name = state.iface_l3_name.text().strip() if state.iface_l3_name else ""
            ip = state.iface_l3_ip.text().strip() if state.iface_l3_ip else ""
            mask = state.iface_l3_mask.text().strip() if state.iface_l3_mask else ""
            desc = state.iface_l3_desc.text().strip() if state.iface_l3_desc else ""
            shut = state.iface_l3_shutdown.isChecked() if state.iface_l3_shutdown else False
            ps = (
                state.iface_l3_undo_portswitch.isChecked()
                if state.iface_l3_undo_portswitch
                else False
            )
            if not name or not ip or not mask:
                raise SdnValidationError(
                    "Interface L3: nome, IP e máscara são obrigatórios."
                )
            iface_cfg = InterfaceL3Config(
                interface=name,
                ip=ip,
                mask=mask,
                description=desc,
                shutdown=shut,
                undo_portswitch=ps,
                is_switch=is_switch,
            )

        l2_cfg: L2AccessConfig | None = None
        if state.l2_chk and state.l2_chk.isChecked():
            vlan = state.l2_vlan_id.text().strip() if state.l2_vlan_id else ""
            iface = state.l2_iface.text().strip() if state.l2_iface else ""
            ip = state.l2_ip.text().strip() if state.l2_ip else ""
            mask = state.l2_mask.text().strip() if state.l2_mask else ""
            v_desc = state.l2_vlan_desc.text().strip() if state.l2_vlan_desc else ""
            i_desc = state.l2_iface_desc.text().strip() if state.l2_iface_desc else ""
            vi_desc = state.l2_vlanif_desc.text().strip() if state.l2_vlanif_desc else ""
            if not vlan or not iface or not ip or not mask:
                raise SdnValidationError(
                    "L2 Access: VLAN ID, interface de acesso, IP e máscara são obrigatórios."
                )
            l2_cfg = L2AccessConfig(
                vlan_id=vlan,
                interface=iface,
                ip=ip,
                mask=mask,
                vlan_description=v_desc,
                interface_description=i_desc,
                vlanif_description=vi_desc,
            )

        ssh_cfg: SshConfig | None = None
        if state.ssh_chk and state.ssh_chk.isChecked():
            u = state.ssh_user.text().strip() if state.ssh_user else ""
            p = state.ssh_pass.text().strip() if state.ssh_pass else ""
            pc = state.ssh_pass_confirm.text().strip() if state.ssh_pass_confirm else ""
            vty = state.ssh_vty.text().strip() if state.ssh_vty else "0 4"
            if not u or not p:
                raise SdnValidationError("SSH: usuário e senha são obrigatórios.")
            if p != pc:
                raise SdnValidationError("SSH: confirmação de senha não confere.")
            ssh_cfg = SshConfig(username=u, password=p, vty_range=vty or "0 4")

        admin_cfg: AdminUserConfig | None = None
        if state.admin_chk and state.admin_chk.isChecked():
            u = state.admin_user.text().strip() if state.admin_user else ""
            p = state.admin_pass.text().strip() if state.admin_pass else ""
            pc = (
                state.admin_pass_confirm.text().strip()
                if state.admin_pass_confirm
                else ""
            )
            priv = state.admin_priv.text().strip() if state.admin_priv else "15"
            if not u or not p:
                raise SdnValidationError(
                    "Usuário administrativo: nome e senha são obrigatórios."
                )
            if p != pc:
                raise SdnValidationError(
                    "Usuário administrativo: confirmação de senha não confere."
                )
            admin_cfg = AdminUserConfig(
                username=u, password=p, privilege=priv or "15"
            )

        plan = BasicConfigPlan(
            hostname=hostname_cfg,
            interface_l3=iface_cfg,
            l2_access=l2_cfg,
            ssh=ssh_cfg,
            admin_user=admin_cfg,
        )
        if plan.is_empty():
            raise SdnValidationError("Nenhuma seção de configuração foi selecionada.")
        return plan

    def preview_plan(self) -> None:
        """Gera e exibe o bloco de comandos que seria aplicado."""
        try:
            plan = self.build_plan_from_ui()
            lines = plan.build_lines()
        except SdnValidationError as err:
            _ui.write(self._state.output, f"✘  Erro de validação: {err}", self._ctx.dispatch)
            return

        secrets = plan.collect_secrets()
        redacted_text = redact_secrets("\n".join(lines), secrets)
        vrp_note = (
            "\n[VRP] commit+save automático serão executados pelo dispositivo "
            "conforme a versão detectada na aplicação."
        )
        header = "=== PRÉVIA DO BLOCO DE CONFIGURAÇÃO (VRP) ===\n"
        _ui.write(
            self._state.output,
            f"{header}{redacted_text}\n{vrp_note}",
            self._ctx.dispatch,
        )

    def apply_plan(self) -> None:
        """Aplica o plano validado via SSHSouthbound.send_config_block.

        O commit/salvamento é tratado automaticamente conforme a versão VRP
        detectada:

        * VRP8 (exige commit): as mudanças são commitadas automaticamente
          ao sair do system-view, e depois gravadas com
          ``save all virtual-systems`` na visão exec.
        * Outras VRP: as mudanças são aplicadas e gravadas com ``save``.
        """
        if not self._ctx.require_access("admin"):
            _ui.write(
                self._state.output,
                "✘  Permissão negada: Configuração Básica exige papel admin.",
                self._ctx.dispatch,
            )
            return

        mode = self._ctx.svc_mode()
        if mode == "mock":
            plan_preview = ""
            try:
                p = self.build_plan_from_ui()
                plan_preview = "\n" + "\n".join(p.build_lines())
            except SdnValidationError:
                pass
            _ui.write(
                self._state.output,
                "ℹ  Modo MOCK ativo: em modo simulado, nenhuma alteração real é enviada ao device."
                + plan_preview,
                self._ctx.dispatch,
            )
            return

        if self._ctx.ensure_device_ready("aplicar a configuração básica") is None:
            return

        # ── Detecta tipo do dispositivo para decidir se undo portswitch é válido ──
        device = self._ctx.device()
        is_switch = device is not None and device.type.upper() == "SWITCH"
        if is_switch:
            _ui.write(
                self._state.output,
                "ℹ  Dispositivo detectado como SWITCH — 'undo portswitch' será enviado se marcado.",
                self._ctx.dispatch,
            )

        # ── Detecção de versão VRP antes de qualquer mutação ──
        # O NAPALM não é confiável para detecção de versão (backend opcional,
        # pode cair para Netmiko). Usamos o caminho SSH/Netmiko já ativo e
        # rodamos ``display version`` para adaptar o bloco antes de enviar.
        version_output = ""
        try:
            version_output = self._ctx.sb.send_command("display version")
        except SdnError:
            version_output = ""
        vrp_version = detect_vrp_version(version_output)
        if vrp_version == VrpVersion.UNKNOWN:
            _ui.write(
                self._state.output,
                "⚠  Não foi possível detectar a versão VRP (usando sintaxe VRP8 por padrão). "
                "Revise o bloco na prévia antes de aplicar.",
                self._ctx.dispatch,
            )

        try:
            plan = self.build_plan_from_ui(is_switch=is_switch)
            lines = plan.build_lines(vrp_version=vrp_version)
        except SdnValidationError as err:
            _ui.write(self._state.output, f"✘  Erro de validação: {err}", self._ctx.dispatch)
            return

        secrets = plan.collect_secrets()
        rollback_lines = plan.build_rollback_lines(vrp_version=vrp_version)

        session = self._ctx.session
        user = getattr(session, "_user", "admin")
        host = getattr(session, "_host", "unknown")
        session_id = getattr(session, "_session_id", None)
        audit = self._ctx.audit

        def _apply_lines(block: list[str]) -> tuple[bool, str]:
            # save é opcional (checkbox da UI). O commit (VRP8) continua decidido
            # automaticamente pela versão VRP via requires_commit()/save_command().
            save_enabled = self._state.save_chk.isChecked() if self._state.save_chk else True
            return self._ctx.sb.send_config_block(
                block,
                save=save_enabled,
                secrets=secrets,
                vrp_version=vrp_version,
            )

        def _verify_applied() -> tuple[bool, str]:
            """Lê o running-config e confere se as linhas do bloco estão lá."""
            try:
                running = self._ctx.sb.send_command("display current-configuration")
            except SdnError as exc:
                return False, f"Não foi possível ler running-config para verificação: {exc}"
            missing: list[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped in {"quit", "return", "system-view"}:
                    continue
                if stripped.startswith("ip address "):
                    ip_part = stripped.split()[1] if len(stripped.split()) > 1 else ""
                    if ip_part and ip_part not in running:
                        missing.append(stripped)
                    continue
                if any(secret in stripped for secret in (secrets or [])):
                    continue
                if stripped not in running:
                    missing.append(stripped)
            if missing:
                return False, (
                    "Verificação falhou: as seguintes linhas não foram encontradas "
                    f"no running-config: {', '.join(missing[:5])}"
                )
            return True, "Verificação pós-aplicação confirmada no running-config."

        cmd = ConfigCommand(
            lines=lines,
            read_state=lambda: self._ctx.sb.send_command("display current-configuration"),
            apply_fn=_apply_lines,
            dry_run=self._ctx.dry_run,
            rollback_lines=rollback_lines,
            verify_fn=_verify_applied,
        )

        _ui.loading(
            self._state.output,
            "Aplicando bloco de configuração básica...",
            self._ctx.dispatch,
        )

        try:
            result = cmd.execute()
        except SnapshotError as exc:
            self._ctx.sb.invalidate_connection()
            _ui.write(
                self._state.output,
                f"✘  Snapshot pré-mudança falhou: {exc} — nada foi aplicado.",
                self._ctx.dispatch,
            )
            audit_config_op(
                audit,
                op="basic_config_apply",
                user=user,
                host=host,
                session_id=session_id,
                status="blocked",
                reason="snapshot falhou",
            )
            return
        except SdnError as exc:
            self._ctx.sb.invalidate_connection()
            self._ctx.set_last_config_command(cmd)
            _ui.write(
                self._state.output,
                f"✘  Falha de comunicação SSH: {exc}",
                self._ctx.dispatch,
            )
            audit_config_op(
                audit,
                op="basic_config_apply",
                user=user,
                host=host,
                session_id=session_id,
                status="error",
                reason=str(exc),
            )
            return

        self._ctx.set_last_config_command(cmd)
        clean_msg = redact_secrets(result.message, secrets)
        _ui.write(self._state.output, clean_msg, self._ctx.dispatch)

        audit_config_op(
            audit,
            op="basic_config_apply",
            user=user,
            host=host,
            session_id=session_id,
            status=result.status,
            duration_ms=result.duration_ms,
        )

        self._ctx.event_bus.put(
            Event(
                EventType.CONFIG_CHANGED,
                source="basic_config",
                payload=CommandExecutedPayload(
                    command="basic-config",
                    data={"status": result.status},
                ),
            )
        )

    def rollback_plan(self) -> None:
        """Executa rollback do último comando de configuração registrado."""
        last_cmd = self._ctx.get_last_config_command()
        if last_cmd is None:
            _ui.write(
                self._state.output,
                "✘  Nenhum comando de configuração anterior para rollback.",
                self._ctx.dispatch,
            )
            return

        _ui.loading(
            self._state.output,
            "Executando rollback da configuração...",
            self._ctx.dispatch,
        )
        try:
            res = last_cmd.rollback()
        except SdnError as err:
            _ui.write(
                self._state.output,
                f"✘  Falha durante o rollback: {err}",
                self._ctx.dispatch,
            )
            return

        _ui.write(self._state.output, res.message, self._ctx.dispatch)
        self._ctx.event_bus.put(
            Event(
                EventType.CONFIG_CHANGED,
                source="basic_config",
                payload=CommandExecutedPayload(
                    command="basic-config-rollback",
                    data={"status": res.status, "rollback": True},
                ),
            )
        )
