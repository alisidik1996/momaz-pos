from typing import List, Optional
from sqlalchemy import func, update
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.core.transactions import transactional
from app.modules.inventory.models import StockMovement
from app.modules.catalog.models import ProductVariant, Product
from app.modules.inventory.schemas import (
    StockAdjustmentRequest, StockInRequest, LowStockItemOut, StockMovementOut
)

def get_stock_item(db: Session, product_id: Optional[int] = None, variant_id: Optional[int] = None):
    if variant_id is not None:
        item = db.query(ProductVariant).filter(ProductVariant.id == variant_id).populate_existing().first()
        if item is None:
            raise HTTPException(status_code=404, detail=f"Varian {variant_id} tidak ditemukan.")
        if product_id is not None and item.product_id != product_id:
            raise HTTPException(status_code=400, detail="Varian bukan milik produk yang dipilih.")
        return item
    if product_id is not None:
        item = db.query(Product).filter(Product.id == product_id).populate_existing().first()
        if item is None:
            raise HTTPException(status_code=404, detail=f"Produk {product_id} tidak ditemukan.")
        return item
    raise HTTPException(status_code=400, detail="ID produk atau varian harus ditentukan.")


@transactional
def record_stock_movement(
    db: Session,
    change_qty: int,
    movement_type: str,
    product_id: Optional[int] = None,
    variant_id: Optional[int] = None,
    reference: Optional[str] = None,
    note: Optional[str] = None,
    user_id: Optional[int] = None,
    expected_stock: Optional[int] = None,
) -> StockMovement:
    db.flush()
    item = get_stock_item(db, product_id, variant_id)
    model = ProductVariant if variant_id is not None else Product
    stock = func.coalesce(model.stock, 0)
    statement = update(model).where(model.id == item.id, stock + change_qty >= 0, stock + change_qty <= 2_147_483_647)
    if expected_stock is not None:
        statement = statement.where(stock == expected_stock)
    current_stock = db.execute(
        statement.values(stock=stock + change_qty).returning(model.stock),
        execution_options={"synchronize_session": "fetch"},
    ).scalar_one_or_none()
    if current_stock is None:
        if expected_stock is not None:
            raise HTTPException(status_code=409, detail="Stok telah berubah. Muat ulang sebelum melakukan penyesuaian.")
        identifier = getattr(item, "name", None) or item.sku
        raise HTTPException(status_code=400, detail=f"Stok untuk '{identifier}' tidak mencukupi atau melebihi batas (sisa: {item.stock or 0}).")
    if variant_id is not None:
        product_id = item.product_id
        
    movement = StockMovement(
        product_id=product_id,
        variant_id=variant_id,
        user_id=user_id,
        change_qty=change_qty,
        current_stock=current_stock,
        movement_type=movement_type,
        reference=reference,
        note=note
    )
    db.add(movement)
    return movement

@transactional
def adjust_stock(db: Session, req: StockAdjustmentRequest, user_id: int) -> StockMovement:
    note_text = f"Penyesuaian stok ({req.reason})"
    if req.note:
        note_text += f": {req.note}"

    item = get_stock_item(db, req.product_id, req.variant_id)
    previous_stock = item.stock or 0
    diff = req.actual_stock - previous_stock
    if diff == 0:
        raise HTTPException(status_code=400, detail="Stok fisik sama dengan stok sistem.")
    movement = record_stock_movement(
        db=db,
        product_id=req.product_id,
        variant_id=req.variant_id,
        change_qty=diff,
        movement_type="adjustment",
        reference=f"ADJ-{req.reason.upper()}",
        note=note_text,
        user_id=user_id,
        expected_stock=previous_stock,
    )

    db.commit()
    db.refresh(movement)
    return movement

@transactional
def process_stock_in(db: Session, req: StockInRequest, user_id: int) -> List[StockMovement]:
    movements = []
    ref = req.invoice_ref or f"PO-{req.supplier_name or 'RESTOCK'}"
    
    for item in req.items:
        note_detail = f"Penerimaan dari {req.supplier_name or 'Supplier'}"
        if req.note:
            note_detail += f" ({req.note})"

        target = get_stock_item(db, item.product_id, item.variant_id)
        if item.cost_price is not None:
            target.cost_price = item.cost_price
        movements.append(record_stock_movement(
            db=db,
            product_id=item.product_id,
            variant_id=item.variant_id,
            change_qty=item.quantity,
            movement_type="restock",
            reference=ref,
            note=note_detail,
            user_id=user_id,
        ))
        
    db.commit()
    return movements

def get_low_stock_variants(db: Session) -> List[LowStockItemOut]:
    result = []
    # 1. Check products directly
    low_products = db.query(Product).options(joinedload(Product.category)).filter(
        Product.is_active.is_(True),
        Product.stock <= Product.min_stock,
        ~Product.variants.any(),
    ).all()
    for p in low_products:
        result.append(LowStockItemOut(
            product_id=p.id,
            variant_id=None,
            product_name=p.name,
            category_name=p.category.name if p.category else None,
            sku=p.sku or "-",
            barcode=p.barcode or "-",
            size="",
            color="",
            stock=p.stock or 0,
            min_stock=p.min_stock
        ))

    # 2. Check variants if any
    variants = db.query(ProductVariant).join(Product).filter(
        ProductVariant.is_active.is_(True),
        ProductVariant.stock <= ProductVariant.min_stock
    ).all()
    for v in variants:
        result.append(LowStockItemOut(
            product_id=v.product_id,
            variant_id=v.id,
            product_name=v.product.name,
            category_name=v.product.category.name if v.product.category else None,
            sku=v.sku,
            barcode=v.barcode,
            size=v.size,
            color=v.color,
            stock=v.stock,
            min_stock=v.min_stock
        ))
    return result

def get_stock_movements(
    db: Session, 
    variant_id: Optional[int] = None, 
    limit: int = 100
) -> List[StockMovementOut]:
    stmt = db.query(StockMovement).options(
        joinedload(StockMovement.product),
        joinedload(StockMovement.variant).joinedload(ProductVariant.product),
        joinedload(StockMovement.user)
    )
    if variant_id:
        stmt = stmt.filter(StockMovement.variant_id == variant_id)
        
    movements = stmt.order_by(StockMovement.id.desc()).limit(limit).all()
    
    output = []
    for m in movements:
        prod_name = "-"
        sku_val = "-"
        var_info = ""

        if m.variant and m.variant.product:
            prod_name = m.variant.product.name
            sku_val = m.variant.sku
            var_info = f"{m.variant.color} - {m.variant.size}"
        elif m.product:
            prod_name = m.product.name
            sku_val = m.product.sku or "-"

        uname = m.user.full_name if m.user else "Sistem"
        
        output.append(StockMovementOut(
            id=m.id,
            product_id=m.product_id,
            variant_id=m.variant_id,
            user_id=m.user_id,
            change_qty=m.change_qty,
            current_stock=m.current_stock,
            movement_type=m.movement_type,
            reference=m.reference,
            note=m.note,
            created_at=m.created_at,
            product_name=prod_name,
            variant_info=var_info or None,
            sku=sku_val,
            user_name=uname
        ))
    return output
