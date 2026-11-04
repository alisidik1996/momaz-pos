import csv
import io
import math
import re
import secrets
from typing import List, Optional, Dict, Any
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session, joinedload

from app.core.csv_utils import safe_csv_cell
from app.core.transactions import transactional
from app.modules.catalog.models import Category, Brand, Product, ProductVariant
from app.modules.catalog.schemas import (
    CategoryCreate, BrandCreate, ProductCreate, ProductUpdate, VariantCreate,
    VariantUpdate, MatrixGenerateRequest, ScanResultOut, ProductAffiliateRuleUpdate,
)


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value.lower().strip())
    return re.sub(r"[\s_-]+", "-", value).strip("-")


def generate_barcode(prefix: str = "899") -> str:
    if not re.fullmatch(r"[0-9]{3}", prefix):
        raise ValueError("Prefix barcode harus berisi 3 angka.")
    raw = prefix + "".join(secrets.choice("0123456789") for _ in range(9))
    checksum = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(raw))
    return raw + str((-checksum) % 10)


def _code_exists(db, code, product_id=None, variant_id=None):
    normalized = code.strip().lower()
    products = db.query(Product).filter(or_(func.lower(Product.sku) == normalized, func.lower(Product.barcode) == normalized))
    variants = db.query(ProductVariant).filter(or_(func.lower(ProductVariant.sku) == normalized, func.lower(ProductVariant.barcode) == normalized))
    if product_id is not None:
        products = products.filter(Product.id != product_id)
    if variant_id is not None:
        variants = variants.filter(ProductVariant.id != variant_id)
    return products.first() is not None or variants.first() is not None


def _check_codes(db, sku, barcode, product_id=None, variant_id=None):
    for code in (sku, barcode):
        if code and _code_exists(db, code, product_id, variant_id):
            raise HTTPException(status_code=400, detail="SKU atau barcode sudah digunakan oleh produk lain.")


def _new_barcode(db):
    for _ in range(100):
        code = generate_barcode()
        if not _code_exists(db, code):
            return code
    raise HTTPException(status_code=503, detail="Gagal membuat barcode unik. Silakan coba kembali.")


def _validate_product_references(db, category_id, brand_id):
    if category_id is not None and db.get(Category, category_id) is None:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan.")
    if brand_id is not None and db.get(Brand, brand_id) is None:
        raise HTTPException(status_code=404, detail="Brand tidak ditemukan.")


def get_categories(db: Session) -> List[Category]:
    return db.query(Category).order_by(Category.name.asc()).all()


@transactional
def create_category(db: Session, cat_in: CategoryCreate) -> Category:
    slug = slugify(cat_in.name)
    existing = db.query(Category).filter(Category.slug == slug).first()
    if existing:
        return existing
    category = Category(name=cat_in.name, slug=slug, description=cat_in.description)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@transactional
def delete_category(db: Session, category_id: int):
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Kategori tidak ditemukan.")
    db.delete(category)
    db.commit()
    return {"message": "Kategori berhasil dihapus."}


def get_brands(db: Session) -> List[Brand]:
    return db.query(Brand).order_by(Brand.name.asc()).all()


@transactional
def create_brand(db: Session, brand_in: BrandCreate) -> Brand:
    existing = db.query(Brand).filter(Brand.name == brand_in.name).first()
    if existing:
        return existing
    brand = Brand(name=brand_in.name)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@transactional
def delete_brand(db: Session, brand_id: int):
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail="Brand tidak ditemukan.")
    db.delete(brand)
    db.commit()
    return {"message": "Brand berhasil dihapus."}


def _set_total_stock(product):
    product.total_stock = (product.stock or 0) + sum(variant.stock or 0 for variant in product.variants if variant.is_active)
    return product


