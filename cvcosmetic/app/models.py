from pydantic import BaseModel
from typing import Optional, List


class ProductCandidate(BaseModel):
    brand: Optional[str] = None
    product_type: Optional[str] = None
    product_name: Optional[str] = None
    volume: Optional[str] = None
    barcode: Optional[str] = None


class RecognitionResponse(BaseModel):
    productCandidate: ProductCandidate
    ingredientsRaw: Optional[str] = None
    ingredientsParsed: List[str] = []
    ocrText: Optional[str] = None
    errors: List[str] = []
    warnings: List[str] = []
