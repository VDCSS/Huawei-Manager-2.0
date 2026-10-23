"""Backend NAPALM opcional para dispositivos Huawei VRP (atrás de flag).

Ativado pela variável de ambiente ``HW_BACKEND=napalm`` (ver :data:`BACKEND_ENV`).
Quando ``napalm-huawei-vrp`` não está instalado o app continua no backend Netmiko
padrão — degradação fechada, nunca exceção em tempo de import.

Motivação (análise do driver comunitário ``napalm-huawei-vrp==1.2.0``):
    * o executor atual (``southbound.send_service_commands``) entra em ``system-view``
      uma vez e envia cada comando em separado, sem esperar o prompt de view;
    * a VRP responde ``% Unrecognized command`` no contexto errado e o app ainda
      reporta sucesso — falha silenciosa;
    * o driver NAPALM prova a semântica correta: ``system-view`` + cada linha com
      ``expect_string=r"\\[.+\\]"`` (o prompt vira ``[acl-adv-3000]`` e segue casando),
      descarte em caso de erro e ``return`` ao final.

Contrato de segurança (AGENTS.md):
    * **dry-run obrigatório** antes de aplicar (``preview`` → diff running × candidate);
    * **snapshot pré-mudança** (``snapshot`` → ``display current-configuration``);
    * **entrada no AuditLogger** preservando o schema (`timestamp`, `op`, `user`,
      `host`, `status`, `duration_ms`, `session_id`, `category`);
    * **rollback**: o snapshot devolvido é a base do plano de rollback (restauração
      via página de Backup do app).
    * fail-closed: sem backend disponível → segue Netmiko, sem fallback inseguro.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from huawei_manager.exceptions import SdnCommandError, SdnConnectionError

if TYPE_CHECKING:
    # Só em tempo de análise: o pacote é opcional (extra `napalm`), mas os
    # stubs parciais em typings/ dão tipo real à fronteira do driver.
    from napalm import NetworkDriver

# ── Flag de feature ───────────────────────────────────────────────────
BACKEND_ENV = "HW_BACKEND"
BACKEND_NETMIKO = "netmiko"
BACKEND_NAPALM = "napalm"
DEFAULT_BACKEND = BACKEND_NETMIKO
_VALID_BACKENDS = (BACKEND_NETMIKO, BACKEND_NAPALM)

# A VRP reporta erros começando com '% ...' na primeira coluna. O driver
# NAPALM só procura a substring "error", o que engole '% Unrecognized command'
# e dispara falso-positivo em strings legítimas. Marcadores extraídos do
# Command Reference VRP5/VRP6/VRP8.
_VRP_ERROR_PREFIXES = (
    "% unrecognized",
    "% wrong",
    "% invalid",
    "% incomplete",
    "% ambiguous",
    "% error",
    "% no such",
    "% no ",
    "% unsupported",
    "command not found",
    "error:",
)


def detect_vrp_errors(output: str) -> list[str]:
    """Retorna as linhas de erro detectadas na saída de comandos VRP.

    Args:
        output: Saída concatenada enviada de volta pelo dispositivo.

    Returns:
        Lista de linhas rejeitadas (vazia = tudo aceito).
    """
    found: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if any(low.startswith(prefix) for prefix in _VRP_ERROR_PREFIXES):
            found.append(stripped)
    return found


def napalm_status() -> tuple[bool, str]:
    """Verifica se ``napalm-huawei-vrp`` está instalável.

    Returns:
        ``(True, "")`` quando disponível; ``(False, motivo)`` caso contrário.
    """
    try:
        import napalm_huawei_vrp  # noqa: F401
        from napalm import get_network_driver  # noqa: F401
    except ImportError as exc:
        return False, f"pacote indisponivel ({exc.__class__.__name__}: {exc})"
    return True, ""


def resolve_backend(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Resolve o backend efetivo a partir da flag de feature.

    Args:
        env: Mapa de ambiente (``os.environ`` por padrão).

    Returns:
        ``(backend_efetivo, aviso)`` — nunca propaga exceção; valor inválido ou
        pacote ausente cai no Netmiko com aviso explícito (fail-closed).
    """
    source = os.environ if env is None else env
    raw = (source.get(BACKEND_ENV, DEFAULT_BACKEND) or "").strip().lower()
    if raw not in _VALID_BACKENDS:
        return DEFAULT_BACKEND, f"{BACKEND_ENV} invalido ({raw!r}); usando '{DEFAULT_BACKEND}'"
    if raw == BACKEND_NAPALM:
        ok, reason = napalm_status()
        if not ok:
            return (
                DEFAULT_BACKEND,
                f"backend '{BACKEND_NAPALM}' solicitado, porem {reason}; usando '{DEFAULT_BACKEND}'",
            )
    return raw, ""