def get_products(db: Session, query: Optional[str] = None, category_id: Optional[int] = None) -> List[Product]:
    statement = db.query(Product).options(joinedload(Product.category), joinedload(Product.brand), joinedload(Product.variants))
    if query:
        pattern = f"%{query}%"
        statement = statement.filter(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern), Product.barcode.ilike(pattern)))
    if category_id:
        statement = statement.filter(Product.category_id == category_id)
    return [_set_total_stock(product) for product in statement.order_by(Product.id.desc()).all()]


def get_product_by_id(db: Session, product_id: int) -> Optional[Product]:
    product = db.query(Product).options(joinedload(Product.category), joinedload(Product.brand), joinedload(Product.variants)).filter(Product.id == product_id).first()
    return _set_total_stock(product) if product is not None else None


@transactional
def create_product(db: Session, prod_in: ProductCreate) -> Product:
    data = prod_in.model_dump()
    prefix = "".join(word[0].upper() for word in prod_in.name.split())[:4] or "PRD"
    data["sku"] = (prod_in.sku or f"{prefix}-{uuid4().hex[:10].upper()}").strip()
    data["barcode"] = (prod_in.barcode or _new_barcode(db)).strip()
    _check_codes(db, data["sku"], data["barcode"])
    _validate_product_references(db, prod_in.category_id, prod_in.brand_id)
    product = Product(**data)
    db.add(product)
    db.commit()
    db.refresh(product)
    return _set_total_stock(product)


@transactional
def update_product(db: Session, product_id: int, prod_in: ProductUpdate) -> Product:
    product = get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    data = prod_in.model_dump(exclude_unset=True)
    for field in ("name", "cost_price", "base_price", "stock", "min_stock", "is_active"):
        if field in data and data[field] is None:
            raise HTTPException(status_code=400, detail=f"Field {field} tidak boleh kosong.")
    _check_codes(db, data.get("sku", product.sku), data.get("barcode", product.barcode), product_id=product.id)
    _validate_product_references(db, data.get("category_id", product.category_id), data.get("brand_id", product.brand_id))
    for field, value in data.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return _set_total_stock(product)


@transactional
def delete_product(db: Session, product_id: int):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    db.delete(product)
    db.commit()
    return {"message": "Produk berhasil dihapus."}


def get_variant_by_id(db: Session, variant_id: int) -> Optional[ProductVariant]:
    return db.query(ProductVariant).options(joinedload(ProductVariant.product)).filter(ProductVariant.id == variant_id).first()


def get_variant_by_barcode(db: Session, barcode_or_sku: str) -> Optional[ProductVariant]:
    code = barcode_or_sku.strip().lower()
    return db.query(ProductVariant).options(joinedload(ProductVariant.product)).filter(or_(func.lower(ProductVariant.barcode) == code, func.lower(ProductVariant.sku) == code)).first()


