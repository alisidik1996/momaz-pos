import re
import logging
import unicodedata
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, inspect
from fastapi import HTTPException
from app.core.security import hash_password, create_access_token, auth_version
from app.core.transactions import transactional
from app.database import TenantManager, is_postgres, _get_master_unpooled_engine
from app.modules.tenants.models import MasterUser, Tenant
from app.modules.tenants.schemas import AdminRegisterRequest, TenantSetupRequest
from app.core.models import StoreSettings
from app.modules.auth.models import User as TenantUser
from app.modules.catalog.models import Category, Brand
from app.modules.catalog.service import slugify as category_slugify

def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

def get_master_user_by_username(db: Session, username: str) -> Optional[MasterUser]:
    # Case-insensitive lookup
    return db.query(MasterUser).filter(func.lower(MasterUser.username) == username.strip().lower()).first()

def get_master_user_by_id(db: Session, user_id: int) -> Optional[MasterUser]:
    return db.query(MasterUser).filter(MasterUser.id == user_id).first()

def get_tenant_by_id(db: Session, tenant_id: int) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()

def get_tenant_by_slug(db: Session, slug: str) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.slug == slug).first()

@transactional
def register_admin(db: Session, req: AdminRegisterRequest) -> MasterUser:
    # Normalize username to lowercase
    username_normalized = req.username.strip().lower()
    existing = get_master_user_by_username(db, username_normalized)
    if existing:
        raise HTTPException(status_code=400, detail="Username ini sudah terdaftar. Silakan gunakan username lain atau login.")

    admin = MasterUser(
        username=username_normalized,
        password_hash=hash_password(req.password),
        full_name=req.full_name.strip(),
        role="admin",
        is_active=True
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin

@transactional
def setup_tenant_database(
    master_db: Session,
    admin_user: MasterUser,
    req: TenantSetupRequest
) -> Tuple[Tenant, str]:
    master_db.refresh(admin_user)
    if admin_user.role != "admin":
        raise HTTPException(status_code=403, detail="Hanya administrator yang dapat membuat toko.")
    if admin_user.tenant_id:
        existing_tenant = get_tenant_by_id(master_db, admin_user.tenant_id)
        if existing_tenant:
            raise HTTPException(
                status_code=400,
                detail=f"Admin ini sudah memiliki toko aktif ({existing_tenant.name}). Tidak perlu setup ulang."
            )

    # 1. Generate unique tenant slug
    base_slug = slugify(req.slug or req.store_name)[:56].rstrip("-")
    if not base_slug:
        base_slug = "toko-pakaian"
        
    slug = base_slug
    counter = 1
    schemas = set(inspect(_get_master_unpooled_engine()).get_schema_names()) if is_postgres else set()
    while get_tenant_by_slug(master_db, slug) or (
        ("tenant_" + slug.replace("-", "_")) in schemas if is_postgres else TenantManager.get_db_path(slug).exists()
    ):
        suffix = f"-{counter}"
        slug = f"{base_slug[:56 - len(suffix)].rstrip('-')}{suffix}"
        counter += 1

    # 2. Create Tenant record in master.db
    tenant = Tenant(
        name=req.store_name.strip(),
        slug=slug,
        owner_id=admin_user.id,
        is_active=True
    )
    master_db.add(tenant)
    master_db.flush()

    admin_user.tenant_id = tenant.id
    tenant_id = tenant.id
    admin_id = admin_user.id
    tenant_db = None
    master_committed = False
    try:
        TenantManager.init_tenant_db(slug)
        tenant_db = TenantManager.get_session(slug)
        # Store Settings
        footer = req.receipt_footer
        if not footer:
            footer = (
                f"Terima kasih telah berbelanja di {tenant.name}!\n"
                f"Barang dapat ditukar maksimal {req.return_policy_days} hari setelah pembelian dengan membawa struk ini & tag utuh."
            )

        settings = StoreSettings(
            store_name=tenant.name,
            tagline=req.tagline or "Fashion & Apparel Distro",
            address=req.address or "Alamat Toko Belum Diatur",
            phone=req.phone or "-",
            email=req.email or "",
            return_policy_days=req.return_policy_days,
            tax_rate=req.tax_rate,
            is_tax_enabled=req.is_tax_enabled,
            receipt_footer=footer
        )
        tenant_db.add(settings)

        # Initial Categories
        category_slugs = set()
        for cat_name in req.categories:
            c_clean = cat_name.strip()
            category_slug = category_slugify(c_clean)
            if c_clean and category_slug not in category_slugs:
                tenant_db.add(Category(name=c_clean, slug=category_slug))
                category_slugs.add(category_slug)

        # Initial Brands
        brand_names = set()
        for brand_name in req.brands:
            b_clean = brand_name.strip()
            if b_clean and b_clean not in brand_names:
                tenant_db.add(Brand(name=b_clean))
                brand_names.add(b_clean)

        # Copy Admin User to Tenant DB for local role management
        local_user = TenantUser(
            username=admin_user.username,
            password_hash=admin_user.password_hash,
            full_name=admin_user.full_name,
            role="admin",
            is_active=True
        )
        tenant_db.add(local_user)

        tenant_db.flush()
        master_db.commit()
        master_committed = True
        tenant_db.commit()
        master_db.refresh(tenant)
        master_db.refresh(admin_user)
    except Exception as exc:
        if tenant_db is not None:
            tenant_db.rollback()
        master_db.rollback()
        if master_committed:
            try:
                owner = master_db.get(MasterUser, admin_id)
                if owner and owner.tenant_id == tenant_id:
                    owner.tenant_id = None
                    master_db.flush()
                registered = master_db.get(Tenant, tenant_id)
                if registered is not None:
                    master_db.delete(registered)
                master_db.commit()
            except Exception:
                master_db.rollback()
                logging.getLogger(__name__).error("Tenant setup compensation failed")
        TenantManager.close_tenant(slug)
        raise HTTPException(status_code=503, detail="Inisialisasi toko gagal. Silakan coba kembali.") from exc
    finally:
        if tenant_db is not None:
            tenant_db.close()

    # 5. Generate refreshed JWT token with tenant_id & tenant_slug
    token = create_access_token(data={
        "sub": admin_user.username,
        "role": admin_user.role,
        "id": admin_user.id,
        "tenant_id": tenant.id,
        "tenant_slug": tenant.slug,
        "ver": auth_version(admin_user.password_hash),
    })

    return tenant, token
