import io
import csv
import random
import re
from typing import List, Optional, Dict, Any
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.modules.catalog.models import Category, Brand, Product, ProductVariant
from app.modules.catalog.schemas import (
    CategoryCreate, BrandCreate,
    ProductCreate, ProductUpdate,
    VariantCreate, VariantUpdate,
    MatrixGenerateRequest, ScanResultOut
)

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text)

def generate_barcode(prefix: str = "899") -> str:
    """Generate 13-digit EAN-like barcode"""
    random_digits = "".join([str(random.randint(0, 9)) for _ in range(9)])
    raw = prefix + random_digits
    # Calculate checksum digit
    checksum = sum(int(d) * (3 if i % 2 == 1 else 1) for i, d in enumerate(raw)) % 10
    check_digit = (10 - checksum) % 10
    return raw + str(check_digit)

# Categories
def get_categories(db: Session) -> List[Category]:
    return db.query(Category).order_by(Category.name.asc()).all()

def create_category(db: Session, cat_in: CategoryCreate) -> Category:
    slug = slugify(cat_in.name)
    existing = db.query(Category).filter(Category.slug == slug).first()
    if existing:
        return existing
    cat = Category(name=cat_in.name, slug=slug, description=cat_in.description)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat

def delete_category(db: Session, category_id: int):
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan.")
    db.delete(cat)
    db.commit()
    return {"message": "Kategori berhasil dihapus."}

# Brands
def get_brands(db: Session) -> List[Brand]:
    return db.query(Brand).order_by(Brand.name.asc()).all()

def create_brand(db: Session, brand_in: BrandCreate) -> Brand:
    existing = db.query(Brand).filter(Brand.name == brand_in.name).first()
    if existing:
        return existing
    brand = Brand(name=brand_in.name)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand

def delete_brand(db: Session, brand_id: int):
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand tidak ditemukan.")
    db.delete(brand)
    db.commit()
    return {"message": "Brand berhasil dihapus."}

# Products
def get_products(db: Session, query: Optional[str] = None, category_id: Optional[int] = None) -> List[Product]:
    stmt = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand),
        joinedload(Product.variants)
    )
    if query:
        q = f"%{query}%"
        stmt = stmt.filter(
            or_(
                Product.name.ilike(q),
                Product.sku.ilike(q),
                Product.barcode.ilike(q)
            )
        )
    if category_id:
        stmt = stmt.filter(Product.category_id == category_id)
        
    products = stmt.order_by(Product.id.desc()).all()
    # Calculate total stock dynamically
    for p in products:
        p.total_stock = (p.stock or 0) + sum(v.stock for v in p.variants if v.is_active)
    return products

def get_product_by_id(db: Session, product_id: int) -> Optional[Product]:
    product = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand),
        joinedload(Product.variants)
    ).filter(Product.id == product_id).first()
    if product:
        product.total_stock = (product.stock or 0) + sum(v.stock for v in product.variants if v.is_active)
    return product

