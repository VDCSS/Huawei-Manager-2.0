"""Parametrização tipada e renderização de blocos de configuração VRP.

O catálogo legado usava ``ServiceDef.description`` como comando executável e
substituía placeholders posicionalmente. Isso aceitava ``\\r``/``\\n`` e
valores semanticamente inválidos dentro de um template permissivo (``.+``).
Aqui cada campo tem tipo, faixa e charset explícitos; o resultado é um bloco
de linhas já normalizado, sem separadores de comando escondidos.

Formato dos templates:
* ``{chave}`` — placeholder obrigatório (normalizado por ``ParamSpec``);
* ``[[texto {chave}]]`` — trecho opcional removido quando todos os
  placeholders internos estiverem vazios.

O renderizador nunca devolve linha vazia, com caractere de controle ou com
``;``/``\\r``/``\\n``. Qualquer anomalia vira ``SdnValidationError`` — a
operação inteira é abortada (fail-closed).
"""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from huawei_manager.exceptions import SdnValidationError

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_COMMAND_SEPARATORS = re.compile(r"[;\r\n]")
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_OPTIONAL_BLOCK = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)

# Interface names aceitos em comandos VRP. Cobre as famílias usadas pelos
# equipamentos suportados (AR/S/NE) sem aceitar espaços ou metacaracteres.
_INTERFACE_RE = re.compile(
    r"^(?:"
    r"Ethernet|GigabitEthernet|GE|MultiGE|Multi-GE|XGigabitEthernet|XGE|"
    r"Eth-Trunk|Vlanif|LoopBack|Tunnel|Serial|POS|40GE|100GE|10GE|25GE"
    r")\d+(?:/\d+){0,3}(?:\.\d+)?$",
    re.IGNORECASE,
)
_HOSTNAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,62}[A-Za-z0-9])?$"
)
_USERNAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,62}[A-Za-z0-9])?$"
)
# Senha administrativa: sem espaços, aspas, barra invertida, ';' ou '|'.
# Os demais caracteres são aceitos para não reduzir a entropia do operador.
_PASSWORD_RE = re.compile(r"^[A-Za-z0-9!@#$%^&*_+\-=.,:?/]{12,64}$")
_VTY_RANGE_RE = re.compile(r"^\d+(?:\s+\d+)?$")


class ParamKind(StrEnum):
    """Tipo semântico de um parâmetro de configuração."""

    TEXT = "text"
    HOSTNAME = "hostname"
    USERNAME = "username"
    PASSWORD = "password"
    IPV4 = "ipv4"
    MASK = "mask"
    WILDCARD = "wildcard"
    INTERFACE = "interface"
    ACL_ID = "acl_id"
    RULE_ID = "rule_id"
    VLAN_ID = "vlan_id"
    PORT = "port"
    INT = "int"
    ENUM = "enum"
    VTY_RANGE = "vty_range"


@dataclass(frozen=True)
class ParamSpec:
    """Especificação de um campo de configuração.

    ``default`` é apenas o valor inicial exibido na UI; serviços de bloco
    usam ``default=""`` e ``required=True`` para forçar preenchimento
    consciente. ``secret=True`` indica que o valor jamais pode ser exibido
    em preview/auditoria/log.
    """

    key: str
    label: str
    kind: ParamKind
    default: str = ""
    required: bool = True
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    max_len: int = 64
    secret: bool = False
    help: str = ""


def _fail(field: str, message: str) -> SdnValidationError:
    return SdnValidationError(f"Parâmetro '{field}' inválido: {message}")


def _as_int(spec: ParamSpec, value: str) -> int:
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise _fail(spec.label, "deve ser um número inteiro") from exc
    if spec.minimum is not None and parsed < spec.minimum:
        raise _fail(spec.label, f"mínimo {spec.minimum}")
    if spec.maximum is not None and parsed > spec.maximum:
        raise _fail(spec.label, f"máximo {spec.maximum}")
    return parsed


def _normalize_mask(spec: ParamSpec, value: str) -> str:
    raw = value.strip()
    if not raw:
        raise _fail(spec.label, "máscara vazia")
    try:
        if raw.startswith("/"):
            prefix = int(raw[1:])
        elif raw.isdigit():
            prefix = int(raw)
        else:
            addr = ipaddress.IPv4Address(raw)
            network = ipaddress.IPv4Network(f"0.0.0.0/{addr}")
            return str(network.netmask)
        if not 0 <= prefix <= 32:
            raise ValueError("prefixo fora de 0..32")
        network = ipaddress.IPv4Network(f"0.0.0.0/{prefix}")
        return str(network.netmask)
    except ValueError as exc:
        raise _fail(spec.label, "máscara IPv4 inválida (use 255.255.255.0 ou /24)") from exc


def _normalize_password(spec: ParamSpec, value: str) -> str:
    if _CONTROL_CHARS.search(value) or any(c.isspace() for c in value):
        raise _fail(spec.label, "não pode conter espaços ou caracteres de controle")
    if not _PASSWORD_RE.fullmatch(value):
        raise _fail(
            spec.label,
            "use 12–64 caracteres ASCII sem aspas, barra invertida, ';' ou '|'",
        )
    return value


