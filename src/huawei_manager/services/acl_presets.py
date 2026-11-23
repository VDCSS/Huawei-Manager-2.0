"""Perfil de ACL padrão de "Bloquear Internet" — persistido por device.

Núcleo **puro** (sem Qt, sem I/O de rede): guarda, por device, os
parâmetros da ACL padrão usada pela feature de bloqueio, para que as
próximas vezes que o operador abrir o modal ele encontre a regra já
definida (em vez de recriar do zero).

Contrato:

* o perfil é **por device** — um device não enxerga o perfil de outro;
* escrita **atômica** (arquivo temporário + ``replace``) para nunca
  deixar o JSON pela metade;
* JSON ausente → ``None`` (fluxo de criação); JSON **corrompido** →
  falha fechada (``SdnValidationError``), nunca fallback silencioso;
* ``applied`` é apenas o **cache** do último estado conhecido — a fonte
  de verdade é a leitura do ``running-config`` (o cache só cobre o caso
  em que não há device para consultar, ex.: modo MOCK/offline).

Limitação honesta (VRP): a imagem NE40E do EVE-NG (VRP 8.180) não tem
``traffic-filter`` nem ``traffic policy``; o modo MOCK é o baseline desse
ambiente — ver ``huawei_manager.services.traffic_policy``.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import cast

from huawei_manager.basic_config.params import ParamKind, ParamSpec, validate_value
from huawei_manager.exceptions import SdnValidationError

#: Versão do schema do arquivo (migração futura).
SCHEMA_VERSION = 1

#: Faixa de ACL avançada — a feature de bloqueio usa destino, que só a
#: ACL avançada (3000–3999) aceita.
ACL_BLOCK_RANGE = (3000, 3999)

#: Direções aceitas no binding da interface.
DIRECTIONS = ("inbound", "outbound")

_SPEC_IP = ParamSpec("destination_ip", "IP de destino", ParamKind.IPV4)
_SPEC_MASK = ParamSpec(
    "destination_mask", "Máscara destino", ParamKind.WILDCARD, required=False
)
_SPEC_IFACE = ParamSpec("interface", "Interface", ParamKind.INTERFACE)
_SPEC_ACL_NAME = ParamSpec("acl_name", "Nome da ACL", ParamKind.ACL_NAME)


@dataclass(frozen=True)
class AclBlockProfile:
    """Parâmetros da ACL padrão de bloqueio de um device.

    Attributes:
        device_key: chave estável do device (isolamento por device).
        acl_name: nome da ACL (usado quando ``id_mode`` for nome).
        acl_number: número da ACL avançada (3000–3999).
        destination_ip: IP de destino da regra (D1 — decisão do usuário).
        destination_mask: máscara curinga do destino (ex.: 0.0.0.255).
        interface: interface onde a ACL é aplicada (``traffic-filter``).
        direction: direção do binding (``inbound``/``outbound``).
        created_from_snapshot: a ACL já existia antes da nossa criação?
            Se ``True``, o rollback **não** apaga a ACL (preserva o estado
            pré-existente do device).
        applied: cache do último estado conhecido do binding (ver módulo).
    """

    device_key: str
    acl_name: str
    acl_number: int
    destination_ip: str
    destination_mask: str
    interface: str
    direction: str
    created_from_snapshot: bool = False
    applied: bool = False

    @property
    def acl_ref(self) -> str:
        """Referência da ACL como aparece no ``traffic-filter ... acl <ref>``.

        A VRP recusa ``acl number <n> name <x>`` (``SUPPORTS_ACL_NUMBER_AND_NAME
        = False``), então a identificação é **ou** número **ou** nome.
        """
        return str(self.acl_number)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _fail(message: str) -> SdnValidationError:
    return SdnValidationError(f"Perfil de Bloquear Internet inválido: {message}")


def profile_path() -> Path:
    """Caminho de ``acl_presets.json`` (mesma resolução de ``db.py``).

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
    return base / "acl_presets.json"


def device_key(name: str, host: str) -> str:
    """Chave estável do device para o perfil (nome + host)."""
    return f"{name.strip()}@{host.strip()}"


def validate_profile(profile: AclBlockProfile) -> AclBlockProfile:
    """Valida um perfil de forma canônica (fail-closed).

    Levanta ``SdnValidationError`` se qualquer campo estiver fora do
    contrato — usado tanto na escrita quanto na leitura do JSON.
    """
    if not profile.device_key.strip():
        raise _fail("device_key vazio")
    number = profile.acl_number
    low, high = ACL_BLOCK_RANGE
    if not isinstance(number, int) or not low <= number <= high:
        raise _fail(f"número da ACL {number!r} fora da faixa {low}–{high}")
    if profile.direction not in DIRECTIONS:
        raise _fail(
            f"direção {profile.direction!r} desconhecida "
            f"(use {', '.join(DIRECTIONS)})"
        )
    # Validação canônica: rejeita nome só numérico (colidiria com
    # 'acl number <n>' — ver ParamKind.ACL_NAME em params.py).
    acl_name = validate_value(_SPEC_ACL_NAME, profile.acl_name)
    if not acl_name:
        raise _fail("nome de ACL vazio")
    ip = validate_value(_SPEC_IP, profile.destination_ip)
    mask = validate_value(_SPEC_MASK, profile.destination_mask) or "0.0.0.0"
    if mask == "any":
        # "any" casaria tudo — não faz sentido como máscara de destino de
        # uma regra de bloqueio pontual.
        raise _fail("máscara de destino não pode ser 'any'")
    iface = validate_value(_SPEC_IFACE, profile.interface)
    if not iface:
        raise _fail("interface vazia")
    return AclBlockProfile(
        device_key=profile.device_key,
        acl_name=acl_name,
        acl_number=number,
        destination_ip=ip,
        destination_mask=mask,
        interface=iface,
        direction=profile.direction,
        created_from_snapshot=bool(profile.created_from_snapshot),
        applied=bool(profile.applied),
    )


