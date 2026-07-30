"""VnfService — Serviço de domínio para gestão de VNFs.

Sem dependência Qt. Sem dependência de sessão SSH ou event bus.
Retorna dados/diffs — o chamador decide como aplicar.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from huawei_manager.vnf_inventory import load_vnf_inventory, save_vnf_inventory
from huawei_manager.vnf_models import VNF
from huawei_manager.vnf_probe import probe_vnfs, simulate_status


@dataclass
class SessionOverrides:
    """Diferença a aplicar na sessão SSH.

    Apenas os campos preenchidos devem ser sobrescritos.
    None = não alterar.
    """
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    ssh_key: str | None = None


def _next_id(vnfs: list[VNF], name: str) -> str:
    """Gera um ID único incremental para um novo VNF."""
    slug = name.lower().replace(" ", "-")
    return f"vnf-{len(vnfs) + 1:03d}-{slug}"


log = logging.getLogger("huawei.vnf_service")


def _noop_resolver(key: str, default: str = "") -> str:
    """Resolver que não resolve nada — fallback seguro."""
    return default


class VnfService:
    """Serviço de domínio para gestão de VNFs.

    Responsabilidades:
    - CRUD de VNFs no inventário (load/save/add/update/delete)
    - Probe ou simulação de status
    - Cálculo de SessionOverrides para seleção de alvo

    Args:
        inventory_path: Caminho para o arquivo JSON de inventário.
        resolve_env: Callable que resolve nome de var de ambiente → valor.
            Ex: ``lambda k: os.environ.get(k, "")`` ou ``_config._s``.
            Se None, ``password_env`` não é resolvido (vazio = sem senha).
    """

    def __init__(
        self,
        inventory_path: str,
        resolve_env: Callable[[str], str] | None = None,
    ) -> None:
        self._inventory_path = inventory_path
        self._resolve_env = resolve_env or _noop_resolver

    # ── CRUD ─────────────────────────────────────────────────────────

    def load_inventory(self) -> list[VNF]:
        """Carrega a lista de VNFs do inventário e resolve ``password_env``.

        Se um VNF tiver ``password_env`` preenchido (ex: ``"ROUTER_PASSWORD"``),
        o valor real é lido do backend de secrets e atribuído a ``password``.
        ``password`` explícito no JSON tem prioridade (override manual).
        """
        vnfs = load_vnf_inventory(self._inventory_path)
        for vnf in vnfs:
            if vnf.password_env and not vnf.password:
                try:
                    resolved = self._resolve_env(vnf.password_env)
                except Exception:
                    log.exception(
                        "Falha ao resolver password_env '%s' para VNF %s",
                        vnf.password_env, vnf.name,
                    )
                    continue
                if resolved:
                    vnf.password = resolved
                    log.debug(
                        "VNF %s: password_env '%s' resolvido",
                        vnf.name, vnf.password_env,
                    )
                else:
                    log.warning(
                        "VNF %s: password_env '%s' retornou vazio",
                        vnf.name, vnf.password_env,
                    )
        return vnfs

    def save_inventory(self, vnfs: list[VNF]) -> None:
        """Persiste a lista de VNFs no arquivo de inventário.

        Se ``password_env`` está preenchido, ``password`` é limpo antes
        de gravar para não persistir o segredo resolvido em disco.
        """
        for vnf in vnfs:
            if vnf.password_env:
                vnf.password = ""
        save_vnf_inventory(vnfs, self._inventory_path)

    def add_device(self, data: dict[str, Any]) -> VNF:
        """Valida dados e adiciona um novo VNF.

        Args:
            data: Dicionário com campos do VNF (name, host, ...).

        Returns:
            O VNF criado.

        Raises:
            ValueError: Se ``name`` ou ``host`` estiverem vazios.
        """
        name = str(data.get("name", "")).strip()
        host = str(data.get("host", "")).strip()
        if not name:
            raise ValueError("Nome é obrigatório.")
        if not host:
            raise ValueError("IP/Host é obrigatório.")
        port = int(data.get("port", 22))
        if not (1 <= port <= 65535):
            raise ValueError("Porta deve estar entre 1 e 65535.")

        vnfs = self.load_inventory()
        vnf = VNF(
            id=_next_id(vnfs, name),
            name=name,
            host=host,
            port=port,
            type=str(data.get("type", "ROUTER")),
            username=str(data.get("username", "")),
            password=str(data.get("password", "")),
            password_env=str(data.get("password_env", "")),
            ssh_key=str(data.get("ssh_key", "")),
            location=str(data.get("location", "")),
        )
        vnfs.append(vnf)
        self.save_inventory(vnfs)
        return vnf

    def update_device(self, vnf: VNF, data: dict[str, Any]) -> VNF:
        """Atualiza campos de um VNF existente.

        Args:
            vnf: VNF a ser atualizado (referência copiada).
            data: Dicionário com campos a atualizar.

        Returns:
            O VNF com os campos atualizados.
        """
        name = str(data.get("name", vnf.name)).strip()
        host = str(data.get("host", vnf.host)).strip()
        port = int(data.get("port", vnf.port))
        if not (1 <= port <= 65535):
            port = vnf.port

        updated = VNF(
            id=vnf.id,
            name=name,
            host=host,
            port=port,
            type=str(data.get("type", vnf.type)),
            username=str(data.get("username", vnf.username)),
            password=str(data.get("password", vnf.password)),
            password_env=str(data.get("password_env", vnf.password_env)),
            ssh_key=str(data.get("ssh_key", vnf.ssh_key)),
            location=str(data.get("location", vnf.location)),
        )

        vnfs = self.load_inventory()
        for i, v in enumerate(vnfs):
            if v.id == vnf.id:
                vnfs[i] = updated
                break
        self.save_inventory(vnfs)
        return updated

    def delete_device(
        self, vnf_id: str, vnfs: list[VNF]
    ) -> tuple[list[VNF], VNF | None]:
        """Remove um VNF da lista pelo ID.

        Args:
            vnf_id: ID do VNF a remover.
            vnfs: Lista atual de VNFs.

        Returns:
            Tupla (lista_atualizada, vnf_removido_ou_None).
        """
        removed: VNF | None = None
        remaining: list[VNF] = []
        for v in vnfs:
            if v.id == vnf_id:
                removed = v
            else:
                remaining.append(v)
        self.save_inventory(remaining)
        return remaining, removed

    # ── Probe ────────────────────────────────────────────────────────

    def probe_or_simulate(self, vnfs: list[VNF], mock_mode: bool) -> list[VNF]:
        """Faz probe TCP real ou simulação de status.

        Args:
            vnfs: Lista de VNFs a verificar.
            mock_mode: Se True, usa simulação; caso contrário, probe real.

        Returns:
            Lista de VNFs com status atualizado.
        """
        if mock_mode:
            return simulate_status(vnfs)
        return probe_vnfs(vnfs)

    # ── Target ───────────────────────────────────────────────────────

    def set_target(self, vnf: VNF) -> SessionOverrides:
        """Calcula os overrides de sessão para um VNF alvo.

        Returns:
            SessionOverrides com os campos do VNF.
        """
        return SessionOverrides(
            host=vnf.host or None,
            port=vnf.port or None,
            username=vnf.username or None,
            password=vnf.password or None,
            ssh_key=vnf.ssh_key or None,
        )

    @staticmethod
    def clear_target() -> SessionOverrides:
        """Retorna overrides vazios (todos None).

        O chamador deve aplicar estes overrides para limpar a sessão.
        """
        return SessionOverrides()
