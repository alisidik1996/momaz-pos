from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
import logging
from app.database import get_db, get_request_identity
from app.core.transactions import transactional
from app.core.security import hash_password, verify_password
from app.modules.auth.models import User
from app.modules.auth.schemas import UserCreate, UserUpdate

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False, bearerFormat="JWT")

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    # Case-insensitive lookup
    return db.query(User).filter(func.lower(User.username) == username.strip().lower()).first()

def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).populate_existing().first()

def get_all_users(db: Session) -> List[User]:
    return db.query(User).order_by(User.id.desc()).all()

@transactional
def create_user(db: Session, user_in: UserCreate, commit: bool = True) -> User:
    # Normalize username to lowercase
    username_normalized = user_in.username.strip().lower()
    existing = get_user_by_username(db, username_normalized)
    if existing:
        raise HTTPException(status_code=400, detail="Username sudah terdaftar.")

    db_user = User(
        username=username_normalized,
        password_hash=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active
    )
    db.add(db_user)
    db.flush()
    if commit:
        db.commit()
        db.refresh(db_user)
    return db_user

@transactional
def update_user(db: Session, user_id: int, user_in: UserUpdate, commit: bool = True) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
    if user.role == "admin" and user.is_active and (user_in.role not in (None, "admin") or user_in.is_active is False):
        if db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count() <= 1:
            raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan atau mengubah admin terakhir.")
    
    if user_in.full_name is not None:
        user.full_name = user_in.full_name
    if user_in.role is not None:
        user.role = user_in.role
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.password:
        user.password_hash = hash_password(user_in.password)
        
    db.flush()
    if commit:
        db.commit()
        db.refresh(user)
    return user

@transactional
def delete_user(db: Session, user_id: int, current_user_id: Optional[int] = None, commit: bool = True) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
    if current_user_id and user.id == current_user_id:
        raise HTTPException(status_code=400, detail="Anda tidak dapat menghapus akun Anda sendiri.")
    
    if user.role == "admin" and user.is_active:
        admin_count = db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Tidak dapat menghapus admin terakhir. Minimal harus ada 1 akun administrator aktif.")
            
    db.delete(user)
    if commit:
        db.commit()
    return user

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> User:
    identity = get_request_identity(request)
    user = getattr(request.state, "current_user", None) or get_user_by_username(db, identity["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Pengguna tidak aktif atau tidak ditemukan.")
        
    return user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ["admin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak: Hanya administrator / manajer yang diizinkan."
        )
    return current_user
