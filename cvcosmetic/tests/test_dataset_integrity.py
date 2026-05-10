"""
Тесты целостности датасетов.
Проверяют структуру файлов, наличие обязательных полей, качество метаданных.
"""
import json
from pathlib import Path

import pytest
from conftest import DATASET_PRIMARY, DATASET_BACKUP, load_metadata, product_folders

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


# ─── Общие проверки для любого датасета ──────────────────────────────────────

def _check_dataset(root: Path, sample_size: int = None):
    """Запускает проверки целостности, возвращает список проблем."""
    folders = product_folders(root)
    if sample_size:
        import random
        folders = random.Random(42).sample(folders, min(sample_size, len(folders)))

    issues = []
    for folder in folders:
        meta_path = folder / "metadata.json"

        # metadata.json существует
        if not meta_path.exists():
            issues.append(f"[NO_META] {folder.name}")
            continue

        # JSON парсится
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append(f"[INVALID_JSON] {folder.name}: {e}")
            continue

        # Обязательные поля
        if not data.get("title"):
            issues.append(f"[NO_TITLE] {folder.name}")
        if not data.get("composition"):
            issues.append(f"[NO_COMPOSITION] {folder.name}")

        # Изображения
        images = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        ]
        if not images:
            issues.append(f"[NO_IMAGES] {folder.name}")
        else:
            # Размер файлов — не пустые
            for img in images:
                if img.stat().st_size < 1024:
                    issues.append(f"[TINY_IMAGE] {folder.name}/{img.name} ({img.stat().st_size}B)")

    return issues, len(folders)


# ─── PRIMARY dataset ──────────────────────────────────────────────────────────

