from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class ReturnItemRequest(BaseModel):
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    quantity: int = 1
    refund_subtotal: float

class ReturnCreateRequest(BaseModel):
    order_id: int
    reason: str = "wrong_size"
    items: List[ReturnItemRequest]
    exchange_product_id: Optional[int] = None
    exchange_variant_id: Optional[int] = None
    notes: Optional[str] = None

class ReturnItemOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    quantity: int
    refund_subtotal: float
    product_name: Optional[str] = None
    variant_info: Optional[str] = None
    sku: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ReturnOrderOut(BaseModel):
    id: int
    return_number: str
    order_id: int
    invoice_number: Optional[str] = None
    cashier_id: Optional[int] = None
    cashier_name: Optional[str] = None
    reason: str
    total_refund_amount: float
    additional_charge: float
    exchange_product_id: Optional[int] = None
    exchange_variant_id: Optional[int] = None
    exchange_product_name: Optional[str] = None
    exchange_variant_info: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    items: List[ReturnItemOut] = []
    model_config = ConfigDict(from_attributes=True)
