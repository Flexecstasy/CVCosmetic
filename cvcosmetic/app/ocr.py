import io
import logging
from functools import lru_cache
from typing import Optional

import easyocr
import numpy as np
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_reader() -> easyocr.Reader:
    """Инициализирует EasyOCR один раз (русский + английский)."""
    logger.info("Загрузка EasyOCR моделей (ru + en)...")
    return easyocr.Reader(["ru", "en"], gpu=False, verbose=False)


def _preprocess_image(image: Image.Image) -> Image.Image:
    """Улучшает изображение для OCR: grayscale, контраст, резкость."""
    image = image.convert("L")  # grayscale
    image = ImageOps.autocontrast(image, cutoff=2)
    image = image.filter(ImageFilter.SHARPEN)
    # Масштабируем если слишком маленькое
    w, h = image.size
    if max(w, h) < 800:
        scale = 800 / max(w, h)
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return image


def run_ocr(image_bytes: bytes) -> tuple[str, list[dict]]:
    """
    Запускает OCR на изображении.
    Возвращает (полный_текст, список_блоков).
    Каждый блок: {text, confidence, bbox}
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise ValueError(f"Невозможно открыть изображение: {e}") from e

    image = _preprocess_image(image)
    img_array = np.array(image)

    reader = _get_reader()
    results = reader.readtext(img_array, detail=1, paragraph=False)

    blocks = []
    lines = []
    for bbox, text, confidence in results:
        if confidence < 0.2:
            continue
        blocks.append({"text": text, "confidence": round(confidence, 3), "bbox": bbox})
        lines.append(text)

    full_text = "\n".join(lines)
    return full_text, blocks


def ocr_from_path(path: str) -> tuple[str, list[dict]]:
    with open(path, "rb") as f:
        return run_ocr(f.read())
