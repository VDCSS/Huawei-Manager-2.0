"""Modelos de dados tipados para a configuração básica de dispositivos (VRP)."""
from __future__ import annotations

from dataclasses import dataclass

from huawei_manager.basic_config.vrp_version import VrpVersion


@dataclass(frozen=True)
class HostnameConfig:
    hostname: str


@dataclass(frozen=True)
class InterfaceL3Config:
    interface: str
    ip: str
    mask: str
    description: str = ""
    shutdown: bool = False
    undo_portswitch: bool = False
    is_switch: bool = False


@dataclass(frozen=True)
class L2AccessConfig:
    vlan_id: str
    interface: str
    ip: str
    mask: str
    vlan_description: str = ""
    interface_description: str = ""
    vlanif_description: str = ""


@dataclass(frozen=True)
class SshConfig:
    username: str
    password: str
    vty_range: str = "0 4"


@dataclass(frozen=True)
class AdminUserConfig:
    username: str
    password: str
    privilege: str = "15"


@dataclass(frozen=True)
class BasicConfigPlan:
    """Plano consolidado com todos os blocos configurados."""

    hostname: HostnameConfig | None = None
    interface_l3: InterfaceL3Config | None = None
    l2_access: L2AccessConfig | None = None
    ssh: SshConfig | None = None
    admin_user: AdminUserConfig | None = None

    def is_empty(self) -> bool:
        return (
            self.hostname is None
            and self.interface_l3 is None
            and self.l2_access is None
            and self.ssh is None
            and self.admin_user is None
        )

    def collect_secrets(self) -> list[str]:
        secrets: list[str] = []
        if self.ssh is not None and self.ssh.password:
            secrets.append(self.ssh.password)
        if self.admin_user is not None and self.admin_user.password:
            secrets.append(self.admin_user.password)
        return secrets

    def build_lines(
        self,
        vrp_version: VrpVersion = VrpVersion.UNKNOWN,
    ) -> list[str]:
        """Gera a sequência hierárquica completa de comandos VRP.

        A sintaxe varia entre versões principais da VRP (VRP5 vs VRP8):
        * ``local-user ... password``: VRP5 não aceita ``irreversible-cipher``
          em todos os modelos; usa ``simple`` ou ``cipher``. VRP8 aceita
          ``irreversible-cipher``.
        * ``undo portswitch``: disponível apenas em portas L3 de switch em
          versões mais recentes (VRP8); em VRP5 a porta já é L3 por padrão
          e o comando é rejeitado.
        * ``ssh user ... authentication-type``: sintaxe pode diferir entre
          versões; em caso de UNKNOWN o bloco usa a sintaxe VRP8 (mais
          restritiva) e o operador é avisado na prévia.
        """
        from huawei_manager.basic_config.builders import (
            ADMIN_USER_SPECS,
            ADMIN_USER_TEMPLATE,
            ADMIN_USER_TEMPLATE_VRP5,
            HOSTNAME_SPECS,
            HOSTNAME_TEMPLATE,
            INTERFACE_L3_SPECS,
            INTERFACE_L3_TEMPLATE,
            L2_ACCESS_SPECS,
            L2_ACCESS_TEMPLATE,
            SSH_SPECS,
            SSH_TEMPLATE,
            SSH_TEMPLATE_VRP5,
        )

        lines: list[str] = []

        if self.hostname is not None:
            lines.extend(
                HOSTNAME_TEMPLATE.render(
                    HOSTNAME_SPECS, {"hostname": self.hostname.hostname}
                )
            )

        if self.interface_l3 is not None:
            vals = {
                "interface": self.interface_l3.interface,
                "ip": self.interface_l3.ip,
                "mask": self.interface_l3.mask,
                "description": self.interface_l3.description,
                "state": "shutdown" if self.interface_l3.shutdown else "undo shutdown",
                # undo portswitch só é válido em porta L3 de switch (VRP8+).
                # Em VRP5 a porta já é L3 por padrão; em roteadores o comando
                # não existe. Só envia se is_switch=True e versão VRP8.
                "portswitch": (
                    "undo portswitch"
                    if self.interface_l3.undo_portswitch
                    and self.interface_l3.is_switch
                    and vrp_version == VrpVersion.VRP8
                    else ""
                ),
            }
            lines.extend(INTERFACE_L3_TEMPLATE.render(INTERFACE_L3_SPECS, vals))

        if self.l2_access is not None:
            vals = {
                "vlan_id": self.l2_access.vlan_id,
                "interface": self.l2_access.interface,
                "ip": self.l2_access.ip,
                "mask": self.l2_access.mask,
                "vlan_description": self.l2_access.vlan_description,
                "interface_description": self.l2_access.interface_description,
                "vlanif_description": self.l2_access.vlanif_description,
            }
            lines.extend(L2_ACCESS_TEMPLATE.render(L2_ACCESS_SPECS, vals))

        if self.ssh is not None:
            vals = {
                "username": self.ssh.username,
                "password": self.ssh.password,
                "vty_range": self.ssh.vty_range,
            }
            ssh_template = SSH_TEMPLATE_VRP5 if vrp_version == VrpVersion.VRP5 else SSH_TEMPLATE
            lines.extend(ssh_template.render(SSH_SPECS, vals))

        if self.admin_user is not None:
            vals = {
                "username": self.admin_user.username,
                "password": self.admin_user.password,
                "privilege": self.admin_user.privilege,
            }
            admin_template = (
                ADMIN_USER_TEMPLATE_VRP5
                if vrp_version == VrpVersion.VRP5
                else ADMIN_USER_TEMPLATE
            )
            lines.extend(admin_template.render(ADMIN_USER_SPECS, vals))

        return lines

    def build_rollback_lines(
        self,
        vrp_version: VrpVersion = VrpVersion.UNKNOWN,
    ) -> list[str]:
        """Gera linhas inversas para desfazer as alterações pontuais."""
        lines: list[str] = []
        if self.interface_l3 is not None:
            lines.extend([
                f"interface {self.interface_l3.interface}",
                "undo ip address",
                "undo description",
                "quit",
            ])
        if self.l2_access is not None:
            lines.extend([
                f"undo interface Vlanif {self.l2_access.vlan_id}",
                f"undo vlan {self.l2_access.vlan_id}",
            ])
        if self.admin_user is not None:
            lines.extend([
                "aaa",
                f"undo local-user {self.admin_user.username}",
                "quit",
            ])
        return lines
