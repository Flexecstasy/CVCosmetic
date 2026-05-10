import re
from typing import Optional
from .models import ProductCandidate


# Паттерны объёма: 50 мл, 100ml, 4.25 г, 6x2 мл (мультиупаковка → берём единичный объём)
_VOLUME_RE = re.compile(
    r"\b(?:\d+[xXхХ])?(\d+(?:[.,]\d+)?)\s*(мл|ml|г(?!\w)|g(?!\w)|oz|fl\.?\s*oz)\b",
    re.IGNORECASE,
)

# EAN-8, EAN-13, UPC-A
_BARCODE_RE = re.compile(r"\b(\d{8}|\d{12,13})\b")

# Бренд из заголовка: текст в `обратных кавычках` или "двойных кавычках"
_BRAND_BACKTICK_RE = re.compile(r"[`«\"]([\w\s\-&]+)[`»\"]")

# Состав начинается после маркера
_COMPOSITION_RE = re.compile(
    r"(?i)(?:состав\s*/?\s*)?ingredients?\s*:?\s*(.*)",
    re.DOTALL,
)
_RU_COMPOSITION_RE = re.compile(
    r"(?i)состав\s*:?\s*(.*)",
    re.DOTALL,
)

# Типы продуктов (из имени папки / заголовка)
_PRODUCT_TYPES = [
    "Крем", "Сыворотка", "Тоник", "Лосьон", "Масло", "Флюид",
    "Ампула", "Бальзам", "Мусс", "Гель", "Пенка", "Маска",
    "Скраб", "Шампунь", "Кондиционер", "Мицеллярная вода",
    "Патчи", "Праймер", "Тональный", "Консилер", "Помада",
    "Тушь", "Тени", "Пудра", "Блеск", "Хайлайтер",
]


def extract_brand_from_title(title: str) -> Optional[str]:
    m = _BRAND_BACKTICK_RE.search(title)
    if m:
        return m.group(1).strip()
    return None


def extract_product_type(title: str) -> Optional[str]:
    title_lower = title.lower()
    for pt in _PRODUCT_TYPES:
        if pt.lower() in title_lower:
            return pt
    return None


def extract_volume(text: str) -> Optional[str]:
    m = _VOLUME_RE.search(text)
    if m:
        amount = m.group(1).replace(",", ".")
        unit = m.group(2).lower()
        return f"{amount} {unit}"
    return None


def extract_barcode(text: str) -> Optional[str]:
    for m in _BARCODE_RE.finditer(text):
        candidate = m.group(1)
        if _validate_ean(candidate):
            return candidate
    return None


def _validate_ean(code: str) -> bool:
    """Проверяет контрольную сумму EAN-8/EAN-13."""
    if len(code) not in (8, 13):
        return False
    digits = [int(d) for d in code]
    if len(code) == 13:
        total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:-1]))
    else:
        total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(digits[:-1]))
    check = (10 - (total % 10)) % 10
    return check == digits[-1]


def extract_composition_raw(text: str) -> Optional[str]:
    """Извлекает сырую строку состава из OCR-текста или metadata."""
    for pattern in (_COMPOSITION_RE, _RU_COMPOSITION_RE):
        m = pattern.search(text)
        if m:
            raw = m.group(1).strip()
            # Берём до следующего раздела (обычно после точки или пустой строки)
            raw = re.split(r"\n\s*\n", raw)[0]
            raw = re.sub(r"\s+", " ", raw).strip()
            if len(raw) > 10:
                return raw
    return None


def extract_entities(title: str, ocr_text: str) -> tuple[ProductCandidate, Optional[str]]:
    """
    Извлекает все сущности из заголовка и OCR-текста.
    Возвращает (ProductCandidate, ingredients_raw).
    """
    full_text = f"{title}\n{ocr_text}"

    brand = extract_brand_from_title(title)
    product_type = extract_product_type(title)
    volume = extract_volume(full_text)
    barcode = extract_barcode(ocr_text)
    composition_raw = extract_composition_raw(ocr_text)

    # Имя продукта: заголовок без бренда в кавычках и без объёма
    product_name = title
    if brand:
        product_name = re.sub(re.escape(f"`{brand}`"), "", product_name)
        product_name = re.sub(re.escape(f'"{brand}"'), "", product_name)
    if volume:
        product_name = product_name.replace(volume, "")
    product_name = re.sub(r"\s{2,}", " ", product_name).strip(" ,")

    candidate = ProductCandidate(
        brand=brand,
        product_type=product_type,
        product_name=product_name,
        volume=volume,
        barcode=barcode,
    )
    return candidate, composition_raw
