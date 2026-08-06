"""Security Event Timeline — coleta, categorizacao e filtros.

Gerencia eventos de seguranca com categorias, severidades, filtros
por device/operador e suporte a acknowledge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Severidades ordenadas (mais critica primeiro)
_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

@dataclass
class SecurityEvent:
    """Um evento de seguranca na timeline.

    Attributes:
        timestamp: Momento do evento.
        category: Categoria (auth, config, policy, system, network).
        severity: Severidade (critical, high, medium, low, info).
        device: Dispositivo envolvido.
        operator: Operador que realizou a acao.
        description: Descricao do evento.
        event_id: Identificador unico (auto-gerado se omitido).
        acknowledged: Se o evento foi reconhecido/dismissed.
    """

    timestamp: datetime
    category: str
    severity: str
    device: str
    operator: str
    description: str
    event_id: str = ""
    acknowledged: bool = False

    _id_counter: int = 0

    def __post_init__(self) -> None:
        if not self.event_id:
            SecurityEvent._id_counter += 1
            object.__setattr__(
                self, "event_id",
                f"evt-{SecurityEvent._id_counter:04d}",
            )

    @property
    def is_critical(self) -> bool:
        """True se a severidade for critical."""
        return self.severity == "critical"

    @property
    def id(self) -> str:
        """Alias para event_id."""
        return self.event_id


def _severity_index(severity: str) -> int:
    """Retorna indice numerico da severidade (0=critical, 4=info)."""
    try:
        return _SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(_SEVERITY_ORDER)


class SecurityTimeline:
    """Timeline de eventos de seguranca com suporte a filtros.

    Eventos sao armazenados em ordem cronologica reversa
    (mais recentes primeiro).
    """

    def __init__(self) -> None:
        self._events: dict[str, SecurityEvent] = {}

    # ── Add ─────────────────────────────────────────────────────────────

    def add_event(self, event: SecurityEvent) -> None:
        """Adiciona um evento a timeline.

        Se ja existir evento com o mesmo ID, sobrescreve.
        """
        self._events[event.id] = event

    # ── Get ─────────────────────────────────────────────────────────────

    def get_events(
        self,
        category: str | None = None,
        severity: str | None = None,
        min_severity: str | None = None,
        device: str | None = None,
        operator: str | None = None,
    ) -> list[SecurityEvent]:
        """Retorna eventos filtrados, ordenados do mais recente.

        Args:
            category: Filtra por categoria exata.
            severity: Filtra por severidade exata.
            min_severity: Severidade minima (inclui mais criticas).
            device: Filtra por dispositivo.
            operator: Filtra por operador.

        Returns:
            Lista de ``SecurityEvent`` ordenada (newest first).
        """
        result = list(self._events.values())

        if category is not None:
            result = [e for e in result if e.category == category]
        if severity is not None:
            result = [e for e in result if e.severity == severity]
        if min_severity is not None:
            min_idx = _severity_index(min_severity)
            result = [
                e for e in result
                if _severity_index(e.severity) <= min_idx
            ]
        if device is not None:
            result = [e for e in result if e.device == device]
        if operator is not None:
            result = [e for e in result if e.operator == operator]

        result.sort(key=lambda e: e.timestamp, reverse=True)
        return result

    def get_event(self, event_id: str) -> SecurityEvent | None:
        """Retorna um evento pelo ID."""
        return self._events.get(event_id)

    # ── Categories / Severities ─────────────────────────────────────────

    def get_categories(self) -> list[str]:
        """Retorna lista de categorias presentes."""
        cats: set[str] = set()
        for ev in self._events.values():
            cats.add(ev.category)
        return sorted(cats)

    def get_severities(self) -> list[str]:
        """Retorna lista de severidades presentes."""
        sevs: set[str] = set()
        for ev in self._events.values():
            sevs.add(ev.severity)
        return sorted(sevs, key=_severity_index)

    # ── Acknowledge ────────────────────────────────────────────────────

    def acknowledge(self, event_id: str) -> bool:
        """Marca um evento como acknowledged.

        Returns:
            True se o evento foi encontrado e atualizado.
        """
        ev = self._events.get(event_id)
        if ev is None:
            return False
        ev.acknowledged = True
        return True

    def unacknowledged_count(self) -> int:
        """Retorna quantos eventos nao foram acknowledged."""
        return sum(
            1 for ev in self._events.values()
            if not ev.acknowledged
        )

    # ── Clear ──────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove todos os eventos."""
        self._events.clear()