def _empty_file() -> dict[str, object]:
    return {"version": SCHEMA_VERSION, "profiles": {}}


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
    profiles = data.get("profiles")
    if profiles is None:
        data["profiles"] = {}
    elif not isinstance(profiles, dict):
        raise _fail(f"campo 'profiles' inválido em {path}")
    return data


def _profiles_of(data: dict[str, object]) -> dict[str, object]:
    """Mapa ``device_key -> perfil`` do arquivo, sempre tipado."""
    raw = data.get("profiles")
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
    """Inteiro obrigatório do JSON (ausente/não inteiro → falha fechada)."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"campo '{key}' ausente ou não inteiro")
    return value


def _profile_from_dict(raw: dict[str, object]) -> AclBlockProfile:
    """Monta o perfil a partir do JSON validando cada campo (fail-closed)."""
    return AclBlockProfile(
        device_key=_req_str(raw, "device_key"),
        acl_name=_req_str(raw, "acl_name"),
        acl_number=_req_int(raw, "acl_number"),
        destination_ip=_req_str(raw, "destination_ip"),
        destination_mask=_req_str(raw, "destination_mask"),
        interface=_req_str(raw, "interface"),
        direction=_req_str(raw, "direction"),
        created_from_snapshot=bool(raw.get("created_from_snapshot", False)),
        applied=bool(raw.get("applied", False)),
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


def load_profile(
    path: Path | None = None, device_key: str | None = None
) -> AclBlockProfile | None:
    """Carrega o perfil do device; ``None`` se não existe.

    Args:
        path: arquivo JSON (padrão: :func:`profile_path`).
        device_key: chave estável do device (ver :func:`device_key`).

    Raises:
        SdnValidationError: JSON corrompido ou perfil fora do contrato.
    """
    if device_key is None or not device_key.strip():
        raise _fail("device_key é obrigatório")
    target = path if path is not None else profile_path()
    data = _read_raw(target)
    profiles = _profiles_of(data)
    raw = profiles.get(device_key)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise _fail(f"perfil de '{device_key}' não é um objeto JSON")
    known = {f.name for f in fields(AclBlockProfile)}
    raw_typed = cast(dict[str, object], raw)
    unknown = set(raw_typed) - known
    if unknown:
        raise _fail(
            f"campos desconhecidos no perfil de '{device_key}': "
            f"{', '.join(sorted(unknown))}"
        )
    profile = _profile_from_dict(raw_typed)
    return validate_profile(profile)


def save_profile(
    path: Path | None, profile: AclBlockProfile
) -> AclBlockProfile:
    """Valida e persiste o perfil do device (substitui o anterior)."""
    validated = validate_profile(profile)
    target = path if path is not None else profile_path()
    data = _read_raw(target)
    profiles = _profiles_of(data)
    profiles[validated.device_key] = validated.to_dict()
    data["profiles"] = profiles
    data["version"] = SCHEMA_VERSION
    _write_raw(target, data)
    return validated


def delete_profile(path: Path | None, device_key: str) -> bool:
    """Remove o perfil do device; ``True`` se havia algo a remover.

    Arquivo ausente ou chave inexistente → ``False`` (não é erro: o
    resultado final desejado — perfil inexistente — já foi alcançado).
    """
    if not device_key.strip():
        raise _fail("device_key vazio")
    target = path if path is not None else profile_path()
    data = _read_raw(target)
    profiles = _profiles_of(data)
    if device_key not in profiles:
        return False
    del profiles[device_key]
    data["profiles"] = profiles
    _write_raw(target, data)
    return True


def set_applied(
    path: Path | None, device_key: str, applied: bool
) -> AclBlockProfile | None:
    """Atualiza só o cache ``applied`` do perfil do device.

    ``None`` se não há perfil (nada a atualizar — não é erro).
    """
    profile = load_profile(path, device_key)
    if profile is None:
        return None
    updated = AclBlockProfile(
        device_key=profile.device_key,
        acl_name=profile.acl_name,
        acl_number=profile.acl_number,
        destination_ip=profile.destination_ip,
        destination_mask=profile.destination_mask,
        interface=profile.interface,
        direction=profile.direction,
        created_from_snapshot=profile.created_from_snapshot,
        applied=applied,
    )
    return save_profile(path, updated)
