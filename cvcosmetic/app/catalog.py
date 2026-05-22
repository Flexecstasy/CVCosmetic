import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from .extractor import (
    extract_brand_from_title,
    extract_product_type,
    extract_volume,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = str(Path(__file__).resolve().parents[1] / "catalog.db")
_DB_PATH = Path(os.getenv("CVCOSMETIC_CATALOG_DB", _DEFAULT_DB_PATH))
_MIN_SCORE = float(os.getenv("CVCOSMETIC_CATALOG_MIN_SCORE", "0.38"))

_COMMON_TOKEN_MAP: tuple[tuple[str, str], ...] = (
    # Product types
    ("moisturiser", "крем"),
    ("moisturizer", "крем"),
    ("cream", "крем"),
    ("creme", "крем"),
    ("gel", "гель"),
    ("serum", "сыворотка"),
    ("toner", "тоник"),
    ("lotion", "лосьон"),
    ("mask", "маска"),
    ("cleanser", "очищение"),
    ("foam", "пенка"),
    ("shampoo", "шампунь"),
    ("conditioner", "кондиционер"),
    ("balm", "бальзам"),
    ("scrub", "скраб"),
    ("patches", "патчи"),
    ("patch", "патчи"),
    ("facial", "лица"),
    ("face", "лица"),
    ("body", "тела"),
    ("hair", "волос"),
    ("skin", "кожи"),
    ("vitamin", "витамин"),
    ("glow", "сияние"),
    ("spot", "пятна"),
    ("correcting", "корректирующий"),
    ("correctin", "корректирующий"),
    ("anti", "против"),
    ("breakout", "высыпаний"),
    ("hydrating", "увлажняющий"),
    ("moisturizing", "увлажняющий"),
    ("nourishing", "питательный"),
    ("soothing", "успокаивающий"),
    ("calming", "успокаивающий"),
    ("repair", "восстанавливающий"),
    ("restoring", "восстанавливающий"),
    ("brightening", "осветляющий"),
    ("mattifying", "матирующий"),
    ("purifying", "очищающий"),
    ("firming", "лифтинг"),
    ("lifting", "лифтинг"),
    ("antiaging", "антивозрастной"),
    ("anti-age", "антивозрастной"),
    ("sensitive", "чувствительной"),
    ("hyaluron", "гиалуроновый"),
    ("niacinamide", "ниацинамид"),
    ("panthenol", "пантенол"),
    ("collagen", "коллаген"),
    ("retinol", "ретинол"),
    ("cica", "центелла"),
    ("centella", "центелла"),
    ("aloe", "алоэ"),
    ("tea", "чайного"),
    ("tree", "дерева"),
    ("charcoal", "уголь"),
    ("salicylic", "салициловой"),
    ("acid", "кислота"),
)


@dataclass
class CatalogMatch:
    title: str
    composition: str
    score: float
    method: str
    matched_tokens: int
    query_tokens: int
    brand: Optional[str] = None
    volume: Optional[str] = None


def _normalize_for_search(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[`'\"«»]", " ", text)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_ocr_noise(text: str) -> str:
    """
    Мягкая коррекция частых OCR-шумов для кириллицы.
    Не пытаемся "исправить всё", только повышаем шанс токен-матчинга.
    """
    raw = (text or "").lower()
    # Склеиваем бренды, распознанные как последовательность букв: "a x i s y" -> "axisy"
    raw = re.sub(
        r"\b(?:[a-zа-яё]\s+){2,}[a-zа-яё]\b",
        lambda m: re.sub(r"\s+", "", m.group(0)),
        raw,
    )
    base = _normalize_for_search(raw)
    raw_tokens = [t for t in base.split() if t]
    normalized_tokens: list[str] = []
    for token in raw_tokens:
        # Общие OCR-шумы: цифры/символы в слове.
        token = token.replace("0", "o").replace("1", "l").replace("5", "s")
        token = re.sub(r"(.)\1{3,}", r"\1\1", token)
        normalized_tokens.append(token)

    mapped_tokens = [_COMMON_TOKEN_MAP_DICT.get(t, t) for t in normalized_tokens]
    return _normalize_for_search(" ".join(mapped_tokens))


_COMMON_TOKEN_MAP_DICT = dict(_COMMON_TOKEN_MAP)


def _token_set(text: str) -> set[str]:
    return {t for t in _normalize_for_search(text).split() if len(t) >= 2}


def _compact_query_tokens(tokens: set[str]) -> set[str]:
    """
    Для длинного OCR убираем часть шумных коротких токенов,
    чтобы score не проваливался только из-за "лишнего" текста.
    """
    if len(tokens) <= 18:
        return tokens
    long_tokens = {t for t in tokens if len(t) >= 4}
    if len(long_tokens) >= 10:
        tokens = long_tokens
    if len(tokens) <= 18:
        return tokens
    ranked = sorted(tokens, key=lambda x: (-len(x), x))
    return set(ranked[:18])


def _score_match(query: str, row_search_text: str) -> float:
    query_norm = _normalize_ocr_noise(query)
    row_norm = _normalize_for_search(row_search_text)
    if not query_norm or not row_norm:
        return 0.0

    seq = SequenceMatcher(None, query_norm, row_norm).ratio()
    q_tokens = _token_set(query_norm)
    r_tokens = _token_set(row_norm)
    if not q_tokens or not r_tokens:
        return seq

    overlap = len(q_tokens & r_tokens) / max(1, len(q_tokens))
    jaccard = len(q_tokens & r_tokens) / max(1, len(q_tokens | r_tokens))
    return 0.35 * seq + 0.45 * overlap + 0.20 * jaccard


def _token_fuzzy_overlap(query_tokens: set[str], row_tokens: set[str]) -> float:
    if not query_tokens or not row_tokens:
        return 0.0
    matched = 0
    for qt in query_tokens:
        best = 0.0
        for rt in row_tokens:
            ratio = SequenceMatcher(None, qt, rt).ratio()
            if ratio > best:
                best = ratio
        if best >= 0.78:
            matched += 1
    return matched / max(1, len(query_tokens))


def _compact_brand(text: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", "", _normalize_for_search(text))


def _detect_brand_lock(query_norm: str, rows: list[sqlite3.Row]) -> Optional[str]:
    brands = {row["brand"] for row in rows if row["brand"]}
    if not brands:
        return None

    q = f" {query_norm} "
    q_compact = _compact_brand(query_norm)
    best_brand = None
    best_score = 0.0
    for brand in brands:
        b = _normalize_for_search(brand)
        b_compact = _compact_brand(brand)
        if not b or len(b_compact) < 3:
            continue
        # Прямое вхождение бренда в OCR-текст.
        if f" {b} " in q:
            return brand
        # Поддержка OCR вида "A X I S -Y"
        if b_compact and b_compact in q_compact:
            return brand
        # Fuzzy-подстраховка для OCR-ошибок.
        score = max(
            SequenceMatcher(None, b, query_norm).ratio(),
            SequenceMatcher(None, b_compact, q_compact).ratio() if b_compact and q_compact else 0.0,
        )
        if score > best_score:
            best_score = score
            best_brand = brand

    if best_brand and best_score >= 0.72:
        return best_brand
    return None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder TEXT,
            title TEXT NOT NULL,
            composition TEXT NOT NULL,
            brand TEXT,
            product_type TEXT,
            volume TEXT,
            search_text TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_search_text ON products(search_text)")
    conn.commit()


def _discover_dataset_roots() -> list[Path]:
    project_root = Path(__file__).resolve().parents[2]
    roots: list[Path] = []

    local_primary = project_root / "product_dataset"
    if local_primary.exists():
        roots.append(local_primary)

    local_backup = project_root / "product_dataset_backup"
    if local_backup.exists():
        roots.append(local_backup)

    for backup in sorted(project_root.glob("product_dataset_backup-*/product_dataset_backup")):
        if backup.exists():
            roots.append(backup)

    docker_primary = Path("/data/product_dataset")
    docker_backup = Path("/data/product_dataset_backup")
    for root in (docker_primary, docker_backup):
        if root.exists():
            roots.append(root)

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        k = str(root.resolve())
        if k not in seen:
            seen.add(k)
            unique.append(root)
    return unique


def _iter_metadata(dataset_root: Path):
    for folder in sorted(p for p in dataset_root.iterdir() if p.is_dir()):
        meta_path = folder / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue

        title = (data.get("title") or "").strip()
        composition = (data.get("composition") or "").strip()
        if not title or not composition or composition in {"-", "Не найден"}:
            continue

        yield {
            "folder": folder.name,
            "title": title,
            "composition": composition,
            "brand": extract_brand_from_title(title),
            "product_type": extract_product_type(title),
            "volume": extract_volume(title),
        }


def rebuild_catalog() -> int:
    roots = _discover_dataset_roots()
    if not roots:
        logger.warning("Не найдено ни одного датасета для построения каталога.")
        return 0

    conn = _connect()
    try:
        _create_schema(conn)
        conn.execute("DELETE FROM products")

        rows = 0
        for root in roots:
            for item in _iter_metadata(root):
                search_text = _normalize_for_search(item["title"])
                conn.execute(
                    """
                    INSERT INTO products(folder, title, composition, brand, product_type, volume, search_text)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["folder"],
                        item["title"],
                        item["composition"],
                        item["brand"],
                        item["product_type"],
                        item["volume"],
                        search_text,
                    ),
                )
                rows += 1

        conn.commit()
        logger.info("Каталог товаров построен: %s записей.", rows)
        return rows
    finally:
        conn.close()


def find_by_text(query_text: str, min_score: float = _MIN_SCORE) -> Optional[CatalogMatch]:
    query_norm = _normalize_ocr_noise(query_text)
    if len(query_norm) < 5:
        return None

    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT title, composition, brand, volume, search_text FROM products"
        ).fetchall()
    finally:
        conn.close()

    best = None
    best_score = 0.0
    best_method = "hybrid"
    best_matched_tokens = 0
    best_query_tokens = 0
    query_tokens = _compact_query_tokens(_token_set(query_norm))

    brand_lock = _detect_brand_lock(query_norm, rows)
    candidate_rows = rows
    local_min_score = min_score
    if brand_lock:
        candidate_rows = [r for r in rows if r["brand"] == brand_lock]
        if candidate_rows:
            local_min_score = max(0.30, min_score - 0.06)
            best_method = "brand_lock_hybrid"

    for row in candidate_rows:
        score = _score_match(query_norm, row["search_text"])
        row_tokens = _token_set(row["search_text"])
        matched_tokens = len(query_tokens & row_tokens)
        token_overlap = matched_tokens / max(1, min(len(query_tokens), max(8, len(row_tokens))))
        token_fuzzy = _token_fuzzy_overlap(query_tokens, row_tokens)
        score += 0.25 * token_overlap
        score += 0.20 * token_fuzzy

        if row["brand"] and _compact_brand(row["brand"]) in _compact_brand(query_norm):
            score += 0.10
        row_volume = (row["volume"] or "").lower().replace(" ", "")
        query_volume = query_norm.lower().replace(" ", "")
        if row_volume and row_volume in query_volume:
            score += 0.08

        if score > best_score:
            best_score = score
            best = row
            best_matched_tokens = matched_tokens
            best_query_tokens = len(query_tokens)

    # Мягкий fallback для шумного OCR:
    # если score немного ниже порога, но явно совпал бренд + есть приличное токен-пересечение.
    if not best:
        return None
    if best_score < local_min_score:
        best_brand_norm = _normalize_for_search(best["brand"] or "")
        has_brand = bool(best_brand_norm and f" {best_brand_norm} " in f" {query_norm} ")
        row_tokens = _token_set(best["search_text"])
        fuzzy = _token_fuzzy_overlap(query_tokens, row_tokens)
        if not (has_brand and fuzzy >= 0.18 and best_score >= (local_min_score - 0.10)):
            return None

    return CatalogMatch(
        title=best["title"],
        composition=best["composition"],
        score=round(best_score, 3),
        method=best_method,
        matched_tokens=best_matched_tokens,
        query_tokens=best_query_tokens,
        brand=best["brand"],
        volume=best["volume"],
    )
