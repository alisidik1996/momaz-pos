import math
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Literal
from datetime import datetime
from app.core.validation import ItemReference, Money, PositiveId, PositiveQuantity, UTCResponse

class CheckoutItem(ItemReference):
    quantity: PositiveQuantity
    unit_price: Money
    discount_amount: Money = 0.0

    @model_validator(mode="after")
    def validate_line_total(self):
        line_price = self.unit_price * self.quantity
        if not math.isfinite(line_price) or self.discount_amount > line_price:
            raise ValueError("Diskon item tidak boleh melebihi harga item.")
        return self

class CheckoutRequest(BaseModel):
    shift_id: Optional[PositiveId] = None
    customer_id: Optional[PositiveId] = None
    items: List[CheckoutItem] = Field(min_length=1)
    discount_amount: Money = 0.0
    tax_rate: Money = Field(default=0.0, le=100)
    payment_method: Literal["cash", "qris", "card", "split"] = "cash"
    amount_paid: Money
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_discount(self):
        subtotal = sum(item.unit_price * item.quantity - item.discount_amount for item in self.items)
        if not math.isfinite(subtotal) or self.discount_amount > subtotal:
            raise ValueError("Diskon transaksi tidak boleh melebihi subtotal.")
        return self

class SalesOrderItemOut(BaseModel):
    id: int
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    product_name: str
    variant_info: Optional[str] = ""
    sku: str
    barcode: str
    cost_price: float
    unit_price: float
    quantity: int
    discount_amount: float
    subtotal: float
    model_config = ConfigDict(from_attributes=True)

class SalesOrderOut(UTCResponse):
    id: int
    invoice_number: str
    shift_id: Optional[int] = None
    cashier_id: Optional[int] = None
    customer_id: Optional[int] = None
    subtotal: float
    discount_amount: float
    tax_amount: float
    total_amount: float
    payment_method: str
    amount_paid: float
    change_amount: float
    status: str
    notes: Optional[str] = None
    created_at: datetime
    cashier_name: Optional[str] = None
    customer_name: Optional[str] = None
    customer_member_id: Optional[str] = None
    items: List[SalesOrderItemOut] = []
    model_config = ConfigDict(from_attributes=True)

class ReceiptOut(UTCResponse):
    created_at: Optional[datetime] = None
    invoice_number: str
    store_name: str
    store_tagline: str
    store_address: str
    store_phone: str
    date_str: str
    cashier_name: str
    customer_name: Optional[str] = None
    customer_member_id: Optional[str] = None
    items: List[SalesOrderItemOut]
    subtotal: float
    discount_amount: float
    tax_amount: float
    total_amount: float
    payment_method: str
    amount_paid: float
    change_amount: float
    receipt_footer: str
