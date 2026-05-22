import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .catalog import find_by_text, rebuild_catalog
from .extractor import extract_entities
from .models import CatalogMatchInfo, RecognitionResponse
from .normalizer import normalize_text, parse_ingredients
from .ocr import _get_reader, run_ocr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Прогреваем EasyOCR при старте
    logger.info("Инициализация OCR моделей...")
    _get_reader()
    rebuild_catalog()
    logger.info("OCR готов.")
    yield


app = FastAPI(
    title="CVCosmetic Label Recognition API",
    description="OCR + NER для этикеток косметики (RU/EN)",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/recognition/label", response_model=RecognitionResponse)
async def recognize_label(
    image: UploadFile = File(..., description="Изображение этикетки (JPG/PNG)"),
    title: str = Form(default="", description="Название продукта (опционально)"),
):
    """
    Принимает изображение этикетки, возвращает структурированные данные:
    бренд, название, объём, штрихкод, состав (сырой и разобранный).
    """
    errors: list[str] = []
    warnings: list[str] = []
    catalog_match_info: CatalogMatchInfo | None = None

    # Валидация типа файла
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(
            status_code=422,
            detail=f"Неподдерживаемый тип файла: {image.content_type}. Допустимо: JPEG, PNG, WEBP.",
        )

    image_bytes = await image.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=422, detail="Файл пустой.")

    # OCR
    try:
        ocr_text, ocr_blocks = run_ocr(image_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Ошибка OCR")
        errors.append(f"OCR failed: {e}")
        ocr_text = ""
        ocr_blocks = []

    if not ocr_text.strip():
        warnings.append("OCR не распознал текст на изображении.")

    normalized_ocr = normalize_text(ocr_text)

    # Извлечение сущностей
    candidate, ingredients_raw = extract_entities(
        title=title or "",
        ocr_text=normalized_ocr,
    )

    # Если на изображении не найден состав, пробуем найти товар в каталоге metadata.json
    if not ingredients_raw:
        search_query = "\n".join(x for x in [title or "", normalized_ocr] if x)
        catalog_match = find_by_text(search_query)
        if catalog_match:
            ingredients_raw = catalog_match.composition
            catalog_match_info = CatalogMatchInfo(
                title=catalog_match.title,
                score=catalog_match.score,
                method=catalog_match.method,
                matched_tokens=catalog_match.matched_tokens,
                query_tokens=catalog_match.query_tokens,
            )
            warnings.append(
                f"Состав взят из каталога по похожему товару (score={catalog_match.score}, title='{catalog_match.title}')."
            )

    # Предупреждение о низком качестве
    low_conf = [b for b in ocr_blocks if b["confidence"] < 0.5]
    if len(low_conf) > len(ocr_blocks) * 0.4 and ocr_blocks:
        warnings.append(
            f"Низкое качество распознавания: {len(low_conf)}/{len(ocr_blocks)} блоков < 50% уверенности."
        )

    # Разбор состава
    ingredients_parsed: list[str] = []
    if ingredients_raw:
        ingredients_parsed = parse_ingredients(ingredients_raw)
        if not ingredients_parsed:
            warnings.append("Список ингредиентов найден, но не удалось его разобрать.")
    else:
        warnings.append("Состав/Ingredients не найден на изображении.")

    return RecognitionResponse(
        productCandidate=candidate,
        ingredientsRaw=ingredients_raw,
        ingredientsParsed=ingredients_parsed,
        ocrText=normalized_ocr if normalized_ocr else None,
        catalogMatch=catalog_match_info,
        errors=errors,
        warnings=warnings,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Необработанное исключение")
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера", "error": str(exc)},
    )
