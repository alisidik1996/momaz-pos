from typing import Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.security import hash_password, create_access_token
from app.core.models import StoreSettings
from app.modules.auth.models import User
from app.modules.catalog.models import Category, Brand
from app.modules.catalog.service import slugify
from app.modules.setup.schemas import SetupInitRequest

def check_setup_required(db: Session) -> bool:
    count = db.query(User).count()
    return count == 0

def initialize_system(db: Session, req: SetupInitRequest) -> Tuple[User, str]:
    if not check_setup_required(db):
        raise HTTPException(
            status_code=400,
            detail="Sistem sudah pernah diinisialisasi sebelumnya. Setup wizard ditutup demi keamanan."
        )

    # 1. Create Admin User
    admin = User(
        username=req.admin.username.strip(),
        password_hash=hash_password(req.admin.password),
        full_name=req.admin.full_name.strip(),
        role="admin",
        is_active=True
    )
    db.add(admin)

    # 2. Setup Store Settings
    footer_text = req.store.receipt_footer
    if not footer_text:
        footer_text = (
            f"Terima kasih telah berbelanja di {req.store.store_name}!\n"
            f"Barang dapat ditukar maksimal {req.store.return_policy_days} hari setelah pembelian dengan membawa struk ini & tag utuh."
        )

    settings = db.query(StoreSettings).first()
    if not settings:
        settings = StoreSettings()
        db.add(settings)

    settings.store_name = req.store.store_name.strip()
    settings.tagline = req.store.tagline or "Fashion & Apparel Distro"
    settings.address = req.store.address or "Alamat Toko Belum Diatur"
    settings.phone = req.store.phone or "-"
    settings.email = req.store.email or ""
    settings.return_policy_days = req.store.return_policy_days or 3
    settings.tax_rate = req.store.tax_rate or 0.0
    settings.is_tax_enabled = req.store.is_tax_enabled
    settings.receipt_footer = footer_text

    # 3. Create Categories
    for cname in req.categories:
        cname_clean = cname.strip()
        if not cname_clean:
            continue
        cslug = slugify(cname_clean)
        cat = db.query(Category).filter(Category.slug == cslug).first()
        if not cat:
            db.add(Category(name=cname_clean, slug=cslug))

    # 4. Create Brands
    for bname in req.brands:
        bname_clean = bname.strip()
        if not bname_clean:
            continue
        brand = db.query(Brand).filter(Brand.name == bname_clean).first()
        if not brand:
            db.add(Brand(name=bname_clean))

    db.commit()
    db.refresh(admin)

    # Generate JWT token for auto-login
    token = create_access_token(data={"sub": admin.username, "role": admin.role, "id": admin.id})
    return admin, token
