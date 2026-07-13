"""Policy Engine — condition-action rules with priority, JSON persistence, audit.

Engine de regras (if/elif) para acoes automatizadas. Gatilhos por
polling ou evento. Regras serializaveis em JSON. Loop prevention.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyRule:
    """Uma regra condicao → acao.

    Attributes:
        id: Identificador unico da regra.
        name: Nome legivel para display.
        condition: Callable sem argumentos que retorna bool (ou None).
        action: Callable sem argumentos para executar se condicao True.
        priority: Menor numero = maior prioridade (executa primeiro).
        enabled: Se False, a regra e pulada no evaluate().
    """

    id: str
    name: str
    condition: Callable[[], bool | None]
    action: Callable[[], Any]
    priority: int = 10
    enabled: bool = True

    def __str__(self) -> str:
        return f"PolicyRule({self.id}, {self.name}, p={self.priority})"


class PolicyEngine:
    """Engine de regras condicao → acao.

    Avalia todas as regras em ordem de prioridade. Se a condicao
    retornar True, executa a acao correspondente.

    Args:
        name: Nome opcional do engine (para logging).
    """

    def __init__(self, name: str = "default") -> None:
        self._name = name
        self._rules: dict[str, PolicyRule] = {}
        self._evaluating = False
        self._audit_logger: Any = None

    # ── Audit ───────────────────────────────────────────────────────────

    def set_audit_logger(self, logger: Any) -> None:
        """Define o logger de auditoria."""
        self._audit_logger = logger

    # ── Rule management ──────────────────────────────────────────────────

    def add_rule(self, rule: PolicyRule) -> None:
        """Adiciona uma regra.

        Raises:
            ValueError: Se ja existir regra com o mesmo ``id``.
        """
        if rule.id in self._rules:
            msg = f"Rule '{rule.id}' already exists"
            raise ValueError(msg)
        self._rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> None:
        """Remove uma regra pelo id.

        Raises:
            KeyError: Se a regra nao existir.
        """
        if rule_id not in self._rules:
            msg = f"Rule '{rule_id}' not found"
            raise KeyError(msg)
        del self._rules[rule_id]

    def list_rules(self) -> list[str]:
        """Retorna lista de ids de regras registradas."""
        return list(self._rules.keys())

    def clear_rules(self) -> None:
        """Remove todas as regras."""
        self._rules.clear()

    # ── Evaluate ────────────────────────────────────────────────────────

    def evaluate(self) -> list[dict[str, Any]]:
        """Avalia todas as regras habilitadas em ordem de prioridade.

        Returns:
            Lista de dicts com resultado de cada regra avaliada:
            ``rule_id``, ``triggered``, ``error`` (opcional).

        Raises:
            RuntimeError: Se chamado dentro de outro evaluate()
                (loop prevention).
        """
        if self._evaluating:
            msg = "Re-entrant evaluate() call detected — loop prevention"
            raise RuntimeError(msg)

        self._evaluating = True
        try:
            return self._evaluate_all()
        finally:
            self._evaluating = False

    def _evaluate_all(self) -> list[dict[str, Any]]:
        """Loop interno de avaliacao."""
        sorted_rules = sorted(
            (r for r in self._rules.values() if r.enabled),
            key=lambda r: r.priority,
        )
        results: list[dict[str, Any]] = []

        for rule in sorted_rules:
            result: dict[str, Any] = {"rule_id": rule.id, "triggered": False}

            try:
                cond = rule.condition()
                if cond:
                    rule.action()
                    result["triggered"] = True
                    self._log_triggered(rule)
            except Exception as e:
                result["error"] = str(e)

            results.append(result)

        return results

    def _log_triggered(self, rule: PolicyRule) -> None:
        """Registra a acao no audit log, se configurado."""
        if self._audit_logger is not None:
            self._audit_logger.log_operation(
                "policy_triggered",
                "engine",
                self._name,
                details=f"Rule '{rule.id}': {rule.name}",
            )

    # ── JSON serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serializa as regras para dict (sem callables).

        Nota: Callables nao sao serializaveis. Este metodo exporta
        apenas metadados. Use ``condition_type`` / ``action_type``
        para identificar os callables ao carregar.
        """
        data: dict[str, Any] = {}
        for rid, rule in self._rules.items():
            data[rid] = {
                "name": rule.name,
                "condition_type": "always",
                "action_type": "callback",
                "priority": rule.priority,
                "enabled": rule.enabled,
            }
        return data

    def load_rules_from_dict(
        self,
        data: dict[str, Any],
        action_map: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        """Carrega regras de um dict.

        Args:
            data: Dict no formato exportado por ``to_dict()``.
            action_map: Mapeamento de action_type → callable.
        """
        action_map = action_map or {}
        for rid, info in data.items():
            action = action_map.get(info.get("action_type", "callback"))
            if action is None:
                action = _noop
            rule = PolicyRule(
                id=rid,
                name=info.get("name", rid),
                condition=_always_true,
                action=action,
                priority=info.get("priority", 10),
                enabled=info.get("enabled", True),
            )
            self._rules[rid] = rule

    def save_json(self, path: str) -> None:
        """Salva as regras em um arquivo JSON."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def load_json(
        self,
        path: str,
        action_map: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        """Carrega regras de um arquivo JSON."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.load_rules_from_dict(data, action_map)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _always_true() -> bool:
    return True


def _noop() -> None:
    return None
