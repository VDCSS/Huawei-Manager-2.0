"""Service Orchestrator — Traducao de intent em comandos multi-dispositivo.

Converte uma intent (servico + parametros + dispositivos-alvo) em um
plano de execucao, verifica estado dos dispositivos, e executa via
funcao injetada ``execute_fn``.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from huawei_manager.sdn_controller.core import ControllerCore
from huawei_manager.services import get_service_by_id
from huawei_manager.services_data import ServiceDef

# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class ExecutionStep:
    """Um passo do plano: comando(s) para um unico dispositivo.

    Attributes:
        device_id: Identificador do dispositivo alvo.
        commands: Lista de comandos CLI a executar.
        params: Parametros resolvidos usados na traducao.
    """

    device_id: str
    commands: list[str]
    params: dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Plano completo de execucao multi-dispositivo.

    Attributes:
        steps: Lista de passos (um por dispositivo).
        service_id: Identificador do servico a executar.
    """

    steps: list[ExecutionStep]
    service_id: str


@dataclass
class ExecutionResult:
    """Resultado da execucao de um passo.

    Attributes:
        device_id: Dispositivo onde o comando foi executado.
        success: True se a execucao foi bem-sucedida.
        output: Saida do comando (vazio se erro).
        error: Mensagem de erro (None se success=True).
    """

    device_id: str
    success: bool
    output: str = ""
    error: str | None = None


# ── Orchestrator ─────────────────────────────────────────────────────────────


class ServiceOrchestrator:
    """Tradutor de intent para comandos CLI multi-dispositivo.

    Args:
        controller: Instancia de ``ControllerCore`` para consultar
            estado dos dispositivos.
        execute_fn: Funcao ``(device_id: str, commands: list[str]) ->
            tuple[str, str]`` que executa comandos e retorna
            ``(output, error)``. Padrao: executa local (mock).
    """

    def __init__(
        self,
        controller: ControllerCore,
        execute_fn: Callable[[str, list[str]], tuple[str, str]] | None = None,
    ) -> None:
        self._controller = controller
        self._execute_fn = execute_fn or self._default_execute

    @staticmethod
    def _default_execute(
        device_id: str, commands: list[str]
    ) -> tuple[str, str]:
        """Execucao padrao (mock) — retorna comandos sem executar."""
        output = "\n".join(commands)
        return output, ""

    # ── Lookup ──────────────────────────────────────────────────────────

    @staticmethod
    def lookup(service_id: str) -> ServiceDef | None:
        """Busca um servico pelo ID no catalogo.

        Returns:
            ``ServiceDef`` ou None se nao encontrado.
        """
        return get_service_by_id(service_id)

    # ── Resolve ─────────────────────────────────────────────────────────

    def resolve(
        self,
        service_id: str,
        params: dict[str, str] | None = None,
    ) -> list[str]:
        """Traduz intent em comandos CLI.

        Args:
            service_id: Identificador do servico no catalogo.
            params: Parametros para substituir placeholders ``<param>``.

        Returns:
            Lista de comandos CLI resolvidos.

        Raises:
            ValueError: Se o servico nao for encontrado.
        """
        svc = self.lookup(service_id)
        if svc is None:
            raise ValueError(f"Service not found: {service_id}")

        commands = list(svc.cli_commands)
        if not commands:
            commands = [svc.description]

        if params:
            commands = [
                self._substitute_params(cmd, params) for cmd in commands
            ]

        return commands

    @staticmethod
    def _substitute_params(cmd: str, params: dict[str, str]) -> str:
        """Substitui placeholders ``<param>`` no comando."""
        def replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            return params.get(key, match.group(0))
        return re.sub(r"<([^>]+)>", replacer, cmd)

    # ── Build plan ──────────────────────────────────────────────────────

    def build_plan(
        self,
        service_id: str,
        target_devices: list[str],
        params: dict[str, str] | None = None,
    ) -> ExecutionPlan:
        """Constroi um plano de execucao.

        Verifica se cada dispositivo existe, esta online, e e compativel
        com o tipo do servico.

        Args:
            service_id: Identificador do servico.
            target_devices: Lista de IDs dos dispositivos alvo.
            params: Parametros opcionais.

        Returns:
            ``ExecutionPlan`` com um passo por dispositivo.

        Raises:
            ValueError: Se servico nao encontrado, dispositivo nao
                registrado, offline, ou tipo incompativel.
        """
        svc = self.lookup(service_id)
        if svc is None:
            raise ValueError(f"Service not found: {service_id}")

        commands = self.resolve(service_id, params)
        steps: list[ExecutionStep] = []

        for dev_id in target_devices:
            state = self._controller.get_state(dev_id)
            if state is None:
                raise ValueError(f"Device not registered: {dev_id}")

            if state.status == "offline":
                raise ValueError(f"Device offline: {dev_id}")

            if state.device_type.upper() not in [
                t.upper() for t in svc.device_types
            ]:
                raise ValueError(
                    f"Device type incompatible: {dev_id} "
                    f"({state.device_type} for {svc.device_types})"
                )

            steps.append(
                ExecutionStep(
                    device_id=dev_id,
                    commands=list(commands),
                    params=params or {},
                )
            )

        return ExecutionPlan(steps=steps, service_id=service_id)

    # ── Execute ─────────────────────────────────────────────────────────

    def execute(
        self, plan: ExecutionPlan
    ) -> list[ExecutionResult]:
        """Executa um plano e retorna resultados.

        Args:
            plan: Plano de execucao.

        Returns:
            Lista de ``ExecutionResult``, um por passo.
        """
        results: list[ExecutionResult] = []
        for step in plan.steps:
            try:
                output, error = self._execute_fn(
                    step.device_id, step.commands
                )
                if error:
                    results.append(
                        ExecutionResult(
                            device_id=step.device_id,
                            success=False,
                            output=output,
                            error=error,
                        )
                    )
                else:
                    results.append(
                        ExecutionResult(
                            device_id=step.device_id,
                            success=True,
                            output=output,
                        )
                    )
            except Exception as e:
                results.append(
                    ExecutionResult(
                        device_id=step.device_id,
                        success=False,
                        output="",
                        error=str(e),
                    )
                )
        return results

    # ── Convenience ─────────────────────────────────────────────────────

    def execute_intent(
        self,
        service_id: str,
        target_devices: list[str],
        params: dict[str, str] | None = None,
    ) -> list[ExecutionResult]:
        """Conveniencia: resolve + build_plan + execute em uma chamada.

        Dispositivos offline ou com erro nao abortam os demais —
        cada um tem seu proprio ``ExecutionResult``.
        """
        svc = self.lookup(service_id)
        if svc is None:
            raise ValueError(f"Service not found: {service_id}")

        commands = self.resolve(service_id, params)
        results: list[ExecutionResult] = []

        for dev_id in target_devices:
            state = self._controller.get_state(dev_id)
            if state is None:
                results.append(
                    ExecutionResult(
                        device_id=dev_id,
                        success=False,
                        error=f"Device not registered: {dev_id}",
                    )
                )
                continue

            if state.status == "offline":
                results.append(
                    ExecutionResult(
                        device_id=dev_id,
                        success=False,
                        error=f"Device offline: {dev_id}",
                    )
                )
                continue

            try:
                output, error = self._execute_fn(dev_id, commands)
                results.append(
                    ExecutionResult(
                        device_id=dev_id,
                        success=not error,
                        output=output,
                        error=error or None,
                    )
                )
            except Exception as e:
                results.append(
                    ExecutionResult(
                        device_id=dev_id,
                        success=False,
                        error=str(e),
                    )
                )

        return results
