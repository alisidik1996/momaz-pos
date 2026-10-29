import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.modules.auth.service import get_current_user, require_admin
from app.modules.auth.models import User
from app.modules.catalog.schemas import (
    CategoryCreate, CategoryOut,
    BrandCreate, BrandOut,
    ProductCreate, ProductUpdate, ProductOut,
    VariantCreate, VariantUpdate, VariantOut,
    MatrixGenerateRequest, ScanResultOut,
    ProductAffiliateRuleUpdate, BatchAffiliateRuleUpdate
)
from app.modules.catalog import service

from app.core.storage import upload_file_to_blob_or_local

router = APIRouter(prefix="/api/catalog", tags=["Catalog (Clothing, Variants, Barcodes)"])

# Image Upload for Clothing Products (Vercel Blob / Local Storage)
@router.post("/upload-image")
async def upload_product_image(
    file: UploadFile = File(...),
    _: User = Depends(require_admin)
):
    allowed_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Format file tidak didukung. Harap upload gambar (PNG, JPG, WEBP).")

    image_url = await upload_file_to_blob_or_local(file, folder="products")
    return {"image_url": image_url}

# Bulk Import & Export (CSV)
@router.get("/import-template")
def download_import_template(_: User = Depends(require_admin)):
    csv_data = service.generate_csv_template()
    return Response(
        content=csv_data.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="template_import_produk.csv"'}
    )

@router.get("/export-csv")
def export_products_csv(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    csv_data = service.export_products_to_csv(db)
    return Response(
        content=csv_data.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="katalog_produk_pos.csv"'}
    )

@router.post("/import-csv")
async def import_products_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    if not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(status_code=400, detail="Hanya file CSV (.csv) yang didukung untuk impor massal.")
    
    content = await file.read()
    return service.import_products_from_csv(db, content)

# Categories & Brands
@router.get("/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db)):
    return service.get_categories(db)

@router.post("/categories", response_model=CategoryOut)
def create_category(cat_in: CategoryCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.create_category(db, cat_in)

@router.delete("/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.delete_category(db, category_id)

@router.get("/brands", response_model=List[BrandOut])
def get_brands(db: Session = Depends(get_db)):
    return service.get_brands(db)

@router.post("/brands", response_model=BrandOut)
def create_brand(brand_in: BrandCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.create_brand(db, brand_in)

@router.delete("/brands/{brand_id}")
def delete_brand(brand_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.delete_brand(db, brand_id)

# Products
@router.get("/products", response_model=List[ProductOut])
def get_products(
    q: Optional[str] = Query(None, description="Cari nama produk"),
    category_id: Optional[int] = Query(None, description="Filter kategori"),
    db: Session = Depends(get_db)
):
    return service.get_products(db, query=q, category_id=category_id)

@router.post("/products", response_model=ProductOut)
def create_product(prod_in: ProductCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.create_product(db, prod_in)

@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = service.get_product_by_id(db, product_id)
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    return product

# Affiliate & Member Discount Rules Batch
@router.put("/products/batch-affiliate-rules")
def batch_update_affiliate_rules(
    batch_in: BatchAffiliateRuleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    count = service.batch_update_affiliate_rules(db, batch_in.rules)
    return {"message": f"Berhasil memperbarui aturan untuk {count} produk.", "count": count}

@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, prod_in: ProductUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.update_product(db, product_id, prod_in)

@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.delete_product(db, product_id)

# Variants
@router.post("/variants", response_model=VariantOut)
def create_variant(var_in: VariantCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.create_variant(db, var_in)

@router.put("/variants/{variant_id}", response_model=VariantOut)
def update_variant(variant_id: int, var_in: VariantUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.update_variant(db, variant_id, var_in)

@router.delete("/variants/{variant_id}")
def delete_variant(variant_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.delete_variant(db, variant_id)

# Matrix Permutation Generator
@router.post("/matrix/generate", response_model=List[VariantOut])
def generate_matrix(matrix_in: MatrixGenerateRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return service.generate_product_matrix(db, matrix_in)

# Fast POS Barcode Scanner Endpoint
@router.get("/scan/{code}", response_model=ScanResultOut)
def scan_code(code: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return service.scan_barcode_lookup(db, code.strip())

# Affiliate & Member Discount Rules
@router.put("/products/{product_id}/affiliate-rules", response_model=ProductOut)
def update_product_affiliate_rule(
    product_id: int,
    rule_in: ProductAffiliateRuleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    return service.update_product_affiliate_rule(
        db=db,
        product_id=product_id,
        member_discount_type=rule_in.member_discount_type,
        member_discount_value=rule_in.member_discount_value,
        affiliate_commission_type=rule_in.affiliate_commission_type,
        affiliate_commission_value=rule_in.affiliate_commission_value
    )
