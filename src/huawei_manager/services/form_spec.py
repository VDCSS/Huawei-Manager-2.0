"""Descrições declarativas dos formulários compostos da aba Serviços.

Um *formulário* é a união de seções; cada seção tem campos tipados
(:class:`FormField`) e pode ser repetível (várias linhas — ex.: regras de
ACL, rotas estáticas).

A validação de valor tem **fonte única**: ``validate_value`` de
:mod:`huawei_manager.basic_config.params`. Este módulo apenas descreve a
forma; a renderização/regra de negócio vive em ``acl_form``/``route_form``
e é despachada por :mod:`huawei_manager.services.form_registry`.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from huawei_manager.basic_config.params import ParamKind, ParamSpec, validate_value
from huawei_manager.exceptions import SdnValidationError

# Valores de uma seção (campo -> texto bruto já normalizado pelo chamador).
SectionValues = Mapping[str, str]
# Valores do formulário inteiro: section_key -> valores (ou lista de linhas).
FormValues = Mapping[str, SectionValues | Sequence[SectionValues]]


@dataclass(frozen=True)
class FormField:
    """Campo de formulário com tipo, faixa e dependência opcional."""

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
    #: Chave do campo controlador + valores que habilitam este campo.
    #: A referência é global no formulário (chaves são únicas no formulário).
    depends_on: tuple[str, tuple[str, ...]] | None = None

    @property
    def param_spec(self) -> ParamSpec:
        """Converte para o :class:`ParamSpec` usado na validação canônica."""
        return ParamSpec(
            key=self.key,
            label=self.label,
            kind=self.kind,
            default=self.default,
            required=self.required,
            choices=self.choices,
            minimum=self.minimum,
            maximum=self.maximum,
            max_len=self.max_len,
            secret=self.secret,
            help=self.help,
        )

    def validate(self, raw: str | None) -> str:
        """Valida e normaliza o valor bruto deste campo."""
        return validate_value(self.param_spec, raw)


@dataclass(frozen=True)
class FormSection:
    """Grupo de campos — único (``repeatable=False``) ou repetível."""

    key: str
    title: str
    fields: tuple[FormField, ...]
    repeatable: bool = False
    min_rows: int = 0
    max_rows: int = 20


@dataclass(frozen=True)
class FormWarning:
    """Aviso exibido quando um campo assume um dos valores indicados."""

    field_key: str
    values: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class FormSpec:
    """Formulário completo: identidade + seções."""

    kind: str
    title: str
    sections: tuple[FormSection, ...]
    #: Comando read-only de consulta do estado já aplicado (opcional).
    consult_command: str = ""
    #: Avisos condicionais exibidos conforme o valor de um campo.
    warnings: tuple[FormWarning, ...] = ()
    #: Padrões (regex) das linhas **aceitas** pelo validador de política.
    #: Não são derivados das linhas renderizadas — a allowlist é declarada
    #: aqui, para que uma linha inesperada seja bloqueada (defesa em
    #: profundidade, em vez de allowlist tautológica).
    allow_patterns: tuple[str, ...] = ()
    #: Padrões (regex) de linhas sensíveis que exigem confirmação explícita
    #: do operador (ex.: aplicação de ACL que pode cortar o próprio acesso).
    confirm_patterns: tuple[str, ...] = ()

    def section(self, key: str) -> FormSection | None:
        for sec in self.sections:
            if sec.key == key:
                return sec
        return None

    def field(self, key: str) -> FormField | None:
        """Busca um campo pelo identificador global."""
        for sec in self.sections:
            for fld in sec.fields:
                if fld.key == key:
                    return fld
        return None

    def all_fields(self) -> tuple[FormField, ...]:
        out: list[FormField] = []
        for sec in self.sections:
            out.extend(sec.fields)
        return tuple(out)


@dataclass(frozen=True)
class RenderedForm:
    """Resultado da renderização de um formulário.

    Attributes:
        lines: bloco de configuração pronto para envio (ordem importa).
        anchors: trechos que precisam existir no ``running-config`` para
            confirmar a aplicação (verificação pós-envio).
        rollback_builder: recebe o ``running-config`` anterior (snapshot) e
            devolve as linhas de rollback; ``None`` = sem rollback.
    """

    lines: tuple[str, ...]
    anchors: tuple[str, ...]
    rollback_builder: Callable[[str], list[str]] | None = None


def require_field(spec: FormSpec, key: str) -> FormField:
    """Campo obrigatório do formulário (erro de domínio se ausente)."""
    fld = spec.field(key)
    if fld is None:
        raise SdnValidationError(f"Campo desconhecido no formulário: '{key}'")
    return fld


def section_rows(
    values: FormValues, section_key: str
) -> list[dict[str, str]]:
    """Normaliza os valores de uma seção em lista de linhas.

    Seções únicas viram uma linha; seções repetíveis viram N linhas.
    """
    raw = values.get(section_key)
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return [dict(raw)]
    return [dict(row) for row in raw]


def global_values(values: FormValues) -> dict[str, str]:
    """Achata o formulário num mapa ``field_key -> valor``.

    Seções repetíveis contribuem com o valor da **primeira** linha — usado
    apenas para resolver dependências entre seções (ex.: tipo de ACL
    decidindo se o campo "protocolo" aparece nas regras).
    """
    flat: dict[str, str] = {}
    for section_key, raw in values.items():
        rows = section_rows(values, section_key)
        if not rows:
            continue
        for key, value in rows[0].items():
            flat[key] = value
    return flat


def field_visible(
    field: FormField, values: FormValues
) -> bool:
    """Resolve a visibilidade de um campo (``depends_on``)."""
    if field.depends_on is None:
        return True
    controller_key, allowed = field.depends_on
    current = global_values(values).get(controller_key, "")
    return current in allowed
