from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from app.core.validation import ItemReference, Money, PositiveId, PositiveQuantity, UTCResponse

class ReturnItemRequest(ItemReference):
    quantity: PositiveQuantity = 1
    refund_subtotal: Money

class ReturnCreateRequest(BaseModel):
    order_id: PositiveId
    reason: str = "wrong_size"
    items: List[ReturnItemRequest] = Field(min_length=1)
    exchange_product_id: Optional[PositiveId] = None
    exchange_variant_id: Optional[PositiveId] = None
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

class ReturnOrderOut(UTCResponse):
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
