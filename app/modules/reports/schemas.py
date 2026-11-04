from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.validation import Money, Name


class StoreSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_name: Optional[Name] = None
    tagline: Optional[str] = Field(default=None, max_length=150)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=100)
    receipt_footer: Optional[str] = None
    return_policy_days: Optional[int] = Field(default=None, ge=0)
    tax_rate: Optional[Money] = Field(default=None, le=100)
    is_tax_enabled: Optional[bool] = None
    currency_symbol: Optional[str] = Field(default=None, max_length=10)