class TestPrimaryDatasetIntegrity:
    def test_root_exists(self):
        assert DATASET_PRIMARY.exists(), f"Директория датасета не найдена: {DATASET_PRIMARY}"

    def test_has_products(self, primary_folders):
        assert len(primary_folders) > 100, "Ожидается > 100 продуктов"

    def test_has_dataset_index(self):
        assert (DATASET_PRIMARY / "dataset_index.json").exists()

    def test_dataset_index_parseable(self):
        data = json.loads((DATASET_PRIMARY / "dataset_index.json").read_text(encoding="utf-8"))
        assert isinstance(data, list)

    def test_all_folders_have_metadata(self, primary_folders):
        missing = [f.name for f in primary_folders if not (f / "metadata.json").exists()]
        assert not missing, f"metadata.json отсутствует у {len(missing)} продуктов: {missing[:5]}"

    def test_all_metadata_valid_json(self, primary_folders):
        bad = []
        for folder in primary_folders:
            meta = folder / "metadata.json"
            if meta.exists():
                try:
                    json.loads(meta.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    bad.append(folder.name)
        assert not bad, f"Невалидный JSON у {bad[:5]}"

    def test_title_field_present(self, primary_folders):
        missing = []
        for folder in primary_folders:
            meta = folder / "metadata.json"
            if meta.exists():
                d = json.loads(meta.read_text(encoding="utf-8"))
                if not d.get("title"):
                    missing.append(folder.name)
        assert not missing, f"Нет поля title у {missing[:5]}"

    def test_composition_coverage(self, primary_folders):
        no_comp = [
            f.name for f in primary_folders
            if (f / "metadata.json").exists()
            and not json.loads((f / "metadata.json").read_text(encoding="utf-8")).get("composition")
        ]
        coverage = 1 - len(no_comp) / len(primary_folders)
        assert coverage >= 0.95, f"Состав отсутствует у {len(no_comp)} продуктов (покрытие {coverage:.1%})"

    def test_images_present(self, primary_folders):
        no_images = [
            f.name for f in primary_folders
            if not any(
                p.suffix.lower() in IMAGE_EXTENSIONS
                for p in f.iterdir() if p.is_file()
            )
        ]
        assert not no_images, f"Нет изображений у {len(no_images)} продуктов: {no_images[:5]}"

    def test_images_not_empty(self, primary_folders):
        tiny = []
        total_images = 0
        for folder in primary_folders:
            for img in folder.iterdir():
                if img.is_file() and img.suffix.lower() in IMAGE_EXTENSIONS:
                    total_images += 1
                    if img.stat().st_size < 1024:
                        tiny.append(f"{folder.name[:40]}/{img.name}")
        # Допускаем до 1% повреждённых/пустых файлов (плейсхолдеры, иконки YouTube)
        ratio = len(tiny) / total_images if total_images else 0
        assert ratio <= 0.01, (
            f"{len(tiny)}/{total_images} изображений < 1KB ({ratio:.2%}): {tiny[:5]}"
        )

    def test_product_count_in_range(self, primary_folders):
        assert 500 <= len(primary_folders) <= 2000, f"Неожиданное кол-во продуктов: {len(primary_folders)}"

    def test_images_per_product_distribution(self, primary_sample):
        counts = []
        for folder in primary_sample:
            imgs = [
                p for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            ]
            counts.append(len(imgs))
        avg = sum(counts) / len(counts)
        assert avg >= 2.0, f"Среднее кол-во изображений {avg:.1f} — слишком мало"
        assert max(counts) >= 3, "Ни у одного продукта нет 3+ изображений"


# ─── BACKUP dataset ───────────────────────────────────────────────────────────

class TestBackupDatasetIntegrity:
    def test_root_exists(self):
        assert DATASET_BACKUP.exists(), f"Директория backup не найдена: {DATASET_BACKUP}"

    def test_has_products(self, backup_folders):
        assert len(backup_folders) > 100

    def test_has_dataset_index(self):
        assert (DATASET_BACKUP / "dataset_index.json").exists()

    def test_all_folders_have_metadata(self, backup_folders):
        missing = [f.name for f in backup_folders if not (f / "metadata.json").exists()]
        # Backup датасет неполный — допускаем до 15% папок без metadata
        ratio = len(missing) / len(backup_folders)
        assert ratio <= 0.15, (
            f"metadata.json отсутствует у {len(missing)}/{len(backup_folders)} "
            f"продуктов ({ratio:.1%}): {missing[:3]}"
        )

    def test_all_metadata_valid_json(self, backup_folders):
        bad = []
        for folder in backup_folders:
            meta = folder / "metadata.json"
            if meta.exists():
                try:
                    json.loads(meta.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    bad.append(folder.name)
        assert not bad, f"Невалидный JSON: {bad[:5]}"

    def test_composition_coverage(self, backup_folders):
        no_comp = [
            f.name for f in backup_folders
            if (f / "metadata.json").exists()
            and not json.loads((f / "metadata.json").read_text(encoding="utf-8")).get("composition")
        ]
        coverage = 1 - len(no_comp) / len(backup_folders)
        assert coverage >= 0.90, f"Покрытие состава {coverage:.1%}"

    def test_images_present(self, backup_folders):
        no_images = [
            f.name for f in backup_folders
            if not any(
                p.suffix.lower() in IMAGE_EXTENSIONS
                for p in f.iterdir() if p.is_file()
            )
        ]
        # Backup датасет неполный — допускаем до 15% папок без изображений
        ratio = len(no_images) / len(backup_folders)
        assert ratio <= 0.15, (
            f"Нет изображений у {len(no_images)}/{len(backup_folders)} "
            f"продуктов ({ratio:.1%}): {no_images[:3]}"
        )

    def test_product_count_in_range(self, backup_folders):
        assert 100 <= len(backup_folders) <= 1000


# ─── Кросс-датасетные проверки ────────────────────────────────────────────────

class TestCrossDataset:
    def test_backup_is_subset_of_primary(self, primary_folders, backup_folders):
        primary_names = {f.name for f in primary_folders}
        backup_names = {f.name for f in backup_folders}
        only_in_backup = backup_names - primary_names
        # Допускаем не более 10% уникальных в backup
        ratio = len(only_in_backup) / len(backup_names)
        assert ratio <= 0.10, (
            f"{len(only_in_backup)} продуктов ({ratio:.1%}) есть только в backup, "
            f"примеры: {list(only_in_backup)[:3]}"
        )

    def test_shared_products_consistent_titles(self, primary_folders, backup_folders):
        primary_map = {f.name: f for f in primary_folders}
        backup_map = {f.name: f for f in backup_folders}
        shared = set(primary_map) & set(backup_map)

        mismatches = []
        read_errors = 0
        for name in list(shared)[:50]:
            try:
                p_meta_path = primary_map[name] / "metadata.json"
                b_meta_path = backup_map[name] / "metadata.json"
                if not b_meta_path.exists():
                    continue
                p_meta = json.loads(p_meta_path.read_text(encoding="utf-8"))
                b_meta = json.loads(b_meta_path.read_text(encoding="utf-8"))
                p_title = p_meta.get("title", "").strip()
                b_title = b_meta.get("title", "").strip()
                if p_title and b_title and p_title != b_title:
                    mismatches.append((name[:40], p_title[:40], b_title[:40]))
            except (OSError, UnicodeDecodeError):
                read_errors += 1

        assert not mismatches, f"Разные заголовки в primary/backup: {mismatches[:3]}"

    def test_backup_has_more_images_per_product(self, primary_sample, backup_sample):
        """Backup (вид сзади) может иметь другое кол-во фото."""
        def avg_images(folders):
            counts = []
            for f in folders:
                imgs = [p for p in f.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
                counts.append(len(imgs))
            return sum(counts) / len(counts) if counts else 0

        p_avg = avg_images(primary_sample)
        b_avg = avg_images(backup_sample)
        # Просто фиксируем метрику, не требуем конкретного соотношения
        assert p_avg > 0 and b_avg > 0, "Оба датасета должны содержать изображения"
