from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from huawei_manager.utils import clean_output, sanitize_command


class TestUtils(unittest.TestCase):

    def test_clean_output_ansi(self):
        raw = "\x1b[32mOK\x1b[0m"
        self.assertEqual(clean_output(raw), "OK")

    def test_clean_output_ctrl_chars(self):
        raw = "test\r\x08more"
        self.assertEqual(clean_output(raw), "testmore")

    def test_clean_output_more_prompt(self):
        raw = "output\n---- More ----"
        self.assertEqual(clean_output(raw), "output")

    def test_clean_output_strip(self):
        raw = "  text with spaces  \n"
        self.assertEqual(clean_output(raw), "text with spaces")

    def test_sanitize_password(self):
        cmd = "configure password=secret123"
        result = sanitize_command(cmd)
        self.assertIn("password=***", result)
        self.assertNotIn("secret123", result)

    def test_sanitize_key(self):
        cmd = "set key=abc123"
        result = sanitize_command(cmd)
        self.assertIn("key=***", result)
        self.assertNotIn("abc123", result)

    def test_sanitize_normal_cmd(self):
        cmd = "display ip routing-table"
        result = sanitize_command(cmd)
        self.assertEqual(result, cmd)

    def test_sanitize_empty(self):
        self.assertEqual(sanitize_command(""), "")


if __name__ == "__main__":
    unittest.main()
