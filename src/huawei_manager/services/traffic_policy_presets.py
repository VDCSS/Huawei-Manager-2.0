"""Presets de traffic policy (classifier/behavior/policy + binding da ACL).

Núcleo **puro** (sem Qt, sem I/O de rede): guarda, por par
``device_key|flow``, os objetos VRP e o binding da ACL usados na policy de
tráfego. O arquivo é separado de ``acl_presets.json`` — o preset de ACL
genérico de "bloquear internet" e a policy completa de um fluxo são
conceitos distintos e não podem sobrescrever um ao outro.

Contrato:

* um preset é por **device e fluxo** (``internet``/``site`` coexistindo);
* escrita **atômica** (temporário + ``os.replace``) — nunca JSON pela metade;
* arquivo ausente → ``None``; JSON **corrompido** ou fora do schema →
  ``SdnValidationError`` (fail-closed, sem fallback silencioso);
* ``applied`` é apenas o cache do último estado conhecido (a fonte de
  verdade é o device); ``preexisting`` preserva o que já existia no device
  para que o rollback não apague configuração alheia.

A imagem VRP usada nos testes (NE40E, EVE-NG) não implementa
``traffic policy``; a persistência funciona em MOCK/offline — ver
``huawei_manager.services.traffic_policy`` para a aplicação no device.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import cast

from huawei_manager.basic_config.params import ParamKind, ParamSpec, validate_value
from huawei_manager.exceptions import SdnValidationError

#: Versão do schema do arquivo (migração futura).
SCHEMA_VERSION = 1

#: Fluxos com policy própria; a chave composta impede colisão entre eles.
FLOWS = ("internet", "site")

#: Ação do behavior VRP.
BEHAVIOR_ACTIONS = ("permit", "deny")

#: Direções aceitas no binding da interface.
DIRECTIONS = ("inbound", "outbound")

#: Faixa de ACL avançada VRP (destino/fluxo).
ACL_RULE_RANGE = (3000, 3999)

#: Nome de objeto VRP (classifier/behavior/policy): 1–32 caracteres ASCII.
_VRP_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,31}$")

_SPEC_IFACE = ParamSpec("interface", "interface", ParamKind.INTERFACE)


@dataclass(frozen=True)
class TrafficPolicyPreset:
    """Objetos VRP e binding que compõem a policy de um fluxo.

    Attributes:
        device_key: chave estável do device (isolamento por device).
        flow: fluxo da policy (``internet`` ou ``site``).
        classifier: nome do ``traffic classifier``.
        behavior: nome do ``traffic behavior``.
        policy: nome da ``traffic policy``.
        behavior_action: ação do behavior (``permit`` ou ``deny``).
        acl_number: número da ACL avançada (3000–3999).
        interface: interface onde a policy é aplicada.
        direction: direção do binding (``inbound``/``outbound``).
        applied: cache do último estado conhecido do binding.
        preexisting: objetos já existiam no device antes da nossa criação?
            Se ``True``, o rollback não deve removê-los.
    """

    device_key: str
    flow: str
    classifier: str
    behavior: str
    policy: str
    behavior_action: str
    acl_number: int
    interface: str
    direction: str
    applied: bool = False
    preexisting: bool = False

    def to_dict(self) -> dict[str, object]:
        """Representação canônica para o JSON (campos do dataclass)."""
        return asdict(self)


def _fail(message: str) -> SdnValidationError:
    return SdnValidationError(f"Preset de traffic policy inválido: {message}")


def preset_path() -> Path:
    """Caminho de ``traffic_policy_presets.json`` (mesma resolução de ``db.py``).

    Usa ``HW_DATA_DIR``/``HUAWEI_MANAGER_DIR`` se definidos; senão
    ``~/.huawei_manager``; com fallback para o diretório corrente e
    ``/tmp`` quando não há permissão de escrita.
    """
    custom_dir = os.environ.get("HW_DATA_DIR") or os.environ.get(
        "HUAWEI_MANAGER_DIR"
    )
    base = Path(custom_dir) if custom_dir else Path.home() / ".huawei_manager"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        fallback = Path.cwd() / ".huawei_manager"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            base = fallback
        except OSError:
            base = Path("/tmp/huawei_manager")
            base.mkdir(parents=True, exist_ok=True)
    return base / "traffic_policy_presets.json"


def _preset_key(device_key: str, flow: str) -> str:
    """Chave composta do mapa persistido."""
    return f"{device_key}|{flow}"


def _validate_lookup(device_key: str, flow: str) -> None:
    """Valida os argumentos de consulta antes de tocar no arquivo."""
    if not isinstance(device_key, str) or not device_key.strip() or "|" in device_key:
        raise _fail("device_key vazio, não textual ou contém '|'")
    if not isinstance(flow, str) or flow not in FLOWS:
        raise _fail(f"flow {flow!r} inválido (use {', '.join(FLOWS)})")


def _vrp_name(key: str, value: object) -> str:
    """Nome VRP obrigatório e canônico (fail-closed)."""
    if not isinstance(value, str) or not _VRP_NAME_RE.fullmatch(value):
        raise _fail(
            f"nome VRP '{key}' inválido "
            "(1–32 caracteres ASCII: letra/_ no início, letras, números, '-' e '_')"
        )
    return value


def validate_preset(preset: TrafficPolicyPreset) -> TrafficPolicyPreset:
    """Valida um preset de forma canônica (fail-closed).

    Usado tanto na escrita quanto na leitura do JSON: qualquer campo fora
    do contrato aborta a operação.
    """
    device_key = preset.device_key
    if (
        not isinstance(device_key, str)
        or not device_key.strip()
        or "|" in device_key
    ):
        raise _fail("device_key vazio, não textual ou contém '|'")
    if preset.flow not in FLOWS:
        raise _fail(f"flow {preset.flow!r} inválido (use {', '.join(FLOWS)})")
    if preset.behavior_action not in BEHAVIOR_ACTIONS:
        raise _fail(
            f"behavior_action {preset.behavior_action!r} inválido "
            f"(use {', '.join(BEHAVIOR_ACTIONS)})"
        )
    if preset.direction not in DIRECTIONS:
        raise _fail(
            f"direção {preset.direction!r} desconhecida "
            f"(use {', '.join(DIRECTIONS)})"
        )
    number = preset.acl_number
    low, high = ACL_RULE_RANGE
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not low <= number <= high
    ):
        raise _fail(f"número da ACL {number!r} fora da faixa {low}–{high}")
    classifier = _vrp_name("classifier", preset.classifier)
    behavior = _vrp_name("behavior", preset.behavior)
    policy = _vrp_name("policy", preset.policy)
    interface = validate_value(_SPEC_IFACE, preset.interface)
    if not interface:
        raise _fail("interface vazia")
    if not isinstance(preset.applied, bool):
        raise _fail("campo 'applied' deve ser booleano")
    if not isinstance(preset.preexisting, bool):
        raise _fail("campo 'preexisting' deve ser booleano")
    return TrafficPolicyPreset(
        device_key=device_key,
        flow=preset.flow,
        classifier=classifier,
        behavior=behavior,
        policy=policy,
        behavior_action=preset.behavior_action,
        acl_number=number,
        interface=interface,
        direction=preset.direction,
        applied=preset.applied,
        preexisting=preset.preexisting,
    )


def _empty_file() -> dict[str, object]:
    return {"version": SCHEMA_VERSION, "presets": {}}


def _read_raw(path: Path) -> dict[str, object]:
    """Lê o arquivo; ausente → estrutura vazia; corrompido → erro."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _empty_file()
    except OSError as exc:
        raise _fail(f"não foi possível ler {path}: {exc}") from exc
    if not text.strip():
        return _empty_file()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _fail(f"JSON corrompido em {path}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise _fail(f"estrutura inesperada em {path} (esperado objeto JSON)")
    # json.loads devolve Any; após isinstance o cast é seguro e tipado.
    data = cast(dict[str, object], decoded)
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise _fail(f"versão {version!r} inválida (esperada {SCHEMA_VERSION})")
    if version != SCHEMA_VERSION:
        raise _fail(
            f"versão {version} não suportada (esperada {SCHEMA_VERSION})"
        )
    presets = data.get("presets")
    if presets is None:
        data["presets"] = {}
    elif not isinstance(presets, dict):
        raise _fail("campo 'presets' inválido (esperado objeto JSON)")
    return data


def _presets_of(data: dict[str, object]) -> dict[str, object]:
    """Mapa ``chave -> preset`` do arquivo, sempre tipado."""
    raw = data.get("presets")
    if not isinstance(raw, dict):
        return {}
    return cast(dict[str, object], raw)


def _req_str(raw: dict[str, object], key: str) -> str:
    """Texto obrigatório do JSON (ausente/não textual → falha fechada)."""
    value = raw.get(key)
    if not isinstance(value, str):
        raise _fail(f"campo '{key}' ausente ou não textual")
    return value


def _req_int(raw: dict[str, object], key: str) -> int:
    """Inteiro obrigatório do JSON (bool não conta como inteiro)."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"campo '{key}' ausente ou não inteiro")
    return value


def _req_bool(raw: dict[str, object], key: str, default: bool) -> bool:
    """Booleano opcional do JSON (tipo errado → falha fechada)."""
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise _fail(f"campo '{key}' deve ser booleano")
    return value


def _preset_from_dict(raw: dict[str, object]) -> TrafficPolicyPreset:
    """Monta o preset a partir do JSON validando cada campo (fail-closed)."""
    return TrafficPolicyPreset(
        device_key=_req_str(raw, "device_key"),
        flow=_req_str(raw, "flow"),
        classifier=_vrp_name("classifier", raw.get("classifier")),
        behavior=_vrp_name("behavior", raw.get("behavior")),
        policy=_vrp_name("policy", raw.get("policy")),
        behavior_action=_req_str(raw, "behavior_action"),
        acl_number=_req_int(raw, "acl_number"),
        interface=_req_str(raw, "interface"),
        direction=_req_str(raw, "direction"),
        applied=_req_bool(raw, "applied", False),
        preexisting=_req_bool(raw, "preexisting", False),
    )


def _write_raw(path: Path, data: dict[str, object]) -> None:
    """Escrita atômica: grava em temp e troca por ``replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        tmp.write_text(payload + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise _fail(f"não foi possível gravar {path}: {exc}") from exc


def load_preset(device_key: str, flow: str) -> TrafficPolicyPreset | None:
    """Carrega o preset do device/fluxo; ``None`` se não existe.

    Raises:
        SdnValidationError: JSON corrompido, versão não suportada, campo
            desconhecido ou preset fora do contrato.
    """
    _validate_lookup(device_key, flow)
    data = _read_raw(preset_path())
    raw = _presets_of(data).get(_preset_key(device_key, flow))
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _fail(f"preset de '{device_key}|{flow}' não é um objeto JSON")
    raw_typed = cast(dict[str, object], raw)
    known = {f.name for f in fields(TrafficPolicyPreset)}
    unknown = set(raw_typed) - known
    if unknown:
        raise _fail(
            f"campos desconhecidos no preset de '{device_key}|{flow}': "
            f"{', '.join(sorted(unknown))}"
        )
    preset = validate_preset(_preset_from_dict(raw_typed))
    expected = _preset_key(preset.device_key, preset.flow)
    actual = _preset_key(device_key, flow)
    if expected != actual:
        raise _fail(f"chave '{actual}' não corresponde ao preset '{expected}'")
    return preset


def save_preset(preset: TrafficPolicyPreset) -> None:
    """Valida e persiste o preset do device/fluxo (substitui o anterior)."""
    validated = validate_preset(preset)
    target = preset_path()
    data = _read_raw(target)
    presets = _presets_of(data)
    presets[
        _preset_key(validated.device_key, validated.flow)
    ] = validated.to_dict()
    data["presets"] = presets
    data["version"] = SCHEMA_VERSION
    _write_raw(target, data)


def delete_preset(device_key: str, flow: str) -> bool:
    """Remove o preset do device/fluxo; ``True`` se havia algo a remover.

    Arquivo ausente ou chave inexistente → ``False`` (não é erro: o estado
    final desejado — preset inexistente — já foi alcançado).
    """
    _validate_lookup(device_key, flow)
    target = preset_path()
    data = _read_raw(target)
    presets = _presets_of(data)
    key = _preset_key(device_key, flow)
    if key not in presets:
        return False
    del presets[key]
    data["presets"] = presets
    _write_raw(target, data)
    return True


def set_applied(device_key: str, flow: str, applied: bool) -> None:
    """Atualiza só o cache ``applied`` do preset do device/fluxo.

    Preset inexistente é no-op (não cria arquivo nem preset).
    """
    _validate_lookup(device_key, flow)
    if not isinstance(applied, bool):
        raise _fail("campo 'applied' deve ser booleano")
    preset = load_preset(device_key, flow)
    if preset is None:
        return
    save_preset(
        TrafficPolicyPreset(
            device_key=preset.device_key,
            flow=preset.flow,
            classifier=preset.classifier,
            behavior=preset.behavior,
            policy=preset.policy,
            behavior_action=preset.behavior_action,
            acl_number=preset.acl_number,
            interface=preset.interface,
            direction=preset.direction,
            applied=applied,
            preexisting=preset.preexisting,
        )
    )
