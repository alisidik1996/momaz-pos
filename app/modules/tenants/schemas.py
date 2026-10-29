from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class AdminRegisterRequest(BaseModel):
    full_name: str
    username: str
    password: str

class TenantSetupRequest(BaseModel):
    store_name: str
    slug: Optional[str] = None
    tagline: Optional[str] = "Fashion & Apparel Distro"
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    return_policy_days: int = 3
    tax_rate: float = 0.0
    is_tax_enabled: bool = False
    receipt_footer: Optional[str] = None
    categories: List[str] = []
    brands: List[str] = []

class TenantOut(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MasterUserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    tenant_id: Optional[int] = None
    tenant_slug: Optional[str] = None
    has_tenant: bool = False
    model_config = ConfigDict(from_attributes=True)
