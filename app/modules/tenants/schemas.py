from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from app.core.validation import Money, Name, Password, Username, UTCResponse

class AdminRegisterRequest(BaseModel):
    full_name: Name
    username: Username
    password: Password

class TenantSetupRequest(BaseModel):
    store_name: Name
    slug: Optional[str] = None
    tagline: Optional[str] = "Fashion & Apparel Distro"
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    return_policy_days: int = Field(default=3, ge=0)
    tax_rate: Money = Field(default=0.0, le=100)
    is_tax_enabled: bool = False
    receipt_footer: Optional[str] = None
    categories: List[Name] = Field(default_factory=list)
    brands: List[Name] = Field(default_factory=list)

class TenantOut(UTCResponse):
    id: int
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class MasterUserOut(UTCResponse):
    id: int
    username: str
    full_name: str
    role: str
    tenant_id: Optional[int] = None
    tenant_slug: Optional[str] = None
    has_tenant: bool = False
    model_config = ConfigDict(from_attributes=True)
