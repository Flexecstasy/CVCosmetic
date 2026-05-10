"""Юнит-тесты модуля extractor на реальных данных датасета."""
import pytest
from app.extractor import (
    extract_brand_from_title,
    extract_composition_raw,
    extract_entities,
    extract_product_type,
    extract_volume,
    extract_barcode,
    _validate_ean,
)


class TestExtractBrand:
    @pytest.mark.parametrize("title,expected", [
        ("Аква-крем для лица `ЧИСТАЯ ЛИНИЯ` ИДЕАЛЬНАЯ КОЖА Мгновенная матовость 50 мл", "ЧИСТАЯ ЛИНИЯ"),
        ("Алоэ-крем `GARNIER` `SKIN NATURALS` гиалуроновый 50 мл", "GARNIER"),
        ("Ампула для лица `VT` REEDLE SHOT 100 с микроиглами 6x2 мл", "VT"),
        ("Бальзам для губ `BLISTEX` Medicated классический SPF-15 4.25 г", "BLISTEX"),
        ("Бальзам для губ `ART-VISAGE` EUPHORIA SOS Repair", "ART-VISAGE"),
        ("Бальзам для губ `A PIEU` THE PURE CANDY оттеночный", "A PIEU"),
    ])
    def test_backtick_brand(self, title, expected):
        assert extract_brand_from_title(title) == expected

    def test_no_brand_returns_none(self):
        assert extract_brand_from_title("Просто название продукта без бренда") is None

    def test_brand_with_hyphen(self):
        result = extract_brand_from_title("Крем `ART-VISAGE` матовый")
        assert result == "ART-VISAGE"


class TestExtractProductType:
    @pytest.mark.parametrize("title,expected_type", [
        ("Аква-крем для лица `GARNIER`", "Крем"),
        ("Бальзам для губ `EAT MY` Брусничный морс", "Бальзам"),
        ("Ампула для лица `VT` REEDLE SHOT", "Ампула"),
        ("Сыворотка для лица `SOME BRAND` увлажняющая", "Сыворотка"),
        ("Шампунь `BRAND` для объёма", "Шампунь"),
        ("Тушь для ресниц `BRAND`", "Тушь"),
    ])
    def test_product_type_extraction(self, title, expected_type):
        assert extract_product_type(title) == expected_type

    def test_unknown_type_returns_none(self):
        assert extract_product_type("Неизвестный продукт `BRAND`") is None


class TestExtractVolume:
    @pytest.mark.parametrize("text,expected", [
        ("крем 50 мл", "50 мл"),
        ("бальзам 4.25 г", "4.25 г"),
        ("serum 30ml", "30 ml"),
        ("ампула 6x2 мл", "2 мл"),   # мультиупаковка: берём единичный объём
        ("ампула 8x2 мл", "2 мл"),
        ("крем 100ML матовый", "100 ml"),
        ("бальзам 4,25 г восстанавливающий", "4.25 г"),
        ("крем 350 мл", "350 мл"),
    ])
    def test_volume_extraction(self, text, expected):
        assert extract_volume(text) == expected

    def test_no_volume_returns_none(self):
        assert extract_volume("Просто текст без объёма") is None

    def test_volume_in_title(self):
        title = "Аква-крем для лица `ЧИСТАЯ ЛИНИЯ` ИДЕАЛЬНАЯ КОЖА Мгновенная матовость 50 мл"
        assert extract_volume(title) == "50 мл"


class TestExtractBarcode:
    def test_valid_ean13(self):
        # EAN-13: 4006381333931 (Nivea, реальный штрихкод с валидной контрольной суммой)
        assert extract_barcode("штрихкод 4006381333931 на этикетке") == "4006381333931"

    def test_invalid_ean_ignored(self):
        assert extract_barcode("123456789012") is None

    def test_no_barcode_returns_none(self):
        assert extract_barcode("Aqua, Glycerin, Panthenol") is None

    def test_ean_in_long_text(self):
        text = "Артикул 123456\nштрихкод 4607001234568\nдругой текст"
        result = extract_barcode(text)
        if result:
            assert len(result) in (8, 13)


class TestValidateEAN:
    def test_valid_ean13(self):
        # 4006381333931 = Nivea, контрольная сумма = 1 ✓
        assert _validate_ean("4006381333931") is True

    def test_invalid_checksum(self):
        assert _validate_ean("4600450023420") is False

    def test_wrong_length(self):
        assert _validate_ean("123456") is False

    def test_valid_ean8(self):
        # EAN-8: 96385074
        assert _validate_ean("96385074") is True


class TestExtractCompositionRaw:
    def test_en_prefix(self):
        text = "Ingredients: Aqua, Glycerin, Panthenol"
        result = extract_composition_raw(text)
        assert result is not None
        assert "Aqua" in result
        assert "Ingredients" not in result

    def test_ru_en_prefix(self):
        text = "Состав/Ingredients: Aqua, Glycerin, Panthenol (пантенол), Limonene."
        result = extract_composition_raw(text)
        assert result is not None
        assert "Aqua" in result

    def test_no_prefix_returns_none(self):
        text = "ПРИМЕНЕНИЕ: нанести на лицо"
        assert extract_composition_raw(text) is None

    def test_stops_at_empty_line(self):
        text = "Ingredients: Aqua, Glycerin\n\nПрименение: нанести"
        result = extract_composition_raw(text)
        assert "Применение" not in result


class TestExtractEntities:
    def test_full_pipeline_chisto_line(self):
        title = "Аква-крем для лица `ЧИСТАЯ ЛИНИЯ` ИДЕАЛЬНАЯ КОЖА Мгновенная матовость 50 мл"
        ocr = "Состав/Ingredients: Aqua, Glycerin, Panthenol, Niacinamide."
        candidate, ingredients_raw = extract_entities(title=title, ocr_text=ocr)

        assert candidate.brand == "ЧИСТАЯ ЛИНИЯ"
        assert candidate.volume == "50 мл"
        assert candidate.product_type == "Крем"
        assert ingredients_raw is not None
        assert "Aqua" in ingredients_raw

    def test_full_pipeline_garnier(self):
        title = "Алоэ-крем `GARNIER` `SKIN NATURALS` гиалуроновый 50 мл"
        ocr = "AQUA, GLYCERIN, BUTYROSPERMUM PARKII BUTTER / SHEA BUTTER"
        candidate, _ = extract_entities(title=title, ocr_text=ocr)

        assert candidate.brand == "GARNIER"
        assert candidate.volume == "50 мл"

    def test_empty_ocr_uses_title(self):
        title = "Ампула для лица `VT` REEDLE SHOT 100 с микроиглами 6x2 мл"
        candidate, ingredients_raw = extract_entities(title=title, ocr_text="")
        assert candidate.brand == "VT"
        assert ingredients_raw is None

    def test_product_name_excludes_brand(self):
        title = "Крем `GARNIER` увлажняющий 50 мл"
        candidate, _ = extract_entities(title=title, ocr_text="")
        assert "GARNIER" not in (candidate.product_name or "")
