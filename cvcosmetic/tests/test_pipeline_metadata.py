"""
Интеграционные тесты пайплайна на реальных метаданных датасета.
OCR не используется — состав берётся напрямую из metadata.json.
Проверяет качество извлечения сущностей и парсинга ингредиентов.
"""
import json
import re
import statistics
from pathlib import Path

import pytest
from conftest import DATASET_PRIMARY, DATASET_BACKUP, load_metadata
from app.extractor import extract_entities, extract_brand_from_title, extract_volume
from app.normalizer import parse_ingredients, normalize_text


def run_pipeline(folder: Path) -> dict:
    """Запускает пайплайн на метаданных одного продукта."""
    data = load_metadata(folder)
    title = data.get("title", "")
    composition = data.get("composition", "")

    candidate, ingredients_raw = extract_entities(title=title, ocr_text=composition)
    if not ingredients_raw and composition:
        ingredients_raw = composition

    parsed = parse_ingredients(ingredients_raw) if ingredients_raw else []
    return {
        "folder": folder.name,
        "title": title,
        "brand": candidate.brand,
        "product_type": candidate.product_type,
        "volume": candidate.volume,
        "barcode": candidate.barcode,
        "ingredients_raw": ingredients_raw,
        "ingredients_parsed": parsed,
        "n_ingredients": len(parsed),
    }


# ─── PRIMARY dataset ──────────────────────────────────────────────────────────

class TestPrimaryPipeline:
    @pytest.fixture(scope="class")
    def results(self, primary_folders):
        import random
        sample = random.Random(42).sample(primary_folders, min(100, len(primary_folders)))
        return [run_pipeline(f) for f in sample]

    def test_brand_extraction_rate(self, results):
        found = sum(1 for r in results if r["brand"])
        rate = found / len(results)
        assert rate >= 0.90, f"Бренд найден у {rate:.1%} продуктов (ожидается ≥ 90%)"

    def test_volume_extraction_rate(self, results):
        found = sum(1 for r in results if r["volume"])
        rate = found / len(results)
        assert rate >= 0.80, f"Объём найден у {rate:.1%} продуктов (ожидается ≥ 80%)"

    def test_product_type_extraction_rate(self, results):
        found = sum(1 for r in results if r["product_type"])
        rate = found / len(results)
        assert rate >= 0.50, f"Тип продукта определён у {rate:.1%} (ожидается ≥ 50%)"

    def test_ingredient_parsing_rate(self, results):
        with_ingredients = [r for r in results if r["ingredients_parsed"]]
        rate = len(with_ingredients) / len(results)
        assert rate >= 0.90, f"Состав разобран у {rate:.1%} (ожидается ≥ 90%)"

    def test_avg_ingredients_count(self, results):
        counts = [r["n_ingredients"] for r in results if r["n_ingredients"] > 0]
        assert counts, "Нет продуктов с ингредиентами"
        avg = statistics.mean(counts)
        assert avg >= 5, f"Среднее кол-во ингредиентов {avg:.1f} — слишком мало"

    def test_no_prefix_in_parsed_ingredients(self, results):
        bad = []
        for r in results:
            for ing in r["ingredients_parsed"]:
                if re.match(r"(?i)^(состав|ingredients?)", ing):
                    bad.append((r["folder"][:40], ing))
        assert not bad, f"Префикс попал в ингредиенты: {bad[:3]}"

    def test_no_empty_ingredients(self, results):
        bad = []
        for r in results:
            for ing in r["ingredients_parsed"]:
                if not ing.strip():
                    bad.append(r["folder"][:40])
                    break
        assert not bad, f"Пустые ингредиенты у {bad[:3]}"

    def test_ingredients_not_too_long(self, results):
        """Один ингредиент не должен быть длиннее 120 символов."""
        long_ones = []
        for r in results:
            for ing in r["ingredients_parsed"]:
                if len(ing) > 120:
                    long_ones.append((r["folder"][:40], ing[:60]))
        # Мягкая проверка: не более 5% слишком длинных
        total = sum(r["n_ingredients"] for r in results)
        ratio = len(long_ones) / total if total else 0
        assert ratio <= 0.05, f"{len(long_ones)} слишком длинных ингредиентов ({ratio:.1%}): {long_ones[:3]}"

    def test_brand_is_uppercase_or_mixed(self, results):
        """Бренды обычно в верхнем регистре или CamelCase."""
        all_lower = [r["brand"] for r in results if r["brand"] and r["brand"] == r["brand"].lower()]
        ratio = len(all_lower) / len(results)
        assert ratio <= 0.10, f"Много брендов в нижнем регистре ({ratio:.1%}): {all_lower[:5]}"

    def test_volume_format_consistent(self, results):
        """Объём должен содержать число и единицу измерения."""
        bad = []
        for r in results:
            if r["volume"]:
                if not re.match(r"[\d.,]+\s*(мл|ml|г|g|oz)", r["volume"], re.I):
                    bad.append((r["folder"][:40], r["volume"]))
        assert not bad, f"Неправильный формат объёма: {bad[:5]}"

    def test_known_brands_recognized(self, primary_folders):
        known = {
            "GARNIER": "Алоэ-крем__GARNIER___SKIN_NATURALS__гиалуроновый_50_мл",
            "BLISTEX": "Бальзам_для_губ__BLISTEX__Medicated__классический_SPF-15__4_25_г",
            "VT": "Ампула_для_лица__VT__REEDLE_SHOT_100_с_микроиглами_6x2_мл",
            "ЧИСТАЯ ЛИНИЯ": "Аква-крем_для_лица__ЧИСТАЯ_ЛИНИЯ__ИДЕАЛЬНАЯ_КОЖА_Мгновенная_матовость_50_мл",
        }
        folder_map = {f.name: f for f in primary_folders}
        for brand, folder_name in known.items():
            if folder_name not in folder_map:
                pytest.skip(f"Тестовый продукт не найден: {folder_name}")
            result = run_pipeline(folder_map[folder_name])
            assert result["brand"] == brand, f"Ожидался бренд {brand!r}, получен {result['brand']!r}"


