from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.database import get_db, get_master_db, get_request_identity
from app.core.security import create_access_token, verify_password, set_auth_cookie, auth_version
from app.core.sync import commit_user_sync, snapshot_master_user, sync_user_to_master, sync_user_update_to_master, sync_user_delete_to_master, DualDBSyncError
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserCreate, UserUpdate, UserOut
from app.modules.auth.service import (
    get_current_user, 
    require_admin,
    create_user, 
    get_all_users, 
    update_user,
    delete_user
)
from app.modules.auth.models import User
from app.modules.tenants.models import MasterUser, Tenant

router = APIRouter(prefix="/api/auth", tags=["Authentication & Users"])

@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, response: Response, request: Request, master_db: Session = Depends(get_master_db)):
    # Case-insensitive username lookup for better UX
    username_normalized = login_data.username.strip().lower()
    user = master_db.query(MasterUser).filter(func.lower(MasterUser.username) == username_normalized).first()
    if not user or not user.is_active or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau kata sandi salah."
        )
    
    tenant_slug = None
    has_tenant = False
    if user.tenant_id:
        t = master_db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if t and not t.is_active:
            raise HTTPException(status_code=403, detail="Toko tidak aktif.")
        if t:
            tenant_slug = t.slug
            has_tenant = True

    token = create_access_token(data={
        "sub": user.username,
        "role": user.role,
        "id": user.id,
        "tenant_id": user.tenant_id,
        "tenant_slug": tenant_slug,
        "ver": auth_version(user.password_hash),
    })
    
    set_auth_cookie(response, request, token)
    
    user_out = UserOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        tenant_id=user.tenant_id,
        tenant_slug=tenant_slug,
        has_tenant=has_tenant
    )
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "has_tenant": has_tenant,
        "tenant_slug": tenant_slug,
        "user": user_out
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token")
    return {"message": "Berhasil logout."}

@router.get("/me", response_model=UserOut)
def read_current_user(request: Request, current_user: User = Depends(get_current_user)):
    identity = get_request_identity(request)
    user = UserOut.model_validate(current_user)
    user.tenant_id = identity["tenant_id"]
    user.tenant_slug = identity["tenant_slug"]
    user.has_tenant = identity["tenant_slug"] is not None
    return user

@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return get_all_users(db)

@router.post("/users", response_model=UserOut)
def create_new_user(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    master_db: Session = Depends(get_master_db),
    _: User = Depends(require_admin)
):
    tenant_id = db.info["tenant_id"]
    try:
        existing = master_db.query(MasterUser).filter(func.lower(MasterUser.username) == user_in.username.lower()).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username sudah digunakan oleh akun lain.")
        new_user = create_user(db, user_in, commit=False)
        sync_user_to_master(
            db, master_db, tenant_id,
            user_in.username, new_user.password_hash,
            user_in.full_name, user_in.role, user_in.is_active,
            commit=False,
        )
        commit_user_sync(db, master_db, new_user.username, tenant_id, original=None)
        db.refresh(new_user)
    except DualDBSyncError as exc:
        db.rollback()
        master_db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        master_db.rollback()
        raise

    return new_user

@router.put("/users/{user_id}", response_model=UserOut)
def update_existing_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    master_db: Session = Depends(get_master_db),
    _: User = Depends(require_admin)
):
    tenant_id = db.info["tenant_id"]
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
        original = snapshot_master_user(master_db, user.username, tenant_id)
        updated = update_user(db, user_id, user_in, commit=False)
        synced = sync_user_update_to_master(
            master_db,
            updated.username,
            tenant_id,
            full_name=updated.full_name,
            role=updated.role,
            is_active=updated.is_active,
            password_hash=updated.password_hash,
            commit=False,
        )
        if not synced:
            sync_user_to_master(db, master_db, tenant_id, updated.username, updated.password_hash, updated.full_name, updated.role, updated.is_active, commit=False)
        commit_user_sync(db, master_db, updated.username, tenant_id, original)
        db.refresh(updated)
    except DualDBSyncError as exc:
        db.rollback()
        master_db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        master_db.rollback()
        raise

    return updated

@router.delete("/users/{user_id}")
def delete_existing_user(
    user_id: int,
    db: Session = Depends(get_db),
    master_db: Session = Depends(get_master_db),
    current_admin: User = Depends(require_admin)
):
    tenant_id = db.info["tenant_id"]
    try:
        existing = db.get(User, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
        original = snapshot_master_user(master_db, existing.username, tenant_id)
        user = delete_user(db, user_id, current_user_id=current_admin.id, commit=False)
        sync_user_delete_to_master(master_db, user.username, tenant_id, commit=False)
        commit_user_sync(db, master_db, user.username, tenant_id, original)
    except DualDBSyncError as exc:
        db.rollback()
        master_db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        master_db.rollback()
        raise

    return {"message": f"Pengguna '{user.username}' berhasil dihapus."}
