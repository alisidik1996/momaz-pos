from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing import Optional, List, Annotated, Literal
from datetime import datetime
from app.core.validation import Money, Name, PositiveId, StockQuantity, UTCResponse

ProductName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
SizeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
ColorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
CatalogCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

class CategoryBase(BaseModel):
    name: Name
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryOut(CategoryBase):
    id: int
    slug: str
    model_config = ConfigDict(from_attributes=True)

class BrandBase(BaseModel):
    name: Name

class BrandCreate(BrandBase):
    pass

class BrandOut(BrandBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class VariantBase(BaseModel):
    sku: Optional[CatalogCode] = None
    barcode: Optional[CatalogCode] = None
    size: SizeName
    color: ColorName
    cost_price: Money = 0.0
    sell_price: Money = 0.0
    stock: StockQuantity = 0
    min_stock: StockQuantity = 5
    is_active: bool = True

class VariantCreate(VariantBase):
    product_id: PositiveId

class VariantUpdate(BaseModel):
    sku: Optional[CatalogCode] = None
    barcode: Optional[CatalogCode] = None
    size: Optional[SizeName] = None
    color: Optional[ColorName] = None
    cost_price: Optional[Money] = None
    sell_price: Optional[Money] = None
    stock: Optional[StockQuantity] = None
    min_stock: Optional[StockQuantity] = None
    is_active: Optional[bool] = None

class VariantOut(VariantBase):
    id: int
    product_id: int
    model_config = ConfigDict(from_attributes=True)

class ProductBase(UTCResponse):
    name: ProductName
    sku: Optional[CatalogCode] = None
    barcode: Optional[CatalogCode] = None
    category_id: Optional[PositiveId] = None
    brand_id: Optional[PositiveId] = None
    description: Optional[str] = None
    cost_price: Money = 0.0
    base_price: Money = 0.0
    discount_price: Optional[Money] = 0.0
    stock: StockQuantity = 0
    min_stock: StockQuantity = 5
    image_url: Optional[str] = None
    is_active: bool = True
    member_discount_type: Optional[Literal["percent", "nominal"]] = "percent"
    member_discount_value: Optional[Money] = 0.0
    affiliate_commission_type: Optional[Literal["percent", "nominal"]] = "percent"
    affiliate_commission_value: Optional[Money] = 0.0

class ProductCreate(ProductBase):
    @model_validator(mode="after")
    def validate_percentages(self):
        for prefix in ("member_discount", "affiliate_commission"):
            if getattr(self, f"{prefix}_type") == "percent" and (getattr(self, f"{prefix}_value") or 0) > 100:
                raise ValueError("Persentase diskon atau komisi tidak boleh melebihi 100%.")
        return self

class ProductUpdate(BaseModel):
    name: Optional[ProductName] = None
    sku: Optional[CatalogCode] = None
    barcode: Optional[CatalogCode] = None
    category_id: Optional[PositiveId] = None
    brand_id: Optional[PositiveId] = None
    description: Optional[str] = None
    cost_price: Optional[Money] = None
    base_price: Optional[Money] = None
    discount_price: Optional[Money] = None
    stock: Optional[StockQuantity] = None
    min_stock: Optional[StockQuantity] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    member_discount_type: Optional[Literal["percent", "nominal"]] = None
    member_discount_value: Optional[Money] = None
    affiliate_commission_type: Optional[Literal["percent", "nominal"]] = None
    affiliate_commission_value: Optional[Money] = None

class ProductAffiliateRuleUpdate(BaseModel):
    product_id: PositiveId
    member_discount_type: Literal["percent", "nominal"] = "percent"
    member_discount_value: Money = 0.0
    affiliate_commission_type: Literal["percent", "nominal"] = "percent"
    affiliate_commission_value: Money = 0.0

    @model_validator(mode="after")
    def validate_percentages(self):
        for prefix in ("member_discount", "affiliate_commission"):
            if getattr(self, f"{prefix}_type") == "percent" and getattr(self, f"{prefix}_value") > 100:
                raise ValueError("Persentase diskon atau komisi tidak boleh melebihi 100%.")
        return self

class BatchAffiliateRuleUpdate(BaseModel):
    rules: List[ProductAffiliateRuleUpdate]

class ProductOut(ProductBase):
    id: int
    created_at: datetime
    category: Optional[CategoryOut] = None
    brand: Optional[BrandOut] = None
    variants: List[VariantOut] = []
    total_stock: Optional[int] = 0
    model_config = ConfigDict(from_attributes=True)

class MatrixGenerateRequest(BaseModel):
    product_id: PositiveId
    sizes: List[SizeName] = Field(min_length=1)
    colors: List[ColorName] = Field(min_length=1)
    cost_price: Money = 0.0
    sell_price: Money = 0.0
    initial_stock: StockQuantity = 0
    min_stock: StockQuantity = 5
    sku_prefix: Optional[str] = None  # e.g., "KMT"

class ScanResultOut(BaseModel):
    product_id: int
    product_name: str
    category_name: Optional[str] = None
    sku: str
    barcode: str
    sell_price: float
    cost_price: float
    stock: int
    is_active: bool
    variant_id: Optional[int] = None
    size: Optional[str] = ""
    color: Optional[str] = ""
    member_discount_type: Optional[str] = "percent"
    member_discount_value: Optional[float] = 0.0
    affiliate_commission_type: Optional[str] = "percent"
    affiliate_commission_value: Optional[float] = 0.0
