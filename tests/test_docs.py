"""Testes para documentação de arquitetura (ADRs)."""

from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
ADR_DIR = DOCS_DIR / "adr"

REQUIRED_ADR_SECTIONS = ["Status", "Context", "Decision", "Consequences"]


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


def test_adr_index() -> None:
    """Deve haver um índice/listagem de ADRs para navegação."""
    readme = ADR_DIR / "README.md"
    if readme.exists():
        content = readme.read_text(encoding="utf-8")
        assert "004" in content, "Índice deve listar o ADR 004"
