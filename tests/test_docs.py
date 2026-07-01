"""Testes para documentação de arquitetura (ADRs)."""

from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
ADR_DIR = DOCS_DIR / "adr"

REQUIRED_ADR_SECTIONS = ["Status", "Context", "Decision", "Consequences"]
REQUIRED_ADR_IDS = ["001", "002", "003", "004"]

ARCHITECTURE_FILE = DOCS_DIR / "architecture.md"


def _read_adr(adr_id: str) -> str:
    """Lê o conteúdo de um ADR pelo ID."""
    path = ADR_DIR / f"{adr_id}-*.md"
    from glob import glob
    matches = sorted(glob(str(path)))
    if not matches:
        msg = f"ADR {adr_id} não encontrado em {ADR_DIR}"
        raise FileNotFoundError(msg)
    return Path(matches[0]).read_text(encoding="utf-8")


class TestAdr004IntegrationStrategy:
    """valida o ADR de estratégia de integração do sdn_controller."""

    ADR_PATH = ADR_DIR / "004-integration-strategy.md"

    def test_file_exists(self) -> None:
        assert self.ADR_PATH.exists(), f"ADR não encontrado: {self.ADR_PATH}"

    def test_has_required_sections(self) -> None:
        content = self.ADR_PATH.read_text(encoding="utf-8")
        for section in REQUIRED_ADR_SECTIONS:
            assert f"## {section}" in content, (
                f"Seção '{section}' obrigatória no ADR 004"
            )

    def test_decision_object_not_mixin(self) -> None:
        """O ADR deve decidir entre objeto interno vs novo mixin."""
        content = self.ADR_PATH.read_text(encoding="utf-8")
        assert "objeto interno" in content.lower() or "self._controller" in content

    def test_decision_lldp_naming(self) -> None:
        """O ADR deve documentar a renomeação para evitar conflito com topology.py."""
        content = self.ADR_PATH.read_text(encoding="utf-8")
        assert "lldp_discovery" in content or "topo_manager" in content or "topology.py" in content

    def test_documents_coexistence(self) -> None:
        """O ADR deve explicar como sdn_controller/ coexiste com GUI existente."""
        content = self.ADR_PATH.read_text(encoding="utf-8")
        assert any(word in content.lower() for word in ["coexist", "import", "mixin", "mro", "acoplamento"])

    def test_has_consequences_list(self) -> None:
        """Seção de Consequências deve listar prós e contras."""
        content = self.ADR_PATH.read_text(encoding="utf-8")
        keywords = ["positivas", "negativas", "pros", "contras", "riscos"]
        assert any(k in content.lower() for k in keywords)


def test_adr_directory_exists() -> None:
    """O diretório docs/adr/ deve existir."""
    assert ADR_DIR.exists(), "Crie o diretório docs/adr/"


def test_all_required_adrs_exist() -> None:
    """Todos os ADRs obrigatórios (001-004) devem existir."""
    for adr_id in REQUIRED_ADR_IDS:
        from glob import glob
        matches = sorted(glob(str(ADR_DIR / f"{adr_id}-*.md")))
        assert len(matches) == 1, (
            f"ADR {adr_id} deve ter exatamente 1 arquivo, encontrados: {len(matches)}"
        )


def test_all_adrs_have_required_sections() -> None:
    """Todo ADR deve ter as 4 seções obrigatórias."""
    for adr_id in REQUIRED_ADR_IDS:
        content = _read_adr(adr_id)
        for section in REQUIRED_ADR_SECTIONS:
            assert f"## {section}" in content, (
                f"ADR {adr_id} não tem seção '{section}'"
            )


def test_adr_001_ssh_only_decision() -> None:
    """ADR 001 deve documentar SSH como único protocolo southbound."""
    content = _read_adr("001")
    keywords = ["ssh", "cli", "netmiko", "southbound"]
    assert any(k in content.lower() for k in keywords), (
        "ADR 001 deve mencionar SSH/CLI como protocolo southbound"
    )


def test_adr_002_local_encryption_decision() -> None:
    """ADR 002 deve documentar criptografia AES-256-GCM local."""
    content = _read_adr("002")
    keywords = ["aes", "encrypt", "gcm", "local"]
    assert any(k in content.lower() for k in keywords), (
        "ADR 002 deve mencionar AES-256-GCM como algoritmo de criptografia"
    )


def test_adr_003_tofu_hostkey_decision() -> None:
    """ADR 003 deve documentar TOFU como estratégia de host key."""
    content = _read_adr("003")
    keywords = ["tofu", "host key", "trust on first", "known_hosts"]
    assert any(k in content.lower() for k in keywords), (
        "ADR 003 deve mencionar TOFU como estratégia de verificação"
    )


def test_adr_index() -> None:
    """Deve haver um índice/listagem de ADRs para navegação."""
    readme = ADR_DIR / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        for adr_id in REQUIRED_ADR_IDS:
            assert adr_id in content, f"Índice deve listar o ADR {adr_id}"


class TestArchitectureDocument:
    """valida o documento de arquitetura geral."""

    def test_file_exists(self) -> None:
        assert ARCHITECTURE_FILE.exists(), (
            f"Arquivo de arquitetura não encontrado: {ARCHITECTURE_FILE}"
        )

    def test_has_mermaid_diagram(self) -> None:
        """Deve conter ao menos um diagrama Mermaid."""
        content = ARCHITECTURE_FILE.read_text(encoding="utf-8")
        assert "```mermaid" in content, (
            "Arquitetura deve conter diagrama Mermaid"
        )

    def test_has_threat_model(self) -> None:
        """Deve conter análise de ameaças (STRIDE ou similar)."""
        content = ARCHITECTURE_FILE.read_text(encoding="utf-8")
        keywords = ["stride", "threat", "ameaça", "risco"]
        assert any(k in content.lower() for k in keywords), (
            "Arquitetura deve incluir modelo de ameaças"
        )

    def test_has_layers_section(self) -> None:
        """Deve descrever as camadas da arquitetura."""
        content = ARCHITECTURE_FILE.read_text(encoding="utf-8")
        assert "layer" in content.lower() or "camada" in content.lower(), (
            "Arquitetura deve descrever camadas"
        )
