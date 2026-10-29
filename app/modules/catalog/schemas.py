from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryOut(CategoryBase):
    id: int
    slug: str
    model_config = ConfigDict(from_attributes=True)

class BrandBase(BaseModel):
    name: str

class BrandCreate(BrandBase):
    pass

class BrandOut(BrandBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class VariantBase(BaseModel):
    sku: Optional[str] = None
    barcode: Optional[str] = None
    size: str
    color: str
    cost_price: float = 0.0
    sell_price: float = 0.0
    stock: int = 0
    min_stock: int = 5
    is_active: bool = True

class VariantCreate(VariantBase):
    product_id: Optional[int] = None

class VariantUpdate(BaseModel):
    sku: Optional[str] = None
    barcode: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    cost_price: Optional[float] = None
    sell_price: Optional[float] = None
    stock: Optional[int] = None
    min_stock: Optional[int] = None
    is_active: Optional[bool] = None

class VariantOut(VariantBase):
    id: int
    product_id: int
    model_config = ConfigDict(from_attributes=True)

class ProductBase(BaseModel):
    name: str
    sku: Optional[str] = None
    barcode: Optional[str] = None
    category_id: Optional[int] = None
    brand_id: Optional[int] = None
    description: Optional[str] = None
    cost_price: float = 0.0
    base_price: float = 0.0
    discount_price: Optional[float] = 0.0
    stock: int = 0
    min_stock: int = 5
    image_url: Optional[str] = None
    is_active: bool = True
    member_discount_type: Optional[str] = "percent"       # 'percent' or 'nominal'
    member_discount_value: Optional[float] = 0.0
    affiliate_commission_type: Optional[str] = "percent"  # 'percent' or 'nominal'
    affiliate_commission_value: Optional[float] = 0.0

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    category_id: Optional[int] = None
    brand_id: Optional[int] = None
    description: Optional[str] = None
    cost_price: Optional[float] = None
    base_price: Optional[float] = None
    discount_price: Optional[float] = None
    stock: Optional[int] = None
    min_stock: Optional[int] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    member_discount_type: Optional[str] = None
    member_discount_value: Optional[float] = None
    affiliate_commission_type: Optional[str] = None
    affiliate_commission_value: Optional[float] = None

class ProductAffiliateRuleUpdate(BaseModel):
    product_id: int
    member_discount_type: str = "percent"
    member_discount_value: float = 0.0
    affiliate_commission_type: str = "percent"
    affiliate_commission_value: float = 0.0

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
    product_id: int
    sizes: List[str]             # e.g., ["S", "M", "L", "XL"]
    colors: List[str]            # e.g., ["Hitam", "Putih", "Navy"]
    cost_price: float = 0.0
    sell_price: float = 0.0
    initial_stock: int = 0
    min_stock: int = 5
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
