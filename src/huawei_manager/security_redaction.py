"""Redação de segredos em comandos, saídas e blocos de configuração VRP."""
from __future__ import annotations

import re
from collections.abc import Iterable

_CFG_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(\blocal-user\s+\S+\s+password)\s+"
        r"(?:irreversible-cipher|cipher|simple)\s+\S+"
    ),
    re.compile(
        r"(?i)(\bset\s+authentication\s+password)\s+"
        r"(?:cipher|simple)\s+\S+"
    ),
    re.compile(
        r"(?i)(\b(?:password|secret|key|token|auth))\s+"
        r"(?:irreversible-cipher|cipher|simple)\s+\S+"
    ),
)

# Formas curtas (`password 'x'`, `password=x`, `token: y`) usadas em logs.
_GENERIC_SECRET = re.compile(
    r"(?i)(password|passwd|secret|key|token|auth)"
    r"(?:\s*[=:]\s*\S+|\s+['\"]?\S+['\"]?)"
)
_REDACTED = "[REDACTED]"


def redact_vrp_config(text: str) -> str:
    """Redige apenas as formas de senha específicas de configuração VRP."""
    result = text
    for pattern in _CFG_SECRET_PATTERNS:
        result = pattern.sub(lambda m: f"{m.group(1)} {_REDACTED}", result)
    return result


def redact_config_text(text: str) -> str:
    """Redige segredos de configuração VRP preservando o restante da linha.

    Cobre ``local-user <u> password irreversible-cipher <p>``,
    ``set authentication password cipher <p>`` e formas curtas
    ``password cipher|simple <p>``. Nunca deve ser usado para *executar*:
    é uma função de exibição/log/auditoria.
    """
    return _GENERIC_SECRET.sub(
        lambda m: f"{m.group(1)} {_REDACTED}",
        redact_vrp_config(text),
    )


def redact_secrets(text: str, secrets: Iterable[str] | None) -> str:
    """Redige valores secretos conhecidos e, depois, padrões genéricos.

    ``secrets`` é qualquer iterável de strings; valores vazios são ignorados.
    A substituição por valor exato é a defesa mais forte contra eco do device
    (ex.: senha repetida em mensagem de erro ou saída de ``display``).
    """
    result = text
    if secrets:
        values = sorted({str(s) for s in secrets if str(s)}, key=len, reverse=True)
        for value in values:
            result = result.replace(value, _REDACTED)
    return redact_config_text(result)
