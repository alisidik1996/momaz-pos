from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class StockMovementOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    user_id: Optional[int] = None
    change_qty: int
    current_stock: int
    movement_type: str
    reference: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    product_name: Optional[str] = None
    variant_info: Optional[str] = None
    sku: Optional[str] = None
    user_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class StockAdjustmentRequest(BaseModel):
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    actual_stock: int
    reason: str  # 'damaged', 'lost', 'physical_count', 'other'
    note: Optional[str] = None

class StockInItem(BaseModel):
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    quantity: int
    cost_price: Optional[float] = None

class StockInRequest(BaseModel):
    supplier_name: Optional[str] = None
    invoice_ref: Optional[str] = None
    note: Optional[str] = None
    items: List[StockInItem]

class LowStockItemOut(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    product_name: str
    category_name: Optional[str] = None
    sku: str
    barcode: str
    size: Optional[str] = ""
    color: Optional[str] = ""
    stock: int
    min_stock: int
