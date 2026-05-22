from pydantic import BaseModel, Field
from typing import Optional, List


class ProductCandidate(BaseModel):
    brand: Optional[str] = None
    product_type: Optional[str] = None
    product_name: Optional[str] = None
    volume: Optional[str] = None
    barcode: Optional[str] = None


class CatalogMatchInfo(BaseModel):
    title: str
    score: float
    method: str
    matched_tokens: int
    query_tokens: int


class RecognitionResponse(BaseModel):
    productCandidate: ProductCandidate
    ingredientsRaw: Optional[str] = None
    ingredientsParsed: List[str] = Field(default_factory=list)
    ocrText: Optional[str] = None
    catalogMatch: Optional[CatalogMatchInfo] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