@dataclass(frozen=True)
class ApplyResult:
    """Resultado estruturado de uma aplicação de configuração."""

    snapshot: str
    output: str
    duration_ms: float


class NapalmVRPBackend:
    """Aplica configuração em lote com dry-run, snapshot e detecção de erro.

    Reusa a conexão Netmiko já aberta pela sessão (nenhuma segunda autenticação
    e nenhum segredo novo manipulado — as credenciais permanecem no ``SecretsBackend``).
    """

    def __init__(
        self,
        conn: Any,
        *,
        user: str = "unknown",
        host: str = "",
        session_id: str | None = None,
        audit: Any = None,
        commit: bool = False,
        read_timeout: float = 60.0,
    ) -> None:
        self._conn = conn
        self._driver: NetworkDriver | None = None
        self._user = user
        self._host = host
        self._session_id = session_id
        self._audit = audit
        self._commit = commit
        self._timeout = read_timeout

    # ── driver NAPALM (lazy, import guardado) ────────────────────────
    @property
    def driver(self) -> NetworkDriver:
        """Driver ``huawei_vrp`` do NAPALM apontando para a sessão existente."""
        driver = self._driver
        if driver is None:
            ok, reason = napalm_status()
            if not ok:
                raise SdnConnectionError(reason)
            from napalm import get_network_driver

            driver = get_network_driver("huawei_vrp")(
                hostname="", username="", password="", optional_args={}
            )
            # Reusa a conexão Netmiko aberta pela sessão (não abre segundo SSH).
            driver.device = self._conn
            self._driver = driver
        return driver

    # ── leitura / dry-run ────────────────────────────────────────────
    def snapshot(self) -> str:
        """Backup pré-mudança: running-config atual."""
        return str(self._conn.send_command("display current-configuration",
                                           read_timeout=120))

    def preview(self, commands: list[str]) -> str:
        """Dry-run: diff entre running-config e o candidate.

        Args:
            commands: Comandos na view correta (já resolvidos pelo chamador).

        Returns:
            Diff textual (vazio = nada mudaria).
        """
        driver = self.driver
        driver.load_merge_candidate(config="\n".join(commands))
        try:
            return str(driver.compare_config())
        except Exception:
            driver.discard_config()
            raise

    def discard(self) -> None:
        """Descarta o candidate carregado (se houver)."""
        if self._driver is not None:
            self._driver.discard_config()

    # ── escrita ──────────────────────────────────────────────────────
    def _run_in_config_mode(self, commands: list[str]) -> str:
        """Executa o lote inteiro numa única sessão de config mode (VRP).

        Segue a semântica do driver NAPALM: espera o prompt ``[view]`` após cada
        linha (o prompt muda de view e continua casando), detecta erro e, se
        houver, **descarta as alterações pendentes antes de reportar**.
        """
        errors: list[str] = []
        out = str(self._conn.send_command("system-view",
                                          expect_string=r"\[.+\]",
                                          read_timeout=self._timeout))
        errors += detect_vrp_errors(out)
        for command in commands:
            resp = str(self._conn.send_command(command,
                                               expect_string=r"\[.+\]",
                                               read_timeout=self._timeout))
            out += "\n" + resp
            # Valida cada resposta ISOLADAMENTE: concatenar saídas sem \n funde
            # a linha de sucesso com a de erro e engole o diagnóstico.
            errors += detect_vrp_errors(resp)
            if errors:
                # Fail-fast: o primeiro rejeitado indica contexto/view errado —
                # seguir empurrando o resto do lote só piora o diagnóstico.
                break

        if not errors and self._commit:
            resp = str(self._conn.send_command("commit",
                                               expect_string=r"\[.+\]",
                                               read_timeout=self._timeout))
            out += "\n" + resp
            errors += detect_vrp_errors(resp)

        if errors:
            out += self._discard_and_exit()
            raise SdnCommandError(
                "Comandos rejeitados pelo dispositivo (alteracoes descartadas): "
                + "; ".join(errors[:5])
                + f"\n{out}"
            )

        out += str(self._conn.send_command("return",
                                           expect_string=r"<.+>",
                                           read_timeout=self._timeout))
        return out

    def _discard_and_exit(self) -> str:
        """Sai do config mode descartando alterações pendentes.

        Nunca propaga exceção: uma falha no descarte não pode esconder o erro
        real de validação que motivou o descarte.
        """
        try:
            ret = str(self._conn.send_command("return",
                                              expect_string=r"[<\[].+[>\]]",
                                              read_timeout=self._timeout))
            if "ncommitted" in ret:
                ret += str(self._conn.send_command("n",
                                                   expect_string=r"<.+>",
                                                   read_timeout=30))
            return ret
        except Exception as exc:  # degradação fechada: o erro original segue visível
            return f"\n[aviso] nao foi possivel sair do config mode: {exc}"

    def apply(self, commands: list[str], *, snapshot: str | None = None) -> ApplyResult:
        """Aplica um lote de comandos com snapshot pré-mudança e auditoria.

        Args:
            commands: Comandos na view correta (``view`` + comando já resolvidos).
            snapshot: Running-config pré-mudança (calculado se ``None``).

        Returns:
            :class:`ApplyResult` com snapshot, saída bruta e duração.

        Raises:
            SdnConnectionError: Sem conexão.
            SdnCommandError: Dispositivo rejeitou algum comando (alterações descartadas).
        """
        if self._conn is None:
            raise SdnConnectionError("Sem conexao ativa")

        started = time.monotonic()
        pre = snapshot if snapshot is not None else self.snapshot()
        try:
            out = self._run_in_config_mode(commands)
        except SdnCommandError as exc:
            self._log(status="blocked", commands=commands, started=started,
                      error=str(exc))
            raise
        except Exception as exc:
            self._log(status="error", commands=commands, started=started,
                      error=str(exc))
            raise SdnCommandError(f"Falha ao aplicar configuracao: {exc}") from exc

        self._log(status="ok", commands=commands, started=started)
        return ApplyResult(
            snapshot=pre,
            output=out,
            duration_ms=(time.monotonic() - started) * 1000.0,
        )

    # ── auditoria ────────────────────────────────────────────────────
    def _log(self, *, status: str, commands: list[str], started: float,
             error: str = "") -> None:
        if self._audit is None:
            return
        try:
            entry: dict[str, Any] = {
                "backend": BACKEND_NAPALM,
                "commands": len(commands),
            }
            if error:
                entry["error"] = error
            self._audit.log_operation(
                "config_apply",
                user=self._user,
                host=self._host,
                status=status,
                duration_ms=(time.monotonic() - started) * 1000.0,
                session_id=self._session_id,
                category="config",
                **entry,
            )
        except Exception:  # auditoria nunca pode derrubar a operação
            pass


def backend_from_session(
    conn: Any,
    *,
    user: str = "unknown",
    host: str = "",
    session_id: str | None = None,
    audit: Any = None,
) -> tuple[str, str, Callable[[list[str]], ApplyResult] | None]:
    """Fabrica o executor de config conforme a flag de feature.

    Returns:
        ``(backend_efetivo, aviso, executor_ou_None)``. Quando o backend é o
        Netmiko (padrão) o executor é ``None`` e o chamador usa o caminho atual.
    """
    backend, warning = resolve_backend()
    if backend != BACKEND_NAPALM:
        return backend, warning, None
    try:
        engine = NapalmVRPBackend(conn, user=user, host=host,
                                  session_id=session_id, audit=audit)
        engine.driver  # força o import lazy já aqui (falha cedo, fecha o caminho)
    except Exception as exc:  # degradação fechada para o Netmiko
        return BACKEND_NETMIKO, f"backend napalm indisponivel: {exc}", None
    return backend, warning, engine.apply
