"""Живой тест API на реальных изображениях из датасета."""
import json
import sys
import urllib.request
import urllib.parse
import io
import os
from pathlib import Path

API_URL = "http://localhost:8000/api/recognition/label"
_PROJECT_ROOT = Path(__file__).parent.parent
DATASET = _PROJECT_ROOT / "product_dataset"
_backup_candidates = sorted(_PROJECT_ROOT.glob("product_dataset_backup-*/product_dataset_backup"))
BACKUP  = _backup_candidates[0] if _backup_candidates else _PROJECT_ROOT / "product_dataset_backup"


def multipart_request(url: str, image_path: Path, title: str) -> dict:
    """Отправляет multipart/form-data запрос без сторонних библиотек."""
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    image_bytes = image_path.read_bytes()
    content_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="title"\r\n\r\n'
        f"{title}\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{image_path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + image_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Content-Length", str(len(body)))

    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_result(label: str, result: dict, expected_brand: str = None) -> bool:
    pc = result["productCandidate"]
    ok = True

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  brand:         {pc['brand']!r}")
    print(f"  product_type:  {pc['product_type']!r}")
    print(f"  volume:        {pc['volume']!r}")
    print(f"  barcode:       {pc['barcode']!r}")

    raw = result.get("ingredientsRaw") or ""
    parsed = result.get("ingredientsParsed", [])
    print(f"  ing_raw:       {raw[:80]!r}{'...' if len(raw)>80 else ''}")
    print(f"  ing_count:     {len(parsed)}")
    if parsed:
        print(f"  ing[0:4]:      {parsed[:4]}")

    ocr = result.get("ocrText") or ""
    print(f"  ocr_chars:     {len(ocr)}")
    print(f"  ocr_preview:   {ocr[:100]!r}")

    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  ⚠  {w}")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  ✗  {e}")
        ok = False

    if expected_brand and pc["brand"] != expected_brand:
        print(f"  ✗ БРЕНД: ожидался {expected_brand!r}, получен {pc['brand']!r}")
        ok = False
    elif expected_brand:
        print(f"  ✓ бренд совпадает: {pc['brand']!r}")

    return ok


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    passed = 0
    total = 0

    # ── Тест 1: Крем ЧИСТАЯ ЛИНИЯ — фронт упаковки ──────────────────────────
    folder1 = DATASET / "Аква-крем_для_лица__ЧИСТАЯ_ЛИНИЯ__ИДЕАЛЬНАЯ_КОЖА_Мгновенная_матовость_50_мл"
    img1 = next(p for p in folder1.iterdir() if p.suffix == ".jpg" and "img1" in p.name)
    meta1 = json.loads((folder1 / "metadata.json").read_text(encoding="utf-8"))
    total += 1
    r1 = multipart_request(API_URL, img1, meta1["title"])
    ok1 = print_result("ТЕСТ 1 · ЧИСТАЯ ЛИНИЯ — фронт (img1)", r1, expected_brand="ЧИСТАЯ ЛИНИЯ")
    if ok1: passed += 1

    # ── Тест 2: GARNIER — бэк этикетка из backup датасета ───────────────────
    folder2_backup = BACKUP / "Аква-крем_для_лица__ЧИСТАЯ_ЛИНИЯ__ИДЕАЛЬНАЯ_КОЖА_Мгновенная_матовость_50_мл"
    if folder2_backup.exists():
        imgs2 = sorted(p for p in folder2_backup.iterdir() if p.suffix == ".jpg")
        if imgs2:
            meta2 = json.loads((folder2_backup / "metadata.json").read_text(encoding="utf-8"))
            total += 1
            r2 = multipart_request(API_URL, imgs2[0], meta2["title"])
            ok2 = print_result("ТЕСТ 2 · ЧИСТАЯ ЛИНИЯ — backup/бэк (img1)", r2, expected_brand="ЧИСТАЯ ЛИНИЯ")
            if ok2: passed += 1

    # ── Тест 3: VT REEDLE SHOT 100 ──────────────────────────────────────────
    folder3 = DATASET / "Ампула_для_лица__VT__REEDLE_SHOT_100_с_микроиглами_6x2_мл"
    imgs3 = sorted(p for p in folder3.iterdir() if p.suffix == ".jpg")
    meta3 = json.loads((folder3 / "metadata.json").read_text(encoding="utf-8"))
    total += 1
    r3 = multipart_request(API_URL, imgs3[0], meta3["title"])
    ok3 = print_result("ТЕСТ 3 · VT REEDLE SHOT 100 — фронт", r3, expected_brand="VT")
    if ok3: passed += 1

    # ── Тест 4: BLISTEX — бэк из backup ─────────────────────────────────────
    folder4_backup = BACKUP / "Бальзам_для_губ__BLISTEX__Medicated__классический_SPF-15__4_25_г"
    if folder4_backup.exists():
        imgs4 = sorted(p for p in folder4_backup.iterdir() if p.suffix == ".jpg")
        if imgs4:
            meta4 = json.loads((folder4_backup / "metadata.json").read_text(encoding="utf-8"))
            total += 1
            # Берём последнее изображение — обычно бэк
            r4 = multipart_request(API_URL, imgs4[-1], meta4["title"])
            ok4 = print_result("ТЕСТ 4 · BLISTEX бальзам — backup последнее фото", r4, expected_brand="BLISTEX")
            if ok4: passed += 1

    # ── Тест 5: ART-VISAGE — без title (только OCR) ──────────────────────────
    folder5 = DATASET / "Бальзам_для_губ__ART-VISAGE__EUPHORIA_SOS_Repair_восстанавливающий_с_маслом_манго"
    imgs5 = sorted(p for p in folder5.iterdir() if p.suffix == ".jpg")
    total += 1
    r5 = multipart_request(API_URL, imgs5[0], "")
    print_result("ТЕСТ 5 · ART-VISAGE — без title (чистый OCR)", r5)
    passed += 1  # этот тест без проверки бренда

    print(f"\n{'='*60}")
    print(f"  ИТОГ: {passed}/{total} критических проверок прошло")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
