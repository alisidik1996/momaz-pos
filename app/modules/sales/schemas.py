from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from datetime import datetime

class CheckoutItem(BaseModel):
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    quantity: int
    unit_price: float
    discount_amount: float = 0.0

class CheckoutRequest(BaseModel):
    shift_id: Optional[int] = None
    customer_id: Optional[int] = None
    items: List[CheckoutItem]
    discount_amount: float = 0.0
    tax_rate: float = 0.0  # percentage, e.g. 11.0
    payment_method: str = "cash" # 'cash', 'qris', 'card', 'split'
    amount_paid: float
    notes: Optional[str] = None

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

class SalesOrderOut(BaseModel):
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

class ReceiptOut(BaseModel):
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