def create_product(db: Session, prod_in: ProductCreate) -> Product:
    sku = prod_in.sku
    if not sku:
        prefix = "".join([w[0].upper() for w in prod_in.name.split() if w])[:4]
        sku = f"{prefix}-{random.randint(100, 999)}"
        
    barcode = prod_in.barcode
    if not barcode:
        barcode = generate_barcode()

    product = Product(
        name=prod_in.name,
        sku=sku,
        barcode=barcode,
        category_id=prod_in.category_id,
        brand_id=prod_in.brand_id,
        description=prod_in.description,
        cost_price=prod_in.cost_price or 0.0,
        base_price=prod_in.base_price or 0.0,
        discount_price=prod_in.discount_price or 0.0,
        stock=prod_in.stock or 0,
        min_stock=prod_in.min_stock if prod_in.min_stock is not None else 5,
        image_url=prod_in.image_url,
        is_active=prod_in.is_active
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    product.total_stock = product.stock
    return product

def update_product(db: Session, product_id: int, prod_in: ProductUpdate) -> Product:
    product = get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    
    for field, val in prod_in.model_dump(exclude_unset=True).items():
        setattr(product, field, val)
        
    db.commit()
    db.refresh(product)
    product.total_stock = (product.stock or 0) + sum(v.stock for v in product.variants if v.is_active)
    return product

def delete_product(db: Session, product_id: int):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    db.delete(product)
    db.commit()
    return {"message": "Produk berhasil dihapus."}

# Variants
def get_variant_by_id(db: Session, variant_id: int) -> Optional[ProductVariant]:
    return db.query(ProductVariant).options(joinedload(ProductVariant.product)).filter(ProductVariant.id == variant_id).first()

def get_variant_by_barcode(db: Session, barcode_or_sku: str) -> Optional[ProductVariant]:
    return db.query(ProductVariant).options(joinedload(ProductVariant.product)).filter(
        (ProductVariant.barcode == barcode_or_sku) | (ProductVariant.sku == barcode_or_sku)
    ).first()

def create_variant(db: Session, var_in: VariantCreate) -> ProductVariant:
    product = get_product_by_id(db, var_in.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk induk tidak ditemukan.")
    
    sku = var_in.sku
    if not sku:
        sku = f"PROD-{product.id}-{var_in.color.upper()[:3]}-{var_in.size.upper()}"
        
    barcode = var_in.barcode
    if not barcode:
        barcode = generate_barcode()
        
    variant = ProductVariant(
        product_id=var_in.product_id,
        sku=sku,
        barcode=barcode,
        size=var_in.size,
        color=var_in.color,
        cost_price=var_in.cost_price,
        sell_price=var_in.sell_price if var_in.sell_price > 0 else product.base_price,
        stock=var_in.stock,
        min_stock=var_in.min_stock,
        is_active=var_in.is_active
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant

def update_variant(db: Session, variant_id: int, var_in: VariantUpdate) -> ProductVariant:
    variant = get_variant_by_id(db, variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Varian produk tidak ditemukan.")
    
    for field, val in var_in.model_dump(exclude_unset=True).items():
        setattr(variant, field, val)
        
    db.commit()
    db.refresh(variant)
    return variant

def delete_variant(db: Session, variant_id: int):
    variant = get_variant_by_id(db, variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail="Varian produk tidak ditemukan.")
    db.delete(variant)
    db.commit()
    return {"message": "Varian berhasil dihapus."}

# Matrix Generator (Fashion Retail Key Feature)
def generate_product_matrix(db: Session, matrix_data: MatrixGenerateRequest) -> List[ProductVariant]:
    product = get_product_by_id(db, matrix_data.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk induk tidak ditemukan.")
    
    prefix = matrix_data.sku_prefix
    if not prefix:
        words = product.name.split()
        prefix = "".join([w[0].upper() for w in words if w])[:4]
        
    created_variants = []
    for color in matrix_data.colors:
        color_clean = color.strip()
        for size in matrix_data.sizes:
            size_clean = size.strip()
            sku = f"{prefix}-{slugify(color_clean).upper()}-{size_clean.upper()}"
            
            # Check if this permutation already exists
            existing = db.query(ProductVariant).filter(
                ProductVariant.product_id == product.id,
                ProductVariant.size == size_clean,
                ProductVariant.color == color_clean
            ).first()
            
            if existing:
                continue
                
            variant = ProductVariant(
                product_id=product.id,
                sku=sku,
                barcode=generate_barcode(),
                size=size_clean,
                color=color_clean,
                cost_price=matrix_data.cost_price,
                sell_price=matrix_data.sell_price if matrix_data.sell_price > 0 else product.base_price,
                stock=matrix_data.initial_stock,
                min_stock=matrix_data.min_stock,
                is_active=True
            )
            db.add(variant)
            created_variants.append(variant)
            
    db.commit()
    for v in created_variants:
        db.refresh(v)
    return created_variants

# Fast Scanner Lookup for POS
def scan_barcode_lookup(db: Session, code: str) -> ScanResultOut:
    # 1. Lookup Product directly by barcode or SKU
    prod = db.query(Product).options(joinedload(Product.category)).filter(
        (Product.barcode == code) | (Product.sku == code)
    ).first()
    
    if prod:
        cat_name = prod.category.name if prod.category else None
        effective_sell = prod.discount_price if (prod.discount_price and prod.discount_price > 0) else prod.base_price
        return ScanResultOut(
            product_id=prod.id,
            product_name=prod.name,
            category_name=cat_name,
            sku=prod.sku or "",
            barcode=prod.barcode or "",
            sell_price=effective_sell,
            cost_price=prod.cost_price or 0.0,
            stock=prod.stock or 0,
            is_active=prod.is_active,
            variant_id=None,
            size="",
            color="",
            member_discount_type=prod.member_discount_type or "percent",
            member_discount_value=prod.member_discount_value or 0.0,
            affiliate_commission_type=prod.affiliate_commission_type or "percent",
            affiliate_commission_value=prod.affiliate_commission_value or 0.0
        )

    # 2. Fallback to variant if exists in legacy db
    variant = get_variant_by_barcode(db, code)
    if variant and variant.product:
        p = variant.product
        cat_name = p.category.name if p.category else None
        return ScanResultOut(
            product_id=p.id,
            product_name=p.name,
            category_name=cat_name,
            sku=variant.sku,
            barcode=variant.barcode,
            sell_price=variant.sell_price,
            cost_price=variant.cost_price,
            stock=variant.stock,
            is_active=variant.is_active,
            variant_id=variant.id,
            size=variant.size,
            color=variant.color,
            member_discount_type=p.member_discount_type or "percent",
            member_discount_value=p.member_discount_value or 0.0,
            affiliate_commission_type=p.affiliate_commission_type or "percent",
            affiliate_commission_value=p.affiliate_commission_value or 0.0
        )

    raise HTTPException(status_code=404, detail=f"Barcode atau SKU '{code}' tidak terdaftar.")

# ----------------- Bulk Import / Export (CSV) -----------------

CSV_HEADERS = [
    "nama_produk",
    "kategori",
    "brand",
    "deskripsi",
    "sku",
    "barcode",
    "harga_modal",
    "harga_jual",
    "harga_diskon",
    "stok",
    "min_stok",
    "foto_url"
]

def generate_csv_template() -> str:
    """Generate sample CSV template"""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()

    writer.writerow({
        "nama_produk": "Kemeja Flanel Slim Fit",
        "kategori": "Atasan Pria",
        "brand": "Erigo",
        "deskripsi": "Bahan katun flanel premium lembut dan tebal",
        "sku": "KMT-FLN-01",
        "barcode": "8991122334455",
        "harga_modal": 95000,
        "harga_jual": 175000,
        "harga_diskon": 149000,
        "stok": 25,
        "min_stok": 5,
        "foto_url": ""
    })
    writer.writerow({
        "nama_produk": "Kaos Polos Cotton Combed 30s",
        "kategori": "Kaos Distro",
        "brand": "Roughneck",
        "deskripsi": "Bahan adem 100% katun combed 30s",
        "sku": "TSH-PLN-01",
        "barcode": "8992233445566",
        "harga_modal": 35000,
        "harga_jual": 75000,
        "harga_diskon": 0,
        "stok": 50,
        "min_stok": 10,
        "foto_url": ""
    })
    return output.getvalue()

def export_products_to_csv(db: Session) -> str:
    """Export all products into CSV"""
    products = get_products(db)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()

    for p in products:
        cat_name = p.category.name if p.category else ""
        brand_name = p.brand.name if p.brand else ""
        writer.writerow({
            "nama_produk": p.name,
            "kategori": cat_name,
            "brand": brand_name,
            "deskripsi": p.description or "",
            "sku": p.sku or "",
            "barcode": p.barcode or "",
            "harga_modal": p.cost_price or 0,
            "harga_jual": p.base_price or 0,
            "harga_diskon": p.discount_price or 0,
            "stok": p.stock if p.stock is not None else (p.total_stock or 0),
            "min_stok": p.min_stock or 5,
            "foto_url": p.image_url or ""
        })

    return output.getvalue()

def import_products_from_csv(db: Session, file_content: bytes) -> Dict[str, Any]:
    """Bulk import products from CSV file with delimiter auto-detection and robust encoding"""
    from app.modules.inventory.models import StockMovement

    # 1. Decode bytes (supports UTF-8-SIG/BOM, UTF-8, CP1252, Latin-1)
    text = None
    for encoding in ["utf-8-sig", "utf-8", "cp1252", "latin-1"]:
        try:
            text = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise HTTPException(status_code=400, detail="Format encoding file tidak didukung. Harap simpan file sebagai CSV UTF-8.")

    # Strip any leading BOMs or zero-width spaces that might still be present
    text = text.lstrip("\ufeff\u200b\r\n ")
    if not text.strip():
        raise HTTPException(status_code=400, detail="File CSV kosong.")

    # 2. Detect delimiter (comma vs semicolon vs tab)
    first_line = text.splitlines()[0]
    semi_count = first_line.count(";")
    comma_count = first_line.count(",")
    tab_count = first_line.count("\t")

    delimiter = ","
    if semi_count > comma_count and semi_count > tab_count:
        delimiter = ";"
    elif tab_count > comma_count and tab_count > semi_count:
        delimiter = "\t"

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="File CSV tidak memiliki baris header.")

    # Normalize header mapping
    header_map = {}
    for fn in reader.fieldnames:
        if fn:
            clean_fn = fn.replace("\ufeff", "").replace("\u200b", "").strip().lower().replace(" ", "_")
            header_map[clean_fn] = fn

    def get_val(row, *aliases, default=""):
        for a in aliases:
            clean_a = a.replace("\ufeff", "").strip().lower().replace(" ", "_")
            if clean_a in header_map:
                val = row.get(header_map[clean_a])
                if val is not None and str(val).strip():
                    return str(val).strip()
            # Also check direct keys in row
            for k in row:
                if k and k.replace("\ufeff", "").strip().lower().replace(" ", "_") == clean_a:
                    val = row[k]
                    if val is not None and str(val).strip():
                        return str(val).strip()
        return default

    def parse_price(val_str, default=0.0):
        if not val_str:
            return default
        s = str(val_str).replace("Rp", "").replace("rp", "").replace("RP", "").strip()
        if not s:
            return default
        if "." in s and "," in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        elif "." in s:
            parts = s.split(".")
            if len(parts) > 1 and len(parts[-1]) == 3 and all(len(p) <= 3 for p in parts[:-1]):
                s = s.replace(".", "")
        try:
            return float(s)
        except ValueError:
            return default

    def parse_int(val_str, default=0):
        if not val_str:
            return default
        s = str(val_str).replace("pcs", "").replace(" ", "").strip()
        try:
            return int(float(s.replace(",", ".")))
        except (ValueError, TypeError):
            return default

    # Track categories & brands cache
    categories_cache = {c.name.lower(): c for c in db.query(Category).all()}
    brands_cache = {b.name.lower(): b for b in db.query(Brand).all()}

    products_created_count = 0
    products_updated_count = 0
    variants_created_count = 0
    rows_processed = 0
    errors = []

    # Map product cache by (sku, barcode, name.lower())
    product_cache = {}
    for p in db.query(Product).options(joinedload(Product.variants)).all():
        if p.sku:
            product_cache[p.sku.lower()] = p
        if p.barcode:
            product_cache[p.barcode.lower()] = p
        product_cache[p.name.lower()] = p

    for row_idx, row in enumerate(reader, start=2):
        name = get_val(row, "nama_produk", "nama", "product_name")
        if not name:
            continue

        rows_processed += 1
        savepoint = db.begin_nested()
        try:
            # Category
            cat_name = get_val(row, "kategori", "category")
            category_id = None
            if cat_name:
                cat_lower = cat_name.lower()
                if cat_lower not in categories_cache:
                    new_cat = Category(name=cat_name, slug=slugify(cat_name))
                    db.add(new_cat)
                    db.flush()
                    categories_cache[cat_lower] = new_cat
                category_id = categories_cache[cat_lower].id

            # Brand
            brand_name = get_val(row, "brand", "merek")
            brand_id = None
            if brand_name:
                brand_lower = brand_name.lower()
                if brand_lower not in brands_cache:
                    new_brand = Brand(name=brand_name)
                    db.add(new_brand)
                    db.flush()
                    brands_cache[brand_lower] = new_brand
                brand_id = brands_cache[brand_lower].id

            # Prices & Stock
            base_price = parse_price(get_val(row, "harga_normal", "harga", "base_price"), default=0.0)
            discount_price = parse_price(get_val(row, "harga_diskon", "diskon", "discount_price"), default=0.0)
            harga_modal = parse_price(get_val(row, "harga_modal", "hpp", "cost_price"), default=0.0)
            harga_jual = parse_price(get_val(row, "harga_jual", "sell_price"), default=base_price if base_price > 0 else 0.0)
            if base_price <= 0 and harga_jual > 0:
                base_price = harga_jual

            sku_induk = get_val(row, "sku", "sku_induk", "sku_produk", "product_sku")
            barcode_induk = get_val(row, "barcode", "barcode_induk", "barcode_produk", "product_barcode")
            desc = get_val(row, "deskripsi", "description")
            foto_url = get_val(row, "foto_url", "image_url", "gambar")

            stok = parse_int(get_val(row, "stok", "stok_awal", "stock"), default=0)
            min_stok = parse_int(get_val(row, "min_stok", "min_stock"), default=3)

            # Find matching product by SKU, Barcode, or Name
            product = None
            if sku_induk and sku_induk.lower() in product_cache:
                product = product_cache[sku_induk.lower()]
            elif barcode_induk and barcode_induk.lower() in product_cache:
                product = product_cache[barcode_induk.lower()]
            elif name.lower() in product_cache:
                product = product_cache[name.lower()]

            if not product:
                # Ensure unique SKU
                if not sku_induk:
                    prefix = "".join([w[0].upper() for w in name.split() if w])[:4] or "PRD"
                    sku_induk = f"{prefix}-{random.randint(100, 999)}"
                    while sku_induk.lower() in product_cache:
                        sku_induk = f"{prefix}-{random.randint(1000, 9999)}"

                # Ensure unique Barcode
                if not barcode_induk:
                    barcode_induk = generate_barcode()
                    while barcode_induk.lower() in product_cache:
                        barcode_induk = generate_barcode()

                product = Product(
                    name=name,
                    sku=sku_induk,
                    barcode=barcode_induk,
                    category_id=category_id,
                    brand_id=brand_id,
                    description=desc,
                    cost_price=harga_modal,
                    base_price=base_price,
                    discount_price=discount_price,
                    stock=stok,
                    min_stock=min_stok,
                    image_url=foto_url if foto_url else None,
                    is_active=True
                )
                db.add(product)
                db.flush()
                product.variants = []

                product_cache[name.lower()] = product
                if sku_induk:
                    product_cache[sku_induk.lower()] = product
                if barcode_induk:
                    product_cache[barcode_induk.lower()] = product
                products_created_count += 1

                if stok > 0:
                    db.add(StockMovement(
                        product_id=product.id,
                        variant_id=None,
                        user_id=None,
                        change_qty=stok,
                        current_stock=product.stock,
                        movement_type="restock",
                        reference="IMPORT-CSV",
                        note=f"Impor CSV baris {row_idx}"
                    ))
            else:
                product.stock = (product.stock or 0) + stok
                if base_price > 0:
                    product.base_price = base_price
                if discount_price >= 0:
                    product.discount_price = discount_price
                if harga_modal > 0:
                    product.cost_price = harga_modal
                if category_id and not product.category_id:
                    product.category_id = category_id
                if brand_id and not product.brand_id:
                    product.brand_id = brand_id
                if foto_url and not product.image_url:
                    product.image_url = foto_url
                if desc and not product.description:
                    product.description = desc
                if min_stok:
                    product.min_stock = min_stok

                products_updated_count += 1

                if stok > 0:
                    db.add(StockMovement(
                        product_id=product.id,
                        variant_id=None,
                        user_id=None,
                        change_qty=stok,
                        current_stock=product.stock,
                        movement_type="restock",
                        reference="IMPORT-CSV",
                        note=f"Impor CSV baris {row_idx}"
                    ))

            savepoint.commit()
        except Exception as ex:
            savepoint.rollback()
            errors.append(f"Baris {row_idx} ({name}): {str(ex)}")

    db.commit()

    return {
        "status": "success",
        "rows_processed": rows_processed,
        "products_created": products_created_count,
        "products_updated": products_updated_count,
        "variants_created": variants_created_count,
        "errors": errors
    }

# ----------------- Affiliate & Member Discount Rules -----------------

def update_product_affiliate_rule(
    db: Session,
    product_id: int,
    member_discount_type: str,
    member_discount_value: float,
    affiliate_commission_type: str,
    affiliate_commission_value: float
) -> Product:
    product = get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")

    product.member_discount_type = member_discount_type
    product.member_discount_value = max(0.0, float(member_discount_value))
    product.affiliate_commission_type = affiliate_commission_type
    product.affiliate_commission_value = max(0.0, float(affiliate_commission_value))

    db.commit()
    db.refresh(product)
    return product

def batch_update_affiliate_rules(db: Session, rules: list) -> int:
    updated_count = 0
    for r in rules:
        prod = db.query(Product).filter(Product.id == r.product_id).first()
        if prod:
            prod.member_discount_type = r.member_discount_type
            prod.member_discount_value = max(0.0, float(r.member_discount_value))
            prod.affiliate_commission_type = r.affiliate_commission_type
            prod.affiliate_commission_value = max(0.0, float(r.affiliate_commission_value))
            updated_count += 1
    db.commit()
    return updated_count
