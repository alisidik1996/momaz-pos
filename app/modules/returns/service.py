from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.modules.returns.models import ReturnOrder, ReturnOrderItem
from app.modules.sales.models import SalesOrder, SalesOrderItem
from app.modules.catalog.models import Product, ProductVariant
from app.modules.inventory.service import record_stock_movement
from app.modules.shifts.service import get_active_shift
from app.core.models import StoreSettings
from app.modules.returns.schemas import ReturnCreateRequest, ReturnOrderOut, ReturnItemOut

def generate_return_number(db: Session) -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    count_today = db.query(ReturnOrder).filter(
        ReturnOrder.return_number.like(f"RET-{today_str}-%")
    ).count()
    seq = str(count_today + 1).zfill(4)
    return f"RET-{today_str}-{seq}"

def process_return_exchange(
    db: Session,
    req: ReturnCreateRequest,
    cashier_id: int
) -> ReturnOrder:
    order = db.query(SalesOrder).filter(SalesOrder.id == req.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Nomor order / invoice tidak ditemukan.")
        
    settings = db.query(StoreSettings).first()
    policy_days = settings.return_policy_days if settings else 3
    
    # Check return window
    order_age = datetime.now(timezone.utc) - order.created_at.replace(tzinfo=timezone.utc)
    if order_age > timedelta(days=policy_days):
        raise HTTPException(
            status_code=400,
            detail=f"Batas waktu penukaran barang telah habis (kebijakan toko: {policy_days} hari)."
        )
        
    ret_number = generate_return_number(db)
    
    total_refund = 0.0
    for it in req.items:
        total_refund += it.refund_subtotal
        
    additional_charge = 0.0
    # Check if exchange product / variant is requested
    exchange_prod = None
    exchange_var = None

    if req.exchange_product_id:
        exchange_prod = db.query(Product).filter(Product.id == req.exchange_product_id).first()
        if not exchange_prod:
            raise HTTPException(status_code=404, detail="Produk tukar tidak ditemukan.")
        if (exchange_prod.stock or 0) <= 0:
            raise HTTPException(status_code=400, detail=f"Stok untuk produk tukar ({exchange_prod.name}) habis.")
        exchange_price = exchange_prod.discount_price if (exchange_prod.discount_price and exchange_prod.discount_price > 0) else exchange_prod.base_price
        if exchange_price > total_refund:
            additional_charge = exchange_price - total_refund
            total_refund = 0.0
        else:
            total_refund = total_refund - exchange_price
            additional_charge = 0.0
    elif req.exchange_variant_id:
        exchange_var = db.query(ProductVariant).filter(ProductVariant.id == req.exchange_variant_id).first()
        if not exchange_var:
            raise HTTPException(status_code=404, detail="Varian tukar tidak ditemukan.")
        if exchange_var.stock <= 0:
            raise HTTPException(status_code=400, detail=f"Stok untuk varian tukar ({exchange_var.sku}) habis.")
            
        # Compare prices
        exchange_price = exchange_var.sell_price
        if exchange_price > total_refund:
            additional_charge = exchange_price - total_refund
            total_refund = 0.0
        else:
            total_refund = total_refund - exchange_price
            additional_charge = 0.0
            
    return_order = ReturnOrder(
        return_number=ret_number,
        order_id=order.id,
        cashier_id=cashier_id,
        reason=req.reason,
        total_refund_amount=total_refund,
        additional_charge=additional_charge,
        exchange_product_id=req.exchange_product_id,
        exchange_variant_id=req.exchange_variant_id,
        notes=req.notes
    )
    db.add(return_order)
    db.flush()
    
    # Restock returned items
    for item_req in req.items:
        roi = ReturnOrderItem(
            return_id=return_order.id,
            product_id=item_req.product_id,
            variant_id=item_req.variant_id,
            quantity=item_req.quantity,
            refund_subtotal=item_req.refund_subtotal
        )
        db.add(roi)
        
        if item_req.product_id:
            record_stock_movement(
                db=db,
                product_id=item_req.product_id,
                change_qty=item_req.quantity,
                movement_type="return",
                reference=ret_number,
                note=f"Retur dari invoice {order.invoice_number}",
                user_id=cashier_id
            )
        elif item_req.variant_id:
            record_stock_movement(
                db=db,
                variant_id=item_req.variant_id,
                change_qty=item_req.quantity,
                movement_type="return",
                reference=ret_number,
                note=f"Retur dari invoice {order.invoice_number}",
                user_id=cashier_id
            )
        
    # If exchange item given, deduct exchange stock
    if exchange_prod:
        record_stock_movement(
            db=db,
            product_id=exchange_prod.id,
            change_qty=-1,
            movement_type="exchange",
            reference=ret_number,
            note=f"Tukar produk dari invoice {order.invoice_number}",
            user_id=cashier_id
        )
    elif exchange_var:
        record_stock_movement(
            db=db,
            variant_id=exchange_var.id,
            change_qty=-1,
            movement_type="exchange",
            reference=ret_number,
            note=f"Tukar varian dari invoice {order.invoice_number}",
            user_id=cashier_id
        )
        
    # Update active shift if cash refund occurred
    shift = get_active_shift(db, cashier_id)
    if shift and total_refund > 0:
        shift.total_refunds += total_refund
        
    db.commit()
    db.refresh(return_order)
    return return_order

def get_return_orders(db: Session, limit: int = 50) -> List[ReturnOrderOut]:
    returns = db.query(ReturnOrder).options(
        joinedload(ReturnOrder.order),
        joinedload(ReturnOrder.cashier),
        joinedload(ReturnOrder.exchange_product),
        joinedload(ReturnOrder.exchange_variant).joinedload(ProductVariant.product),
        joinedload(ReturnOrder.items).joinedload(ReturnOrderItem.product),
        joinedload(ReturnOrder.items).joinedload(ReturnOrderItem.variant).joinedload(ProductVariant.product)
    ).order_by(ReturnOrder.id.desc()).limit(limit).all()
    
    output = []
    for r in returns:
        items_out = []
        for i in r.items:
            prod_name = None
            var_info = None
            sku_val = "-"
            if i.product:
                prod_name = i.product.name
                sku_val = i.product.sku or "-"
            elif i.variant:
                prod_name = i.variant.product.name if i.variant.product else "-"
                var_info = f"{i.variant.color} - {i.variant.size}"
                sku_val = i.variant.sku or "-"

            items_out.append(ReturnItemOut(
                id=i.id,
                product_id=i.product_id,
                variant_id=i.variant_id,
                quantity=i.quantity,
                refund_subtotal=i.refund_subtotal,
                product_name=prod_name,
                variant_info=var_info,
                sku=sku_val
            ))
            
        ex_prod_name = None
        ex_info = None
        if r.exchange_product:
            ex_prod_name = r.exchange_product.name
        elif r.exchange_variant and r.exchange_variant.product:
            ex_prod_name = r.exchange_variant.product.name
            ex_info = f"{r.exchange_variant.product.name} ({r.exchange_variant.color} - {r.exchange_variant.size})"
            
        output.append(ReturnOrderOut(
            id=r.id,
            return_number=r.return_number,
            order_id=r.order_id,
            invoice_number=r.order.invoice_number if r.order else None,
            cashier_id=r.cashier_id,
            cashier_name=r.cashier.full_name if r.cashier else "Kasir",
            reason=r.reason,
            total_refund_amount=r.total_refund_amount,
            additional_charge=r.additional_charge,
            exchange_product_id=r.exchange_product_id,
            exchange_variant_id=r.exchange_variant_id,
            exchange_product_name=ex_prod_name,
            exchange_variant_info=ex_info or ex_prod_name,
            notes=r.notes,
            created_at=r.created_at,
            items=items_out
        ))
    return output
