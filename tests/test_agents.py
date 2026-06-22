"""Testes unitários para os agentes de auditoria (scanners)."""

from __future__ import annotations

from pathlib import Path

from agents import AgentItem, AgentResult

# ─── Agent dataclasses ────────────────────────────────────────────────

class TestAgentItem:
    def test_create_minimal(self) -> None:
        item = AgentItem(severity="info", file="test.py:1", message="msg", suggestion="fix")
        assert item.severity == "info"
        assert item.file == "test.py:1"
        assert item.message == "msg"
        assert item.suggestion == "fix"

    def test_create_with_defaults(self) -> None:
        """Severidades alternativas funcionam."""
        for sev in ("info", "warning", "error"):
            item = AgentItem(severity=sev, file="x.py", message="m", suggestion="s")
            assert item.severity == sev


class TestAgentResult:
    def test_create_minimal(self) -> None:
        r = AgentResult(name="dead_code", status="ok", summary="Nada")
        assert r.name == "dead_code"
        assert r.status == "ok"
        assert r.items == []

    def test_create_with_items(self) -> None:
        items = [AgentItem(severity="warning", file="a.py", message="x", suggestion="y")]
        r = AgentResult(name="test", status="warning", summary="1 item", items=items)
        assert len(r.items) == 1
        assert r.items[0].severity == "warning"


# ─── dead_code scanner ───────────────────────────────────────────────

class TestDeadCodeScan:
    def test_scan_empty_project(self, tmp_path: Path) -> None:
        from agents.scans.dead_code import scan
        result = scan(tmp_path)
        assert isinstance(result, AgentResult)
        assert result.name == "dead_code"

    def test_scan_clean_file(self, tmp_path: Path) -> None:
        """Um ficheiro com função usada não deve gerar alertas."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "clean.py").write_text(
            "def used() -> int:\n    return 1\n\nx = used()\n"
        )
        from agents.scans.dead_code import scan
        result = scan(tmp_path)
        assert len(result.items) == 0

    def test_scan_unused_function(self, tmp_path: Path) -> None:
        """Função privada verdadeiramente não chamada deve ser reportada."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "test.py").write_text(
            "def _truly_unused() -> int:\n    return 1\n\ndef _used_only() -> int:\n    return 42\n"
            "result = _used_only()\n"
        )
        from agents.scans.dead_code import scan
        result = scan(tmp_path)
        names = {i.message.split("'")[1] for i in result.items}
        assert "_truly_unused" in names
        assert "_used_only" not in names

    def test_scan_cross_file_usage(self, tmp_path: Path) -> None:
        """Método definido num ficheiro e chamado via self. noutro não é falso positivo."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "mixin_a.py").write_text(
            "class MixinA:\n    def _helper(self) -> int:\n        return 42\n"
        )
        (src / "app.py").write_text(
            "from mixin_a import MixinA\nclass App(MixinA):\n    def run(self) -> None:\n        self._helper()\n"
        )
        from agents.scans.dead_code import scan
        result = scan(tmp_path)
        names = {i.message.split("'")[1] for i in result.items}
        assert "_helper" not in names, "_helper usado via self. noutro ficheiro"

    def test_scan_exceptions(self, tmp_path: Path) -> None:
        """Dunder methods e hooks pytest não são reportados."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "hooks.py").write_text(
            "class TestFoo:\n    def setup_method(self) -> None: pass\n"
            "    def teardown_method(self) -> None: pass\n"
        )
        from agents.scans.dead_code import scan
        result = scan(tmp_path)
        names = {i.message.split("'")[1] for i in result.items}
        assert "setup_method" not in names
        assert "teardown_method" not in names


# ─── cross_ref scanner ───────────────────────────────────────────────

class TestCrossRefScan:
    def test_no_constants_file(self, tmp_path: Path) -> None:
        from agents.scans.cross_ref import scan
        result = scan(tmp_path)
        assert result.status == "error"

    def test_all_constants_used(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "huawei_manager"
        src.mkdir(parents=True)
        (src / "constants.py").write_text(
            "NEON_CYAN = '#00e5ff'\nBG_BASE = '#0d0d1a'\n"
        )
        (src / "app.py").write_text(
            "from constants import NEON_CYAN\nx = NEON_CYAN\n"
        )
        from agents.scans.cross_ref import scan
        result = scan(tmp_path)
        used_names = {i.message.split("'")[1] for i in result.items}
        assert "NEON_CYAN" not in used_names

    def test_unused_constant_reported(self, tmp_path: Path) -> None:
        src = tmp_path / "src" / "huawei_manager"
        src.mkdir(parents=True)
        (src / "constants.py").write_text(
            "USED = 1\nUNUSED = 2\n"
        )
        (src / "app.py").write_text(
            "from constants import USED\nx = USED\n"
        )
        from agents.scans.cross_ref import scan
        result = scan(tmp_path)
        used_names = {i.message.split("'")[1] for i in result.items}
        assert "UNUSED" in used_names
        assert "USED" not in used_names


# ─── deps scanner ────────────────────────────────────────────────────

class TestDepsScan:
    def test_no_pyproject(self, tmp_path: Path) -> None:
        from agents.scans.deps import scan
        result = scan(tmp_path)
        assert isinstance(result, AgentResult)

    def test_stdlib_ignored(self, tmp_path: Path) -> None:
        """Módulos da stdlib não são reportados como dependências em falta."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "mod.py").write_text("import os\nimport sys\nfrom pathlib import Path\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = []\n'
        )
        from agents.scans.deps import scan
        result = scan(tmp_path)
        assert result.status == "ok"

    def test_missing_dep_reported(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "mod.py").write_text("import requests\n")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = []\n'
        )
        from agents.scans.deps import scan
        result = scan(tmp_path)
        assert len(result.items) > 0
        assert "requests" in result.items[0].message


# ─── security scanner ────────────────────────────────────────────────

class TestSecurityScan:
    def test_clean_project(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")
        from agents.scans.security import scan
        result = scan(tmp_path)
        assert result.status == "ok"

    def test_hardcoded_password(self, tmp_path: Path) -> None:
        (tmp_path / "secret.py").write_text(
            'password = "supersecret123"\n'
        )
        from agents.scans.security import scan
        result = scan(tmp_path)
        assert len(result.items) > 0
        assert result.items[0].severity == "error"

    def test_env_file_ignored(self, tmp_path: Path) -> None:
        """Ficheiro .env é intencional (lab) e não deve ser varrido."""
        (tmp_path / ".env").write_text(
            'ADMIN_PASSWORD="lab123"\n'
        )
        from agents.scans.security import scan
        result = scan(tmp_path)
        assert len(result.items) == 0


# ─── runner ──────────────────────────────────────────────────────────

class TestRunner:
    def test_run_all_returns_results(self) -> None:

        from agents.runner import run_all
        results = run_all()
        assert len(results) >= 4
        names = {r.name for r in results}
        for expected in ("dead_code", "structure", "security", "deps", "style", "cross_ref"):
            assert expected in names

    def test_run_all_items_are_agent_results(self) -> None:
        from agents.runner import run_all
        results = run_all()
        for r in results:
            assert isinstance(r, AgentResult)
