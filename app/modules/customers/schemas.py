from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class CustomerBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    member_id: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    member_id: Optional[str] = None

class CustomerOut(CustomerBase):
    id: int
    member_id: Optional[str] = None
    total_spend: float
    total_commission: float = 0.0
    visit_count: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AffiliateCommissionOut(BaseModel):
    id: int
    customer_id: int
    order_id: Optional[int] = None
    amount: float
    notes: Optional[str] = None
    created_at: datetime
    customer_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
