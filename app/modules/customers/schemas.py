from pydantic import ConfigDict, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
from app.core.validation import Name, UTCResponse


class OptionalContactFields(UTCResponse):
    @field_validator("phone", "email", "member_id", mode="before", check_fields=False)
    @classmethod
    def normalize_optional_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value

class CustomerBase(OptionalContactFields):
    name: Name
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = None
    member_id: Optional[str] = Field(default=None, max_length=30)

class CustomerCreate(CustomerBase):
    pass

class CustomerUpdate(OptionalContactFields):
    name: Optional[Name] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = None
    member_id: Optional[str] = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def name_cannot_be_null(self):
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Nama pelanggan tidak boleh kosong.")
        return self

class CustomerOut(CustomerBase):
    id: int
    member_id: Optional[str] = None
    total_spend: float
    total_commission: float = 0.0
    visit_count: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AffiliateCommissionOut(UTCResponse):
    id: int
    customer_id: int
    order_id: Optional[int] = None
    amount: float
    notes: Optional[str] = None
    created_at: datetime
    customer_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
