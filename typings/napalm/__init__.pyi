"""Stub parcial de ``napalm`` — só a superfície usada pelo app.

O pacote NAPALM não publica ``py.typed`` nem arquivos ``.pyi``; sem este
stub o pyright trata toda chamada à API como ``Any`` implícito e emite
``reportMissingTypeStubs`` (fronteira de segurança: dry-run/apply em
``sdn_controller/napalm_backend.py``). Declarado aqui apenas o que o
código realmente usa, para que typo na API real (ex.: ``compare_conf()`)
falhe no CI em vez de em runtime com dispositivo real.

Referência: napalm.base.network_driver.NetworkDriver (napalm 5.x).
"""

from typing import Any

class NetworkDriver:
    """Driver NAPALM (superfície parcial).

    ``device`` não faz parte da API oficial: o app injeta a conexão Netmiko
    já aberta em ``NapalmVRPBackend.driver`` para reusar o SSH existente.
    """

    device: Any

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        optional_args: dict[str, Any] | None = None,
    ) -> None: ...
    def open(self) -> None: ...
    def close(self) -> None: ...
    def load_merge_candidate(
        self, filename: str | None = None, config: str | None = None
    ) -> None: ...
    def load_replace_candidate(
        self, filename: str | None = None, config: str | None = None
    ) -> None: ...
    def compare_config(self) -> str: ...
    def discard_config(self) -> None: ...
    def commit_config(self, message: str | None = None) -> None: ...

def get_network_driver(module_name: str) -> type[NetworkDriver]: ...
