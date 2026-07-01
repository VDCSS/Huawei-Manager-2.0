from huawei_manager.constants import (
    CLI_FILTERS,
    CMD_TEMPLATES,
    FONT_BODY,
    FONT_H1,
    THEME,
)
from huawei_manager.services import VNF_CATEGORIES, VNF_TYPES


class TestTheme:
    def test_has_expected_keys(self):
        expected = {"BG_BASE", "BG_CARD", "BG_SIDEBAR", "FG_MAIN", "NEON_CYAN"}
        assert expected.issubset(THEME.keys())

    def test_bg_is_string(self):
        assert isinstance(THEME["BG_BASE"], str)


class TestFonts:
    def test_font_body_is_tuple(self):
        assert isinstance(FONT_BODY, tuple)
        assert len(FONT_BODY) == 2

    def test_font_sizes_are_positive(self):
        for f in [FONT_BODY, FONT_H1]:
            assert f[1] > 0


class TestCLIFilters:
    def test_has_expected_keys(self):
        assert "routing" in CLI_FILTERS
        assert "interfaces" in CLI_FILTERS

    def test_values_are_strings(self):
        for v in CLI_FILTERS.values():
            assert isinstance(v, str)


class TestVnfCategories:
    def test_all_types_have_categories(self):
        for t in VNF_TYPES:
            assert t in VNF_CATEGORIES, f"{t} missing from VNF_CATEGORIES"

    def test_categories_are_non_empty(self):
        for t, cats in VNF_CATEGORIES.items():
            assert len(cats) > 0, f"{t} has no categories"


class TestCmdTemplates:
    def test_not_empty(self):
        assert len(CMD_TEMPLATES) > 0

    def test_values_are_strings(self):
        for v in CMD_TEMPLATES.values():
            assert isinstance(v, str)
