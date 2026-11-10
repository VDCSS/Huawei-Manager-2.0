"""Testes para ausência de artefatos `,cover` no repositório."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["src", "tests", "agents"]
COVER_PATTERN = "*,cover"


def test_no_cover_artifacts_in_tracked_dirs() -> None:
    """Nenhum arquivo `,cover` (artefato de `coverage annotate`) deve existir.

    Arquivos `,cover` são resíduos do `coverage annotate` e não podem
    se acumular no working tree. Se este teste falhar, rode `make clean`
    (que agora remove `,cover`) ou delete os arquivos manualmente.
    """
    cover_files: list[Path] = []
    for dirname in SCAN_DIRS:
        scan_root = ROOT / dirname
        if not scan_root.exists():
            continue
        cover_files.extend(sorted(scan_root.rglob(COVER_PATTERN)))
    assert cover_files == [], (
        f"Encontrados {len(cover_files)} arquivos ',cover'. "
        "Rode `make clean` ou delete manualmente:\n"
        + "\n".join(str(p) for p in cover_files)
    )