def validate_value(spec: ParamSpec, raw: str | None) -> str:
    """Valida e normaliza um valor; levanta ``SdnValidationError`` se inválido.

    Valores vazios são aceitos apenas quando ``required=False``. O retorno é
    sempre a forma canônica que entra no bloco de configuração.
    """
    value = "" if raw is None else str(raw).strip()
    if not value:
        if spec.required:
            raise _fail(spec.label, "obrigatório")
        return ""
    if _CONTROL_CHARS.search(value):
        raise _fail(spec.label, "contém caractere de controle")
    if len(value) > spec.max_len:
        raise _fail(spec.label, f"excede {spec.max_len} caracteres")

    match spec.kind:
        case ParamKind.IPV4:
            try:
                return str(ipaddress.IPv4Address(value))
            except ValueError as exc:
                raise _fail(spec.label, "endereço IPv4 inválido") from exc
        case ParamKind.WILDCARD:
            try:
                return str(ipaddress.IPv4Address(value))
            except ValueError as exc:
                raise _fail(spec.label, "wildcard IPv4 inválido") from exc
        case ParamKind.MASK:
            return _normalize_mask(spec, value)
        case ParamKind.INTERFACE:
            if not _INTERFACE_RE.fullmatch(value):
                raise _fail(
                    spec.label,
                    "interface inválida (ex.: GigabitEthernet0/0/0, Vlanif10)",
                )
            return value
        case ParamKind.ACL_ID:
            parsed = _as_int(spec, value)
            if not 2000 <= parsed <= 3999:
                raise _fail(spec.label, "ACL numérica deve estar em 2000–3999")
            return str(parsed)
        case ParamKind.RULE_ID:
            return str(_as_int(spec, value))
        case ParamKind.VLAN_ID:
            return str(_as_int(spec, value))
        case ParamKind.PORT:
            return str(_as_int(spec, value))
        case ParamKind.INT:
            return str(_as_int(spec, value))
        case ParamKind.ENUM:
            lowered = value.lower()
            choices = tuple(c.lower() for c in spec.choices)
            if not choices or lowered not in choices:
                raise _fail(spec.label, f"valor deve ser um de: {', '.join(spec.choices)}")
            return lowered
        case ParamKind.HOSTNAME:
            if not _HOSTNAME_RE.fullmatch(value):
                raise _fail(spec.label, "hostname inválido (letras, números, '.', '_' e '-')")
            return value
        case ParamKind.USERNAME:
            if not _USERNAME_RE.fullmatch(value):
                raise _fail(spec.label, "usuário inválido (letras, números, '.', '_' e '-')")
            return value
        case ParamKind.PASSWORD:
            return _normalize_password(spec, value)
        case ParamKind.VTY_RANGE:
            if not _VTY_RANGE_RE.fullmatch(value):
                raise _fail(spec.label, "faixa VTY inválida (ex.: '0 4')")
            for part in value.split():
                if not 0 <= int(part) <= 15:
                    raise _fail(spec.label, "faixa VTY deve estar em 0–15")
            return " ".join(value.split())
        case ParamKind.TEXT:
            if _COMMAND_SEPARATORS.search(value):
                raise _fail(spec.label, "não pode conter ';', quebra de linha ou CR")
            if any(c in value for c in "`$(){}"):
                raise _fail(spec.label, "contém caractere reservado de comando")
            return value
        case _:  # pragma: no cover - enum exaustivo, defesa para evolução
            raise _fail(spec.label, f"tipo desconhecido: {spec.kind}")


def normalize_values(
    specs: Sequence[ParamSpec], values: Mapping[str, str | None]
) -> dict[str, str]:
    """Valida todos os campos e devolve um mapa ``key -> valor canônico``."""
    known = {spec.key for spec in specs}
    unknown = set(values) - known
    if unknown:
        raise SdnValidationError(
            f"Parâmetro(s) desconhecido(s): {', '.join(sorted(unknown))}"
        )
    normalized: dict[str, str] = {}
    for spec in specs:
        normalized[spec.key] = validate_value(spec, values.get(spec.key, spec.default))
    return normalized


@dataclass(frozen=True)
class ConfigTemplate:
    """Bloco de configuração hierárquico com placeholders tipados."""

    lines: tuple[str, ...]

    def render(
        self, specs: Sequence[ParamSpec], values: Mapping[str, str | None]
    ) -> list[str]:
        """Renderiza o bloco normalizado; aborta em qualquer anomalia."""
        normalized = normalize_values(specs, values)
        rendered: list[str] = []
        for raw_line in self.lines:
            line = _render_optional_blocks(raw_line, normalized)
            missing = [
                key for key in _PLACEHOLDER.findall(line)
                if key not in normalized
            ]
            if missing:
                raise SdnValidationError(
                    "Template de configuração contém placeholder não resolvido: "
                    + ", ".join(sorted(set(missing)))
                )
            line = _PLACEHOLDER.sub(
                lambda m: normalized[m.group(1)], line
            )
            if "{" in line or "}" in line:
                raise SdnValidationError(
                    "Template de configuração contém placeholder não resolvido"
                )
            line = line.strip()
            if not line:
                continue
            if _CONTROL_CHARS.search(line):
                raise SdnValidationError("Configuração gerada contém caractere de controle")
            if _COMMAND_SEPARATORS.search(line):
                raise SdnValidationError("Configuração gerada contém separador de comando")
            rendered.append(line)
        if not rendered:
            raise SdnValidationError("Configuração gerada está vazia")
        return rendered


def _render_optional_blocks(line: str, values: Mapping[str, str]) -> str:
    """Remove ``[[...]]`` cujos placeholders internos estejam vazios."""
    while True:
        match = _OPTIONAL_BLOCK.search(line)
        if match is None:
            return line
        block = match.group(1)
        keys = _PLACEHOLDER.findall(block)
        keep = bool(keys) and all(values.get(key, "") for key in keys)
        line = line[: match.start()] + (block if keep else "") + line[match.end() :]
