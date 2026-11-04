from fastapi import APIRouter, Depends, Response, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_master_db, get_request_identity
from app.core.security import create_access_token, set_auth_cookie, auth_version
from app.modules.tenants.schemas import (
    AdminRegisterRequest, TenantSetupRequest
)
from app.modules.tenants.models import MasterUser
from app.modules.tenants import service

router = APIRouter(prefix="/api/tenants", tags=["Multi-Tenant Store Management"])

def get_current_master_user(request: Request, master_db: Session = Depends(get_master_db)) -> MasterUser:
    identity = get_request_identity(request)
    user = master_db.get(MasterUser, identity["id"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Pengguna tidak aktif atau tidak ditemukan.")

    return user

@router.post("/register-admin")
def register_new_admin(
    req: AdminRegisterRequest,
    response: Response,
    request: Request,
    master_db: Session = Depends(get_master_db)
):
    admin = service.register_admin(master_db, req)
    
    # Generate token without tenant initially
    token = create_access_token(data={
        "sub": admin.username,
        "role": admin.role,
        "id": admin.id,
        "tenant_id": None,
        "tenant_slug": None,
        "ver": auth_version(admin.password_hash),
    })

    set_auth_cookie(response, request, token)

    return {
        "status": "success",
        "message": "Pendaftaran akun admin berhasil! Silakan lanjutkan ke Setup Toko.",
        "access_token": token,
        "username": admin.username,
        "role": admin.role,
        "tenant_id": None,
        "has_tenant": False,
        "user": {
            "id": admin.id,
            "username": admin.username,
            "full_name": admin.full_name,
            "role": admin.role,
            "tenant_id": None,
            "has_tenant": False
        }
    }

@router.get("/status")
def get_tenant_status(
    master_user: MasterUser = Depends(get_current_master_user),
    master_db: Session = Depends(get_master_db)
):
    has_tenant = False
    tenant_name = None
    tenant_slug = None

    if master_user.tenant_id:
        t = service.get_tenant_by_id(master_db, master_user.tenant_id)
        if t:
            has_tenant = True
            tenant_name = t.name
            tenant_slug = t.slug

    return {
        "user_id": master_user.id,
        "username": master_user.username,
        "full_name": master_user.full_name,
        "role": master_user.role,
        "has_tenant": has_tenant,
        "tenant_id": master_user.tenant_id,
        "tenant_name": tenant_name,
        "tenant_slug": tenant_slug
    }

@router.post("/setup")
def initialize_tenant_store(
    req: TenantSetupRequest,
    response: Response,
    request: Request,
    master_user: MasterUser = Depends(get_current_master_user),
    master_db: Session = Depends(get_master_db)
):
    tenant, new_token = service.setup_tenant_database(master_db, master_user, req)

    set_auth_cookie(response, request, new_token)

    return {
        "status": "success",
        "message": f"Database toko '{tenant.name}' berhasil dibuat!",
        "access_token": new_token,
        "has_tenant": True,
        "tenant_slug": tenant.slug,
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug
        }
    }
