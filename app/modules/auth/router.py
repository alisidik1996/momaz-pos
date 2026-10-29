from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db, get_master_db
from app.core.security import create_access_token, verify_password, hash_password
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
def login(login_data: LoginRequest, response: Response, master_db: Session = Depends(get_master_db)):
    user = master_db.query(MasterUser).filter(MasterUser.username == login_data.username.strip()).first()
    if not user or not verify_password(login_data.password, user.password_hash) or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau kata sandi salah."
        )
    
    tenant_slug = None
    has_tenant = False
    if user.tenant_id:
        t = master_db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if t:
            tenant_slug = t.slug
            has_tenant = True

    token = create_access_token(data={
        "sub": user.username,
        "role": user.role,
        "id": user.id,
        "tenant_id": user.tenant_id,
        "tenant_slug": tenant_slug
    })
    
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=False,
        max_age=86400 * 7,
        samesite="lax"
    )
    
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
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user

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
    new_user = create_user(db, user_in)
    
    # Sync with master_db so the user can immediately log in from /login
    try:
        from app.database import get_tenant_slug_from_request
        slug = get_tenant_slug_from_request(request)
        tenant_id = None
        if slug:
            t = master_db.query(Tenant).filter(Tenant.slug == slug).first()
            if t:
                tenant_id = t.id
                
        m_user = master_db.query(MasterUser).filter(MasterUser.username == user_in.username).first()
        if not m_user:
            m_user = MasterUser(
                username=user_in.username,
                password_hash=new_user.password_hash,
                full_name=user_in.full_name,
                role=user_in.role,
                tenant_id=tenant_id,
                is_active=user_in.is_active
            )
            master_db.add(m_user)
        else:
            m_user.password_hash = new_user.password_hash
            m_user.full_name = user_in.full_name
            m_user.role = user_in.role
            m_user.is_active = user_in.is_active
            if tenant_id:
                m_user.tenant_id = tenant_id
        master_db.commit()
    except Exception as e:
        print("Warning syncing user to master_db:", e)
        
    return new_user

@router.put("/users/{user_id}", response_model=UserOut)
def update_existing_user(
    user_id: int, 
    user_in: UserUpdate, 
    db: Session = Depends(get_db), 
    master_db: Session = Depends(get_master_db),
    _: User = Depends(require_admin)
):
    updated = update_user(db, user_id, user_in)
    
    # Sync updates with master_db
    try:
        m_user = master_db.query(MasterUser).filter(MasterUser.username == updated.username).first()
        if m_user:
            if user_in.full_name is not None:
                m_user.full_name = user_in.full_name
            if user_in.role is not None:
                m_user.role = user_in.role
            if user_in.is_active is not None:
                m_user.is_active = user_in.is_active
            if user_in.password:
                m_user.password_hash = updated.password_hash
            master_db.commit()
    except Exception as e:
        print("Warning syncing updated user to master_db:", e)
        
    return updated

@router.delete("/users/{user_id}")
def delete_existing_user(
    user_id: int, 
    db: Session = Depends(get_db), 
    master_db: Session = Depends(get_master_db),
    current_admin: User = Depends(require_admin)
):
    user = delete_user(db, user_id, current_user_id=current_admin.id)
    
    # Also clean up from master_db if present
    try:
        m_user = master_db.query(MasterUser).filter(MasterUser.username == user.username).first()
        if m_user:
            master_db.delete(m_user)
            master_db.commit()
    except Exception as e:
        print("Warning deleting master user:", e)
        
    return {"message": f"Pengguna '{user.username}' berhasil dihapus."}