@transactional
def create_variant(db: Session, var_in: VariantCreate) -> ProductVariant:
    product = get_product_by_id(db, var_in.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produk induk tidak ditemukan.")
    data = var_in.model_dump()
    data["sku"] = (var_in.sku or f"PROD-{product.id}-{uuid4().hex[:10].upper()}").strip()
    data["barcode"] = (var_in.barcode or _new_barcode(db)).strip()
    if data["sell_price"] == 0:
        data["sell_price"] = product.base_price
    _check_codes(db, data["sku"], data["barcode"])
    variant = ProductVariant(**data)
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


@transactional
def update_variant(db: Session, variant_id: int, var_in: VariantUpdate) -> ProductVariant:
    variant = get_variant_by_id(db, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Varian produk tidak ditemukan.")
    data = var_in.model_dump(exclude_unset=True)
    if any(value is None for value in data.values()):
        raise HTTPException(status_code=400, detail="Field varian tidak boleh kosong.")
    _check_codes(db, data.get("sku", variant.sku), data.get("barcode", variant.barcode), variant_id=variant.id)
    for field, value in data.items():
        setattr(variant, field, value)
    db.commit()
    db.refresh(variant)
    return variant


@transactional
def delete_variant(db: Session, variant_id: int):
    variant = db.get(ProductVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Varian produk tidak ditemukan.")
    db.delete(variant)
    db.commit()
    return {"message": "Varian berhasil dihapus."}


@transactional
def generate_product_matrix(db: Session, matrix_data: MatrixGenerateRequest) -> List[ProductVariant]:
    product = get_product_by_id(db, matrix_data.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produk induk tidak ditemukan.")
    prefix = matrix_data.sku_prefix or "".join(word[0].upper() for word in product.name.split())[:4] or "PRD"
    created = []
    for color in dict.fromkeys(matrix_data.colors):
        for size in dict.fromkeys(matrix_data.sizes):
            if db.query(ProductVariant).filter_by(product_id=product.id, color=color, size=size).first():
                continue
            sku = f"{prefix[:8]}-{product.id}-{slugify(color).upper()[:8]}-{size.upper()[:8]}"
            if _code_exists(db, sku):
                sku = f"{sku}-{uuid4().hex[:8].upper()}"
            variant = ProductVariant(
                product_id=product.id, color=color, size=size, sku=sku, barcode=_new_barcode(db),
                cost_price=matrix_data.cost_price, sell_price=matrix_data.sell_price or product.base_price,
                stock=matrix_data.initial_stock, min_stock=matrix_data.min_stock, is_active=True,
            )
            db.add(variant)
            db.flush()
            created.append(variant)
    db.commit()
    for variant in created:
        db.refresh(variant)
    return created


def scan_barcode_lookup(db: Session, code: str) -> ScanResultOut:
    normalized = code.strip().lower()
    product = db.query(Product).options(joinedload(Product.category)).filter(or_(func.lower(Product.barcode) == normalized, func.lower(Product.sku) == normalized)).first()
    variant = None if product is not None else get_variant_by_barcode(db, code)
    if product is None:
        product = variant.product if variant else None
    if product is None:
        raise HTTPException(status_code=404, detail=f"Barcode atau SKU '{code}' tidak terdaftar.")
    return ScanResultOut(
        product_id=product.id, variant_id=variant.id if variant else None, product_name=product.name,
        category_name=product.category.name if product.category else None,
        sku=variant.sku if variant else product.sku or "", barcode=variant.barcode if variant else product.barcode or "",
        sell_price=variant.sell_price if variant else product.discount_price or product.base_price,
        cost_price=variant.cost_price if variant else product.cost_price or 0.0,
        stock=(variant.stock if variant else product.stock) or 0,
        is_active=bool(product.is_active and (variant.is_active if variant else True)),
        color=variant.color if variant else "", size=variant.size if variant else "",
        member_discount_type=product.member_discount_type or "percent", member_discount_value=product.member_discount_value or 0,
        affiliate_commission_type=product.affiliate_commission_type or "percent", affiliate_commission_value=product.affiliate_commission_value or 0,
    )


CSV_HEADERS = ["nama_produk", "kategori", "brand", "deskripsi", "sku", "barcode", "harga_modal", "harga_jual", "harga_diskon", "stok", "min_stok", "foto_url"]


def generate_csv_template() -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    writer.writerow(dict(zip(CSV_HEADERS, ["Kemeja Flanel Slim Fit", "Atasan Pria", "Erigo", "Bahan katun flanel tebal dan adem", "KMT-FLN-01", "8991122334455", 95000, 175000, 149000, 25, 5, ""])))
    writer.writerow(dict(zip(CSV_HEADERS, ["Kaos Polos Cotton Combed 30s", "Kaos Distro", "Roughneck", "Bahan adem 100% katun combed 30s", "TSH-PLN-01", "8992233445566", 35000, 75000, 0, 50, 10, ""])))
    return output.getvalue()


def export_products_to_csv(db: Session) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)
    writer.writeheader()
    for product in get_products(db):
        values = [
            product.name, product.category.name if product.category else "", product.brand.name if product.brand else "",
            product.description or "", product.sku or "", product.barcode or "", product.cost_price or 0,
            product.base_price or 0, product.discount_price or 0, product.stock or 0,
            product.min_stock if product.min_stock is not None else 5, product.image_url or "",
        ]
        writer.writerow({key: safe_csv_cell(value) for key, value in zip(CSV_HEADERS, values)})
    return output.getvalue()


def _parse_number(value, default=0.0, integer=False):
    if value is None or not str(value).strip():
        return default
    value = re.sub(r"(?i)rp|pcs", "", str(value)).replace(" ", "").strip()
    if "." in value and "," in value:
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    elif not integer and "." in value:
        parts = value.split(".")
        if len(parts[-1]) == 3 and all(len(part) <= 3 for part in parts[:-1]):
            value = value.replace(".", "")
    number = float(value)
    if not math.isfinite(number) or number < 0 or (integer and not number.is_integer()):
        raise ValueError("Harga dan stok harus berupa angka yang valid dan tidak negatif.")
    return int(number) if integer else number


@transactional
def import_products_from_csv(db: Session, file_content: bytes) -> Dict[str, Any]:
    from app.modules.inventory.models import StockMovement

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            content = file_content.decode(encoding).lstrip("\ufeff\u200b\r\n ")
            break
        except UnicodeDecodeError:
            continue
    if not content.strip():
        raise HTTPException(status_code=400, detail="File CSV kosong.")
    first_line = content.splitlines()[0]
    delimiter = max((",", ";", "\t"), key=first_line.count)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    headers = {name.replace("\ufeff", "").replace("\u200b", "").strip().lower().replace(" ", "_"): name for name in reader.fieldnames or []}
    if not {"nama_produk", "nama", "product_name"} & headers.keys():
        raise HTTPException(status_code=400, detail="Header nama_produk tidak ditemukan.")

    def value(row, *aliases, default=None):
        for alias in aliases:
            raw = row.get(headers.get(alias))
            if raw is not None and raw.strip():
                return raw.strip()
        return default

    categories = {category.slug: category for category in db.query(Category).all()}
    brands = {brand.name.lower(): brand for brand in db.query(Brand).all()}
    created = updated = processed = 0
    errors = []
    for line_number, row in enumerate(reader, start=2):
        name = value(row, "nama_produk", "nama", "product_name")
        if not name:
            continue
        processed += 1
        pending_categories = categories.copy()
        pending_brands = brands.copy()
        try:
            with db.begin_nested():
                sku = value(row, "sku", "sku_induk", "sku_produk", "product_sku")
                barcode = value(row, "barcode", "barcode_induk", "barcode_produk", "product_barcode")
                matches = []
                if sku:
                    matches.extend(db.query(Product).filter(func.lower(Product.sku) == sku.lower()).all())
                if barcode:
                    matches.extend(db.query(Product).filter(func.lower(Product.barcode) == barcode.lower()).all())
                if len({product.id for product in matches}) > 1:
                    raise ValueError("SKU dan barcode merujuk pada produk yang berbeda.")
                product = matches[0] if matches else None
                if product is None and not sku and not barcode:
                    product = db.query(Product).filter(func.lower(Product.name) == name.lower()).first()
                stock = _parse_number(value(row, "stok", "stok_awal", "stock"), integer=True)
                data = ProductCreate(
                    name=name, sku=sku, barcode=barcode,
                    base_price=_parse_number(value(row, "harga_normal", "harga", "base_price", "harga_jual", "sell_price"), product.base_price if product else 0),
                    cost_price=_parse_number(value(row, "harga_modal", "hpp", "cost_price"), product.cost_price if product else 0),
                    discount_price=_parse_number(value(row, "harga_diskon", "diskon", "discount_price"), product.discount_price or 0 if product else 0),
                    stock=stock, min_stock=_parse_number(value(row, "min_stok", "min_stock"), product.min_stock if product else 5, integer=True),
                    description=value(row, "deskripsi", "description", default=product.description if product else None),
                    image_url=value(row, "foto_url", "image_url", "gambar", default=product.image_url if product else None),
                )
                category_name = value(row, "kategori", "category")
                if category_name:
                    category_name = CategoryCreate(name=category_name).name
                    category_slug = slugify(category_name)
                    if category_slug not in pending_categories:
                        category = Category(name=category_name, slug=category_slug)
                        db.add(category)
                        db.flush()
                        pending_categories[category_slug] = category
                    data.category_id = pending_categories[category_slug].id
                brand_name = value(row, "brand", "merek")
                if brand_name:
                    brand_name = BrandCreate(name=brand_name).name
                    if brand_name.lower() not in pending_brands:
                        brand = Brand(name=brand_name)
                        db.add(brand)
                        db.flush()
                        pending_brands[brand_name.lower()] = brand
                    data.brand_id = pending_brands[brand_name.lower()].id
                is_new = product is None
                if is_new:
                    values = data.model_dump()
                    values["sku"] = sku or f"PRD-{uuid4().hex[:10].upper()}"
                    values["barcode"] = barcode or _new_barcode(db)
                    _check_codes(db, values["sku"], values["barcode"])
                    product = Product(**values)
                    db.add(product)
                    db.flush()
                else:
                    _check_codes(db, sku, barcode, product_id=product.id)
                    for field in ("name", "base_price", "cost_price", "discount_price", "min_stock", "description", "image_url"):
                        setattr(product, field, getattr(data, field))
                    if sku:
                        product.sku = sku
                    if barcode:
                        product.barcode = barcode
                    if data.category_id is not None:
                        product.category_id = data.category_id
                    if data.brand_id is not None:
                        product.brand_id = data.brand_id
                    db.flush()
                    if stock:
                        result = db.execute(update(Product).where(Product.id == product.id, func.coalesce(Product.stock, 0) + stock <= 2_147_483_647).values(stock=func.coalesce(Product.stock, 0) + stock).returning(Product.stock)).scalar_one_or_none()
                        if result is None:
                            raise ValueError("Jumlah stok melebihi batas.")
                if stock:
                    db.add(StockMovement(product_id=product.id, change_qty=stock, current_stock=product.stock, movement_type="restock", reference="IMPORT-CSV", note=f"Impor CSV baris {line_number}"))
                db.flush()
            categories = pending_categories
            brands = pending_brands
            created += int(is_new)
            updated += int(not is_new)
        except (ValueError, ValidationError, HTTPException) as exc:
            message = exc.detail if isinstance(exc, HTTPException) else "Data produk, harga, atau stok tidak valid."
            errors.append(f"Baris {line_number}: {message}")
        except Exception:
            errors.append(f"Baris {line_number}: Data produk tidak dapat disimpan.")
    db.commit()
    return {"status": "success", "rows_processed": processed, "products_created": created, "products_updated": updated, "variants_created": 0, "errors": errors}


@transactional
def update_product_affiliate_rule(db: Session, product_id: int, member_discount_type: str, member_discount_value: float, affiliate_commission_type: str, affiliate_commission_value: float) -> Product:
    product = get_product_by_id(db, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
    rule = ProductAffiliateRuleUpdate(product_id=product_id, member_discount_type=member_discount_type, member_discount_value=member_discount_value, affiliate_commission_type=affiliate_commission_type, affiliate_commission_value=affiliate_commission_value)
    for field, value in rule.model_dump(exclude={"product_id"}).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@transactional
def batch_update_affiliate_rules(db: Session, rules: list) -> int:
    updated = 0
    for rule in rules:
        product = db.get(Product, rule.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Produk tidak ditemukan.")
        for field, value in rule.model_dump(exclude={"product_id"}).items():
            setattr(product, field, value)
        updated += 1
    db.commit()
    return updated
