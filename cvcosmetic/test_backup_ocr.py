"""Проверяем: читает ли OCR состав с backup-изображений."""
import json, sys, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

API_URL = "http://localhost:8000/api/recognition/label"
BACKUP  = Path(r"C:\Users\VitoScaletto\OneDrive\Рабочий стол\CVCosmetic\product_dataset_backup-20260421T153504Z-3-001\product_dataset_backup")

KNOWN_INGREDIENTS_KEYWORDS = [
    "aqua", "glycerin", "water", "alcohol", "acid", "extract",
    "oil", "butyrospermum", "dimethicone", "parfum", "fragrance",
    "ingredients", "состав", "niacinamide", "panthenol",
]

def send(image_path: Path, title: str) -> dict:
    boundary = "----B7MA4"
    img_bytes = image_path.read_bytes()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\n{title}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{image_path.name}\"\r\nContent-Type: image/jpeg\r\n\r\n"
    ).encode() + img_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))

def has_ingredients(ocr_text: str) -> bool:
    t = ocr_text.lower()
    return sum(1 for kw in KNOWN_INGREDIENTS_KEYWORDS if kw in t) >= 3

products = [p for p in BACKUP.iterdir() if p.is_dir() and (p/"metadata.json").exists()][:6]

found_ingredients = 0
total_images = 0

for folder in products:
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    title = meta.get("title", "")
    imgs  = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))

    print(f"\n{'─'*60}")
    print(f"  {folder.name[:58]}")
    print(f"  Изображений: {len(imgs)}")

    best_ocr = ""
    best_img = ""
    for img in imgs:
        total_images += 1
        r = send(img, title)
        ocr = r.get("ocrText") or ""
        ing = r.get("ingredientsParsed", [])
        flag = "🟢 СОСТАВ" if (has_ingredients(ocr) or ing) else "⚪ текст"
        short_ocr = ocr[:120].replace("\n", " ")
        print(f"  {flag}  {img.name[-20:]}  chars={len(ocr):3d}  ing={len(ing):2d}  | {short_ocr}")
        if has_ingredients(ocr) or ing:
            found_ingredients += 1
            best_ocr = ocr
            best_img = img.name

    if best_ocr:
        print(f"\n  ▶ Лучший OCR ({best_img}):")
        print(f"  {best_ocr[:300]}")

print(f"\n{'='*60}")
print(f"  Изображений проверено: {total_images}")
print(f"  Найден состав на:      {found_ingredients} из {total_images}")
print(f"={'='*59}\n")