# ─── BACKUP dataset ───────────────────────────────────────────────────────────

class TestBackupPipeline:
    @pytest.fixture(scope="class")
    def results(self, backup_folders):
        import random
        # Берём только папки с metadata.json
        valid = [f for f in backup_folders if (f / "metadata.json").exists()]
        sample = random.Random(42).sample(valid, min(50, len(valid)))
        return [run_pipeline(f) for f in sample]

    def test_brand_extraction_rate(self, results):
        found = sum(1 for r in results if r["brand"])
        rate = found / len(results)
        assert rate >= 0.85, f"Backup: бренд найден у {rate:.1%}"

    def test_ingredient_parsing_rate(self, results):
        with_ing = [r for r in results if r["ingredients_parsed"]]
        rate = len(with_ing) / len(results)
        assert rate >= 0.85, f"Backup: состав разобран у {rate:.1%}"

    def test_avg_ingredients_count(self, results):
        counts = [r["n_ingredients"] for r in results if r["n_ingredients"] > 0]
        avg = statistics.mean(counts) if counts else 0
        assert avg >= 5, f"Backup: среднее кол-во ингредиентов {avg:.1f}"


# ─── Проверки форматов состава ─────────────────────────────────────────────────

class TestCompositionFormats:
    """Проверяет что все форматы состава из датасета корректно парсятся."""

    BULLET_COMP = (
        "AQUA / WATER • BUTYROSPERMUM PARKII BUTTER / SHEA BUTTER • GLYCERIN • "
        "CAPRYLIC/CAPRIC TRIGLYCERIDE • ALCOHOL DENAT. • STEARYL ALCOHOL • "
        "ZEA MAYS STARCH / CORN STARCH • POLYGLYCERYL-3 METHYLGLUCOSE DISTEARATE"
    )
    COMMA_COMP = (
        "Aqua, Aluminum Starch Octenylsuccinate, Isopropyl Myristate, Glycerin, "
        "Caprylic/Capric Triglyceride, Zinc Sulfate, Panthenol, Limonene."
    )
    MIXED_COMP = (
        "Состав/Ingredients: Aqua, Aluminum Starch Octenylsuccinate, Glycerin, "
        "Zinc Sulfate (сульфат цинка), Panthenol (пантенол), Limonene."
    )
    LOWERCASE_COMP = (
        "Dimethicone 2.0 %, Octinoxate 6.6 %, Octisalate 4.4 %, beeswax, camphor, "
        "cetyl alcohol, cetyl palmitate, mineral oil, white petrolatum."
    )

    def test_comma_separated_parses(self):
        result = parse_ingredients(self.COMMA_COMP)
        assert len(result) >= 6

    def test_mixed_prefix_parses(self):
        result = parse_ingredients(self.MIXED_COMP)
        assert len(result) >= 5
        assert not any("Состав" in x for x in result)

    def test_lowercase_composition_parses(self):
        result = parse_ingredients(self.LOWERCASE_COMP)
        assert len(result) >= 6

    def test_bullet_separator_handled(self):
        """Bullet • не является стандартным разделителем — проверяем поведение."""
        result = parse_ingredients(self.BULLET_COMP)
        # Может разобраться как один блок или несколько — главное не падает
        assert isinstance(result, list)

    def test_real_garnier_from_dataset(self):
        folder = DATASET_PRIMARY / "Алоэ-крем__GARNIER___SKIN_NATURALS__гиалуроновый_50_мл"
        if not folder.exists():
            pytest.skip("Продукт GARNIER не найден в датасете")
        data = load_metadata(folder)
        # Garnier использует bullet • как разделитель
        result = parse_ingredients(data["composition"])
        assert len(result) >= 8, (
            f"Ожидается ≥8 ингредиентов, получено {len(result)}: {result[:5]}"
        )

    def test_real_blistex_from_dataset(self):
        folder = DATASET_PRIMARY / "Бальзам_для_губ__BLISTEX__Medicated__классический_SPF-15__4_25_г"
        if not folder.exists():
            pytest.skip("Продукт BLISTEX не найден")
        data = load_metadata(folder)
        result = parse_ingredients(data["composition"])
        assert len(result) >= 5
