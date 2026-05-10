"""
Батч-тест пайплайна на локальном датасете без Docker.
Запуск: python batch_test.py [--limit 10]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.extractor import extract_entities
from app.normalizer import normalize_text, parse_ingredients
from app.ocr import ocr_from_path

DATASET_ROOT = Path(__file__).parent.parent / "product_dataset"


def process_product(folder: Path) -> dict:
    meta_path = folder / "metadata.json"
    if not meta_path.exists():
        return {"folder": folder.name, "error": "metadata.json not found"}

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    title = meta.get("title", "")
    composition_from_meta = meta.get("composition", "")

    # Берём первое изображение для OCR
    images = [p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    ocr_text = ""
    if images:
        try:
            ocr_text, _ = ocr_from_path(str(images[0]))
            ocr_text = normalize_text(ocr_text)
        except Exception as e:
            ocr_text = ""
            print(f"  OCR error: {e}")

    # Если OCR не нашёл состав — используем состав из метаданных
    candidate, ingredients_raw = extract_entities(title=title, ocr_text=ocr_text)
    if not ingredients_raw and composition_from_meta:
        ingredients_raw = composition_from_meta

    ingredients_parsed = parse_ingredients(ingredients_raw) if ingredients_raw else []

    return {
        "folder": folder.name,
        "title": title,
        "productCandidate": candidate.model_dump(),
        "ingredientsRaw": ingredients_raw,
        "ingredientsParsed": ingredients_parsed,
        "ingredientsCount": len(ingredients_parsed),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5, help="Количество продуктов для обработки")
    parser.add_argument("--output", default="batch_results.json")
    args = parser.parse_args()

    folders = [p for p in DATASET_ROOT.iterdir() if p.is_dir()][:args.limit]
    print(f"Обрабатываем {len(folders)} продуктов...")

    results = []
    for i, folder in enumerate(folders, 1):
        print(f"[{i}/{len(folders)}] {folder.name[:60]}...")
        result = process_product(folder)
        results.append(result)
        print(f"  Бренд: {result.get('productCandidate', {}).get('brand')}")
        print(f"  Ингредиентов: {result.get('ingredientsCount', 0)}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nРезультаты сохранены в {args.output}")


if __name__ == "__main__":
    main()
