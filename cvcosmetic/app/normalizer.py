import re
import unicodedata


def normalize_text(text: str) -> str:
    """Нормализует текст: unicode, лишние пробелы, переносы строк."""
    text = unicodedata.normalize("NFC", text)
    # Убираем управляющие символы кроме пробела и переноса
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\t ")
    # Схлопываем пробелы
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_ingredient(ingredient: str) -> str:
    """Нормализует одиночный ингредиент INCI."""
    ingredient = ingredient.strip()
    # Убираем звёздочки, слэши в конце, скобочные пояснения на русском
    ingredient = re.sub(r"\*+$", "", ingredient)
    ingredient = re.sub(r"\s*\((?:[а-яёА-ЯЁ][^)]*)\)", "", ingredient)
    # Капитализация первой буквы, остальное — как есть
    ingredient = ingredient.strip(" ,;/")
    if ingredient:
        ingredient = ingredient[0].upper() + ingredient[1:]
    return ingredient


def parse_ingredients(raw: str) -> list[str]:
    """Разбивает строку состава по разделителям (запятая, точка с запятой, bullet •)."""
    # Убираем маркер начала состава
    raw = re.sub(
        r"(?i)(состав\s*/?\s*ingredients?\s*:?|ingredients?\s*:?|состав\s*:?)",
        "",
        raw,
    ).strip()

    # Если используется bullet-разделитель (•) — конвертируем в запятые
    if "\u2022" in raw:
        # Убираем также альтернативные названия формата "ИМЯ / NAME"
        raw = re.sub(r"\s*/\s*[A-Z][A-Z\s]+(?=\s*[•,]|$)", "", raw)
        raw = raw.replace("\u2022", ",")

    # Разделяем по запятой или точке с запятой
    parts = re.split(r"[,;]", raw)
    result = []
    for part in parts:
        normalized = normalize_ingredient(part)
        if len(normalized) >= 2:
            result.append(normalized)
    return result
