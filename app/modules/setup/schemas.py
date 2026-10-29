from pydantic import BaseModel, ConfigDict
from typing import Optional, List

class AdminSetupInput(BaseModel):
    full_name: str
    username: str
    password: str

class StoreSetupInput(BaseModel):
    store_name: str
    tagline: Optional[str] = "Fashion & Apparel Distro"
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    return_policy_days: int = 3
    tax_rate: float = 0.0
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
