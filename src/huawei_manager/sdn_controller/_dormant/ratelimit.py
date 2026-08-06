"""Rate Limiter — per-device token bucket para operacoes de escrita.

Implementa algoritmo token bucket. Cada dispositivo tem seu proprio
bucket com taxa de recarga e burst configuraveis. Operacoes de leitura
(show/display) nao consomem tokens — apenas escrita (configure/commit).
"""
from __future__ import annotations


class TokenBucket:
    """Token bucket para um dispositivo.

    Controla a taxa de operacoes de escrita permitidas. Tokens sao
    adicionados a uma taxa fixa (rate tokens/sec) ate o limite maximo
    (burst). Cada operacao de escrita consome 1 token.

    Args:
        device_id: Identificador do dispositivo.
        rate: Tokens adicionados por segundo.
        burst: Capacidade maxima do bucket (tokens iniciais).
    """

    def __init__(
        self, device_id: str, rate: float, burst: float,
    ) -> None:
        self.device_id = device_id
        self.rate = rate
        self.max_tokens = burst
        self.tokens = burst

    def consume(self, tokens: float = 1.0) -> bool:
        """Tenta consumir tokens.

        Args:
            tokens: Quantidade de tokens a consumir (padrao 1).

        Returns:
            True se havia tokens suficientes, False caso contrario.
        """
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def refill(self, elapsed: float = 1.0) -> None:
        """Recarrega tokens baseado no tempo decorrido.

        Args:
            elapsed: Segundos desde a ultima recarga.
        """
        self.tokens = min(
            self.max_tokens,
            self.tokens + (self.rate * elapsed),
        )

    def reset(self) -> None:
        """Restaura o bucket a capacidade maxima."""
        self.tokens = self.max_tokens

    def __str__(self) -> str:
        return (
            f"TokenBucket({self.device_id}, "
            f"{self.tokens:.1f}/{self.max_tokens:.0f}, "
            f"rate={self.rate}/s)"
        )


class RateLimiter:
    """Gerenciador de rate limiting multi-dispositivo.

    Mantem um TokenBucket por device. Operacoes de leitura sao sempre
    permitidas; operacoes de escrita consomem tokens.

    Args:
        default_rate: Taxa padrao de recarga (tokens/sec).
        default_burst: Burst padrao (max tokens).
    """

    def __init__(
        self,
        default_rate: float = 10.0,
        default_burst: float = 20.0,
    ) -> None:
        self.default_rate = default_rate
        self.default_burst = default_burst
        self._buckets: dict[str, TokenBucket] = {}

    def get_bucket(self, device_id: str) -> TokenBucket:
        """Retorna ou cria um bucket para o dispositivo.

        Args:
            device_id: Identificador do dispositivo.

        Returns:
            ``TokenBucket`` do dispositivo.
        """
        if device_id not in self._buckets:
            self._buckets[device_id] = TokenBucket(
                device_id=device_id,
                rate=self.default_rate,
                burst=self.default_burst,
            )
        return self._buckets[device_id]

    def check(
        self, device_id: str, tokens: float = 1.0,
        is_write: bool = True,
    ) -> bool:
        """Verifica se uma operacao pode prosseguir.

        Args:
            device_id: Identificador do dispositivo.
            tokens: Quantidade de tokens a consumir.
            is_write: Se True (escrita), consome tokens.
                Se False (leitura), sempre permitido.

        Returns:
            True se permitido, False se rate limited.
        """
        bucket = self.get_bucket(device_id)

        if not is_write:
            return True

        return bucket.consume(tokens)

    def reset(self, device_id: str) -> None:
        """Restaura o bucket de um dispositivo a capacidade maxima."""
        bucket = self.get_bucket(device_id)
        bucket.reset()

    def reset_all(self) -> None:
        """Restaura todos os buckets a capacidade maxima."""
        for bucket in self._buckets.values():
            bucket.reset()

    def __str__(self) -> str:
        return (
            f"RateLimiter({len(self._buckets)} devices, "
            f"rate={self.default_rate}/s, "
            f"burst={self.default_burst})"
        )
