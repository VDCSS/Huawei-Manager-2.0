from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from huawei_manager.vault import EnvBackend, SopsBackend


class TestEnvBackend(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["TEST_VAULT_KEY"] = "test_value_123"

    def test_get_existing_key(self):
        backend = EnvBackend()
        self.assertEqual(backend.get("TEST_VAULT_KEY"), "test_value_123")

    def test_get_missing_key_default(self):
        backend = EnvBackend()
        self.assertEqual(backend.get("NONEXISTENT_KEY", "fallback"), "fallback")

    def test_get_missing_key_empty_default(self):
        backend = EnvBackend()
        self.assertEqual(backend.get("NONEXISTENT_KEY"), "")

    def test_backend_name(self):
        backend = EnvBackend()
        self.assertEqual(backend.backend_name, "env (.env)")

    def test_put_and_get(self):
        backend = EnvBackend()
        backend.put("TEST_PUT_KEY", "put_value")
        self.assertEqual(backend.get("TEST_PUT_KEY"), "put_value")
        if hasattr(backend, "_env_path") and backend._env_path.exists():
            lines = backend._env_path.read_text().splitlines()
            has_line = any("TEST_PUT_KEY=" in l for l in lines)
            self.assertTrue(has_line)


class TestSopsBackend(unittest.TestCase):

    def test_init_no_secret_file(self):
        import tempfile, os
        orig = Path("secrets.enc.yaml")
        if not orig.exists():
            self.skipTest("secrets.enc.yaml not present")
        tmp = orig.with_suffix(".yaml.bak")
        orig.rename(tmp)
        try:
            with self.assertRaises(RuntimeError):
                SopsBackend()
        finally:
            tmp.rename(orig)


if __name__ == "__main__":
    unittest.main()
