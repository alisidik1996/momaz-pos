import re
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.security import hash_password, create_access_token
from app.database import TenantManager
from app.modules.tenants.models import MasterUser, Tenant
from app.modules.tenants.schemas import AdminRegisterRequest, TenantSetupRequest
from app.core.models import StoreSettings
from app.modules.auth.models import User as TenantUser
from app.modules.catalog.models import Category, Brand

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text)

def get_master_user_by_username(db: Session, username: str) -> Optional[MasterUser]:
    return db.query(MasterUser).filter(MasterUser.username == username).first()

def get_master_user_by_id(db: Session, user_id: int) -> Optional[MasterUser]:
    return db.query(MasterUser).filter(MasterUser.id == user_id).first()

def get_tenant_by_id(db: Session, tenant_id: int) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.id == tenant_id).first()

def get_tenant_by_slug(db: Session, slug: str) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.slug == slug).first()

def register_admin(db: Session, req: AdminRegisterRequest) -> MasterUser:
    existing = get_master_user_by_username(db, req.username.strip())
    if existing:
        raise HTTPException(status_code=400, detail="Username ini sudah terdaftar. Silakan gunakan username lain atau login.")

    admin = MasterUser(
        username=req.username.strip(),
        password_hash=hash_password(req.password),
        full_name=req.full_name.strip(),
        role="admin",
        is_active=True
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin

def setup_tenant_database(
    master_db: Session,
    admin_user: MasterUser,
    req: TenantSetupRequest
) -> Tuple[Tenant, str]:
    if admin_user.tenant_id:
        existing_tenant = get_tenant_by_id(master_db, admin_user.tenant_id)
        if existing_tenant:
            raise HTTPException(
                status_code=400,
                detail=f"Admin ini sudah memiliki toko aktif ({existing_tenant.name}). Tidak perlu setup ulang."
            )

    # 1. Generate unique tenant slug
    base_slug = slugify(req.slug or req.store_name)
    if not base_slug:
        base_slug = "toko-pakaian"
        
    slug = base_slug
    counter = 1
    while get_tenant_by_slug(master_db, slug):
        slug = f"{base_slug}-{counter}"
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
    master_db.commit()
    master_db.refresh(tenant)
    master_db.refresh(admin_user)

    # 3. Initialize Tenant SQLite Database file (tenants/{slug}.db)
    TenantManager.init_tenant_db(tenant.slug)

    # 4. Populate Tenant Store Settings, Categories, Brands & Tenant Admin User
    tenant_db = TenantManager.get_session(tenant.slug)
    try:
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
        for cat_name in req.categories:
            c_clean = cat_name.strip()
            if c_clean:
                tenant_db.add(Category(name=c_clean, slug=slugify(c_clean)))

        # Initial Brands
        for brand_name in req.brands:
            b_clean = brand_name.strip()
            if b_clean:
                tenant_db.add(Brand(name=b_clean))

        # Copy Admin User to Tenant DB for local role management
        local_user = TenantUser(
            username=admin_user.username,
            password_hash=admin_user.password_hash,
            full_name=admin_user.full_name,
            role="admin",
            is_active=True
        )
        tenant_db.add(local_user)

        tenant_db.commit()
    finally:
        tenant_db.close()

    # 5. Generate refreshed JWT token with tenant_id & tenant_slug
    token = create_access_token(data={
        "sub": admin_user.username,
        "role": admin_user.role,
        "id": admin_user.id,
        "tenant_id": tenant.id,
        "tenant_slug": tenant.slug
    })

    return tenant, token
