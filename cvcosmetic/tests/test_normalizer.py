"""Юнит-тесты модуля normalizer."""
import pytest
from app.normalizer import normalize_text, normalize_ingredient, parse_ingredients


class TestNormalizeText:
    def test_collapses_multiple_spaces(self):
        assert normalize_text("Aqua    Glycerin") == "Aqua Glycerin"

    def test_strips_edges(self):
        assert normalize_text("  Hello  ") == "Hello"

    def test_collapses_blank_lines(self):
        result = normalize_text("A\n\n\n\nB")
        assert "\n\n\n" not in result

    def test_preserves_newline(self):
        assert "\n" in normalize_text("Line1\nLine2")

    def test_removes_control_chars(self):
        assert normalize_text("A\x00B\x01C") == "ABC"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_unicode_nfc(self):
        # Составной символ е (е + combining) → NFC
        import unicodedata
        decomposed = unicodedata.normalize("NFD", "Аёжё")
        result = normalize_text(decomposed)
        assert unicodedata.is_normalized("NFC", result)


class TestNormalizeIngredient:
    def test_strips_whitespace(self):
        assert normalize_ingredient("  Aqua  ") == "Aqua"

    def test_removes_trailing_asterisk(self):
        assert normalize_ingredient("Glycerin**") == "Glycerin"

    def test_removes_russian_parenthetical(self):
        result = normalize_ingredient("Zinc Sulfate (сульфат цинка)")
        assert "сульфат" not in result
        assert "Zinc Sulfate" in result

    def test_keeps_english_parenthetical(self):
        result = normalize_ingredient("Butyrospermum Parkii (Shea Butter)")
        assert "Shea Butter" in result

    def test_capitalizes_first_letter(self):
        assert normalize_ingredient("aqua").startswith("A")

    def test_strips_leading_comma(self):
        assert not normalize_ingredient(",Aqua").startswith(",")

    def test_empty_returns_empty(self):
        assert normalize_ingredient("") == ""

    def test_short_noise_preserved(self):
        # Короткие легитимные ингредиенты типа "CI"
        result = normalize_ingredient("CI")
        assert result == "CI"


class TestParseIngredients:
    COMMA_LIST = "Aqua, Glycerin, Panthenol, Niacinamide"
    SEMICOLON_LIST = "Aqua; Glycerin; Panthenol"
    WITH_RU_PREFIX = "Состав: Aqua, Glycerin, Zinc Sulfate (сульфат цинка)"
    WITH_EN_PREFIX = "Ingredients: Aqua, Glycerin, Panthenol"
    WITH_BOTH_PREFIX = "Состав/Ingredients: Aqua, Glycerin, Panthenol"
    BULLET_SEPARATED = "AQUA / WATER • GLYCERIN • PANTHENOL • NIACINAMIDE"

    def test_comma_separated(self):
        result = parse_ingredients(self.COMMA_LIST)
        assert "Aqua" in result
        assert "Glycerin" in result
        assert "Panthenol" in result
        assert "Niacinamide" in result
        assert len(result) == 4

    def test_semicolon_separated(self):
        result = parse_ingredients(self.SEMICOLON_LIST)
        assert len(result) == 3

    def test_removes_russian_prefix(self):
        result = parse_ingredients(self.WITH_RU_PREFIX)
        assert not any("Состав" in x for x in result)
        assert "Aqua" in result

    def test_removes_english_prefix(self):
        result = parse_ingredients(self.WITH_EN_PREFIX)
        assert not any("Ingredient" in x for x in result)

    def test_removes_bilingual_prefix(self):
        result = parse_ingredients(self.WITH_BOTH_PREFIX)
        assert not any("Состав" in x for x in result)
        assert "Aqua" in result

    def test_no_empty_items(self):
        result = parse_ingredients("Aqua, , Glycerin, , Panthenol")
        assert all(len(x) >= 2 for x in result)

    def test_real_garnier_composition(self):
        comp = (
            "AQUA / WATER, BUTYROSPERMUM PARKII BUTTER / SHEA BUTTER, GLYCERIN, "
            "CAPRYLIC/CAPRIC TRIGLYCERIDE, ALCOHOL DENAT., STEARYL ALCOHOL"
        )
        result = parse_ingredients(comp)
        assert len(result) >= 5
        assert any("Aqua" in x or "AQUA" in x for x in result)

    def test_real_ru_en_mixed_composition(self):
        comp = (
            "Состав/Ingredients: Aqua, Aluminum Starch Octenylsuccinate, "
            "Glycerin, Zinc Sulfate (сульфат цинка), Panthenol (пантенол), Limonene."
        )
        result = parse_ingredients(comp)
        assert len(result) >= 5
        assert not any("Состав" in x for x in result)
        assert any("Zinc Sulfate" in x for x in result)
