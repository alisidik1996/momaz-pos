from pydantic import BaseModel, Field
from typing import Optional, List
from app.core.validation import Name, Username, Password, Money

class AdminSetupInput(BaseModel):
    full_name: Name
    username: Username
    password: Password

class StoreSetupInput(BaseModel):
    store_name: Name
    tagline: Optional[str] = "Fashion & Apparel Distro"
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    return_policy_days: int = Field(default=3, ge=0)
    tax_rate: Money = Field(default=0.0, le=100)
    is_tax_enabled: bool = False
    receipt_footer: Optional[str] = None

class SetupInitRequest(BaseModel):
    admin: AdminSetupInput
    store: StoreSetupInput
    categories: List[str] = []
    brands: List[str] = []

class SetupStatusResponse(BaseModel):
    is_setup_required: bool
    store_name: Optional[str] = None
