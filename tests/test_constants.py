from huawei_manager.constants import (
    CLI_FILTERS,
    CMD_TEMPLATES,
    FONT_BODY,
    FONT_CANVAS_BODY,
    FONT_CAPTION,
    FONT_H1,
    FONT_SUBHEAD,
    FONT_TITLE,
    THEME,
)
from huawei_manager.services import DEVICE_CATEGORIES, DEVICE_TYPES


class TestTheme:
    def test_has_expected_keys(self):
        expected = {"BG_BASE", "BG_CARD", "BG_SIDEBAR", "FG_MAIN", "NEON_CYAN"}
        assert expected.issubset(THEME.keys())

    def test_bg_is_string(self):
        assert isinstance(THEME["BG_BASE"], str)


class TestFonts:
    def test_canvas_font_body_is_tuple(self):
        assert isinstance(FONT_CANVAS_BODY, tuple)
        assert len(FONT_CANVAS_BODY) == 2

    def test_canvas_font_sizes_are_positive(self):
        for f in [FONT_CANVAS_BODY, FONT_H1]:
            assert f[1] > 0

    def test_ui_scale_is_positive_ints(self):
        for size in [FONT_CAPTION, FONT_BODY, FONT_SUBHEAD, FONT_TITLE]:
            assert isinstance(size, int)
            assert size > 0

    def test_ui_scale_is_ascending(self):
        assert FONT_CAPTION < FONT_BODY < FONT_SUBHEAD < FONT_TITLE


class TestCLIFilters:
    def test_has_expected_keys(self):
        assert "routing" in CLI_FILTERS
        assert "interfaces" in CLI_FILTERS

    def test_values_are_strings(self):
        for v in CLI_FILTERS.values():
            assert isinstance(v, str)


class TestDeviceCategories:
    def test_all_types_have_categories(self):
        for t in DEVICE_TYPES:
            assert t in DEVICE_CATEGORIES, f"{t} missing from DEVICE_CATEGORIES"

    def test_categories_are_non_empty(self):
        for t, cats in DEVICE_CATEGORIES.items():
            assert len(cats) > 0, f"{t} has no categories"


class TestCmdTemplates:
    def test_not_empty(self):
        assert len(CMD_TEMPLATES) > 0

    def test_values_are_strings(self):
        for v in CMD_TEMPLATES.values():
            assert isinstance(v, str)
