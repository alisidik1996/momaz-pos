from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.core.validation import Name, Password, Username, UserRole, UTCResponse

class UserBase(UTCResponse):
    username: Username
    full_name: Name
    role: UserRole = "cashier"
    is_active: bool = True

class UserCreate(UserBase):
    password: Password

class UserUpdate(BaseModel):
    full_name: Optional[Name] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[Password] = None

class UserOut(UserBase):
    id: int
    created_at: datetime
    tenant_id: Optional[int] = None
    tenant_slug: Optional[str] = None
    has_tenant: bool = False
    model_config = ConfigDict(from_attributes=True)

class LoginRequest(BaseModel):
    username: Username
    password: Password

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    has_tenant: bool = False
    tenant_slug: Optional[str] = None
    user: UserOut
