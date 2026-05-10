"""Общие фикстуры и константы для всех тестов."""
import json
import sys
from pathlib import Path

import pytest

# Добавляем корень пакета в sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DATASET_PRIMARY = Path(r"C:\Users\VitoScaletto\OneDrive\Рабочий стол\CVCosmetic\product_dataset")
DATASET_BACKUP = Path(
    r"C:\Users\VitoScaletto\OneDrive\Рабочий стол\CVCosmetic"
    r"\product_dataset_backup-20260421T153504Z-3-001\product_dataset_backup"
)


def load_metadata(folder: Path) -> dict:
    meta = folder / "metadata.json"
    return json.loads(meta.read_text(encoding="utf-8"))


def product_folders(dataset_root: Path) -> list[Path]:
    return sorted(p for p in dataset_root.iterdir() if p.is_dir())


@pytest.fixture(scope="session")
def primary_folders():
    return product_folders(DATASET_PRIMARY)


@pytest.fixture(scope="session")
def backup_folders():
    return product_folders(DATASET_BACKUP)


@pytest.fixture(scope="session")
def primary_sample(primary_folders):
    """50 случайных продуктов из основного датасета."""
    import random
    rng = random.Random(42)
    return rng.sample(primary_folders, min(50, len(primary_folders)))


@pytest.fixture(scope="session")
def backup_sample(backup_folders):
    """50 случайных продуктов из backup датасета."""
    import random
    rng = random.Random(42)
    return rng.sample(backup_folders, min(50, len(backup_folders)))
