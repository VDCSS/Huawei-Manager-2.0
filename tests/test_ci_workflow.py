"""Testes para o workflow de CI do GitHub Actions."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Majors estáveis atuais (ago/2026): checkout e setup-python em @v7,
# livres da deprecação do runtime Node 20.
EXPECTED_ACTION_PINS = {
    "actions/checkout": "v7",
    "actions/setup-python": "v7",
}


def _load_ci_workflow() -> dict:
    """Carrega o workflow de CI como dicionário YAML."""
    data = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "ci.yml deve conter um mapeamento YAML válido"
    return data


def _ci_steps() -> list[dict]:
    """Retorna os steps do job `ci` do workflow."""
    data = _load_ci_workflow()
    job = data["jobs"]["ci"]
    return job["steps"]


def _used_actions() -> list[str]:
    """Lista as referências `uses` presentes nos steps."""
    return [step["uses"] for step in _ci_steps() if "uses" in step]


class TestCiWorkflowActionPins:
    """Garante que as actions do CI usem majors estáveis atuais (@v7)."""

    def test_file_exists(self) -> None:
        assert CI_WORKFLOW.exists(), f"Workflow não encontrado: {CI_WORKFLOW}"

    def test_actions_pinned_to_current_majors(self) -> None:
        """checkout e setup-python devem estar em @v7 (Node 20 deprecation)."""
        uses = _used_actions()
        for action, expected_pin in EXPECTED_ACTION_PINS.items():
            expected_ref = f"{action}@{expected_pin}"
            assert expected_ref in uses, (
                f"{expected_ref} ausente em ci.yml; encontrado: {uses}"
            )

    def test_setup_python_keeps_python_3_10(self) -> None:
        """O workflow deve continuar fixando python-version 3.10."""
        setup_step = next(
            step
            for step in _ci_steps()
            if step.get("uses", "").startswith("actions/setup-python")
        )
        assert setup_step["with"]["python-version"] == "3.10", (
            "python-version do setup-python deve permanecer 3.10"
        )
