from huawei_manager.utils import clean_output, sanitize_command


class TestCleanOutput:
    def test_ansi_stripped(self):
        assert clean_output("\x1b[32mOK\x1b[0m") == "OK"

    def test_ctrl_chars(self):
        assert clean_output("test\r\x08more") == "testmore"

    def test_more_prompt_stripped(self):
        assert clean_output("output\n---- More ----") == "output"

    def test_stripped(self):
        assert clean_output("  text with spaces  \n") == "text with spaces"

    def test_empty(self):
        assert clean_output("") == ""

    def test_already_clean(self):
        assert clean_output("clean text") == "clean text"

    def test_multiple_more_prompts(self):
        assert clean_output("line1\n---- More ----\nline2\n---- More ----") == "line1\n\nline2"

    def test_multiple_ctrl_chars(self):
        assert clean_output("\r\x08a\r\x08b") == "ab"


class TestSanitizeCommand:
    def test_password(self):
        result = sanitize_command("configure password=secret123")
        assert "password=***" in result
        assert "secret123" not in result

    def test_key(self):
        result = sanitize_command("set key=abc123")
        assert "key=***" in result
        assert "abc123" not in result

    def test_normal_cmd(self):
        cmd = "display ip routing-table"
        assert sanitize_command(cmd) == cmd

    def test_empty(self):
        assert sanitize_command("") == ""

    def test_token(self):
        result = sanitize_command("set token=abc123")
        assert "token=***" in result
        assert "abc123" not in result

    def test_auth(self):
        result = sanitize_command("set auth=basic")
        assert "auth=***" in result
        assert "basic" not in result

    def test_multiple_sensitive_fields(self):
        result = sanitize_command("password=secret1 token=secret2 key=secret3")
        assert "password=***" in result
        assert "token=***" in result
        assert "key=***" in result
