"""Testes para o script scripts/encrypt-env.sh — regeneração sem merge.

O script deve REGENERAR o .env.enc a partir do .env: chaves removidas do
.env não podem sobreviver ao re-encrypt (bug de merge do store antigo).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from huawei_manager.vault import CryptoEnvBackend

REPO_ROOT = Path(__file__).resolve().parent.parent
ENCRYPT_SCRIPT = REPO_ROOT / "scripts" / "encrypt-env.sh"


def _run_encrypt(env_file: Path, out_file: Path, key: str) -> subprocess.CompletedProcess:
    """Executa encrypt-env.sh com SECRETS_KEY e caminhos de arquivo explícitos."""
    env = dict(os.environ)
    env["SECRETS_KEY"] = key
    # Garante que `python3` resolva para o mesmo interpretador que roda o pytest
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [str(ENCRYPT_SCRIPT), str(env_file), str(out_file)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"encrypt-env.sh falhou:\n{result.stdout}\n{result.stderr}"
    return result


class TestEncryptEnvRegeneratesStore:
    """O script deve regenerar o store do zero, sem preservar chaves antigas."""

    def test_removed_keys_do_not_survive_re_encryption(self, tmp_path) -> None:
        """Chave removida do .env não deve permanecer no .env.enc após re-encrypt."""
        env_file = tmp_path / ".env"
        out_file = tmp_path / ".env.enc"
        key = "k" * 32

        env_file.write_text("ROUTER_HOST=10.0.0.1\nSSH_PASSWORD=antiga\n", encoding="utf-8")
        _run_encrypt(env_file, out_file, key)
        store1 = json.loads(out_file.read_text(encoding="utf-8"))
        assert "SSH_PASSWORD" in store1, "Primeira rodada deve conter SSH_PASSWORD"

        # Rotação: SSH_PASSWORD sai do .env; VNF_ENCRYPT_KEY entra
        env_file.write_text(
            "ROUTER_HOST=10.0.0.1\nVNF_ENCRYPT_KEY=chave_fernet\n", encoding="utf-8"
        )
        _run_encrypt(env_file, out_file, key)

        store2 = json.loads(out_file.read_text(encoding="utf-8"))
        assert set(store2) == {"ROUTER_HOST", "VNF_ENCRYPT_KEY"}, (
            f"Chaves removidas do .env não devem sobreviver à regeneração: {sorted(store2)}"
        )

    def test_key_rotation_keeps_current_keys_readable(self, tmp_path) -> None:
        """Após trocar a SECRETS_KEY, o store final deve ter só chaves atuais, legíveis."""
        env_file = tmp_path / ".env"
        out_file = tmp_path / ".env.enc"

        env_file.write_text("ROUTER_HOST=10.0.0.1\nSSH_PASSWORD=antiga\n", encoding="utf-8")
        _run_encrypt(env_file, out_file, "k" * 32)

        env_file.write_text(
            "ROUTER_HOST=10.0.0.1\nVNF_ENCRYPT_KEY=chave_fernet\n", encoding="utf-8"
        )
        new_key = "n" * 32
        _run_encrypt(env_file, out_file, new_key)

        backend = CryptoEnvBackend(encryption_key=new_key, storage_path=out_file)
        assert backend.get("ROUTER_HOST") == "10.0.0.1"
        assert backend.get("VNF_ENCRYPT_KEY") == "chave_fernet"
        assert backend.get("SSH_PASSWORD", "NAO_EXISTE") == "NAO_EXISTE"
