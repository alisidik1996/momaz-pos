import random
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.modules.sales.models import SalesOrder, SalesOrderItem
from app.modules.catalog.models import Product, ProductVariant
from app.modules.shifts.models import CashierShift
from app.modules.shifts.service import get_active_shift
from app.modules.customers.models import Customer
from app.modules.inventory.service import record_stock_movement
from app.core.models import StoreSettings
from app.modules.sales.schemas import (
    CheckoutRequest, SalesOrderOut, SalesOrderItemOut, ReceiptOut
)

def generate_invoice_number(db: Session) -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    count_today = db.query(SalesOrder).filter(
        SalesOrder.invoice_number.like(f"INV-{today_str}-%")
    ).count()
    seq = str(count_today + 1).zfill(4)
    return f"INV-{today_str}-{seq}"

def process_checkout(db: Session, req: CheckoutRequest, cashier_id: int) -> SalesOrder:
    if not req.items:
        raise HTTPException(status_code=400, detail="Keranjang belanja kosong.")
        
    # Check or assign active cashier shift
    shift = None
    if req.shift_id:
        shift = db.query(CashierShift).filter(CashierShift.id == req.shift_id, CashierShift.status == "open").first()
    if not shift:
        shift = get_active_shift(db, cashier_id)
        
    invoice_no = generate_invoice_number(db)
    
    # Calculate items subtotal and check stock
    order_items = []
    items_subtotal = 0.0
    
    for item_in in req.items:
        line_subtotal = (item_in.unit_price * item_in.quantity) - item_in.discount_amount
        items_subtotal += line_subtotal
        
        if item_in.product_id:
            prod = db.query(Product).filter(Product.id == item_in.product_id).first()
            if not prod:
                raise HTTPException(status_code=404, detail=f"Produk #{item_in.product_id} tidak ditemukan.")
            if (prod.stock or 0) < item_in.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stok untuk '{prod.name}' tidak mencukupi. Sisa stok: {prod.stock or 0} pcs."
                )
            order_item = SalesOrderItem(
                product_id=prod.id,
                variant_id=None,
                product_name=prod.name,
                variant_info="",
                sku=prod.sku or "-",
                barcode=prod.barcode or "-",
                cost_price=prod.cost_price or 0.0,
                unit_price=item_in.unit_price,
                quantity=item_in.quantity,
                discount_amount=item_in.discount_amount,
                subtotal=line_subtotal
            )
            order_items.append((order_item, prod, None))
        elif item_in.variant_id:
            var = db.query(ProductVariant).options(
                joinedload(ProductVariant.product)
            ).filter(ProductVariant.id == item_in.variant_id).first()
            if not var:
                raise HTTPException(status_code=404, detail=f"Varian #{item_in.variant_id} tidak ditemukan.")
            if var.stock < item_in.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Stok untuk '{var.product.name} ({var.color} - {var.size})' tidak mencukupi. Sisa stok: {var.stock} pcs."
                )
            order_item = SalesOrderItem(
                product_id=var.product_id,
                variant_id=var.id,
                product_name=var.product.name,
                variant_info=f"{var.color} - {var.size}",
                sku=var.sku,
                barcode=var.barcode,
                cost_price=var.cost_price,
                unit_price=item_in.unit_price,
                quantity=item_in.quantity,
                discount_amount=item_in.discount_amount,
                subtotal=line_subtotal
            )
            order_items.append((order_item, var.product, var))
        else:
            raise HTTPException(status_code=400, detail="Item belanja harus menyertakan product_id.")
        
    # Tax and Total
    subtotal_after_discount = max(0.0, items_subtotal - req.discount_amount)
    tax_amount = 0.0
    if req.tax_rate > 0:
        tax_amount = round(subtotal_after_discount * (req.tax_rate / 100.0), 2)
        
    total_amount = subtotal_after_discount + tax_amount
    
    if req.amount_paid < total_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Jumlah pembayaran (Rp {req.amount_paid:,.0f}) kurang dari total tagihan (Rp {total_amount:,.0f})."
        )
        
    change_amount = req.amount_paid - total_amount
    
    order = SalesOrder(
        invoice_number=invoice_no,
        shift_id=shift.id if shift else None,
        cashier_id=cashier_id,
        customer_id=req.customer_id,
        subtotal=items_subtotal,
        discount_amount=req.discount_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        payment_method=req.payment_method,
        amount_paid=req.amount_paid,
        change_amount=change_amount,
        notes=req.notes,
        status="completed"
    )
    db.add(order)
    db.flush() # get order.id
    
    # Save order items & decrement stock
    for oi, prod, var in order_items:
        oi.order_id = order.id
        db.add(oi)
        if prod and not var:
            record_stock_movement(
                db=db,
                product_id=prod.id,
                change_qty=-oi.quantity,
                movement_type="sale",
                reference=order.invoice_number,
                note=f"Penjualan POS ({order.invoice_number})",
                user_id=cashier_id
            )
        elif var:
            record_stock_movement(
                db=db,
                variant_id=var.id,
                change_qty=-oi.quantity,
                movement_type="sale",
                reference=order.invoice_number,
                note=f"Penjualan POS ({order.invoice_number})",
                user_id=cashier_id
            )
        
    # Update Cashier Shift sales
    if shift:
        if req.payment_method == "cash":
            shift.total_sales_cash += total_amount
        else:
            shift.total_sales_non_cash += total_amount
            
    # Update Customer spend, visits & calculate affiliate commission
    if req.customer_id:
        cust = db.query(Customer).filter(Customer.id == req.customer_id).first()
        if cust:
            cust.total_spend += total_amount
            cust.visit_count += 1

            total_comm = 0.0
            for oi, prod, var in order_items:
                target_prod = prod if prod else (var.product if var else None)
                if target_prod and (target_prod.affiliate_commission_value or 0) > 0:
                    comm_type = target_prod.affiliate_commission_type or "percent"
                    comm_val = target_prod.affiliate_commission_value
                    if comm_type == "percent":
                        comm = round((oi.subtotal * (comm_val / 100.0)), 2)
                    else:
                        comm = round(comm_val * oi.quantity, 2)
                    total_comm += comm

            if total_comm > 0:
                cust.total_commission = (cust.total_commission or 0.0) + total_comm
                from app.modules.customers.models import AffiliateCommission
                comm_record = AffiliateCommission(
                    customer_id=cust.id,
                    order_id=order.id,
                    amount=total_comm,
                    notes=f"Komisi Affiliate Invoice {order.invoice_number}"
                )
                db.add(comm_record)
            
    db.commit()
    db.refresh(order)
    return order

def get_order_by_id(db: Session, order_id: int) -> Optional[SalesOrder]:
    return db.query(SalesOrder).options(
        joinedload(SalesOrder.cashier),
        joinedload(SalesOrder.customer),
        joinedload(SalesOrder.items)
    ).filter(SalesOrder.id == order_id).first()

def get_order_by_invoice(db: Session, invoice_number: str) -> Optional[SalesOrder]:
    return db.query(SalesOrder).options(
        joinedload(SalesOrder.cashier),
        joinedload(SalesOrder.customer),
        joinedload(SalesOrder.items)
    ).filter(SalesOrder.invoice_number == invoice_number).first()

def get_recent_orders(db: Session, limit: int = 50) -> List[SalesOrderOut]:
    orders = db.query(SalesOrder).options(
        joinedload(SalesOrder.cashier),
        joinedload(SalesOrder.customer),
        joinedload(SalesOrder.items)
    ).order_by(SalesOrder.id.desc()).limit(limit).all()
    
    output = []
    for o in orders:
        out = SalesOrderOut.model_validate(o)
        out.cashier_name = o.cashier.full_name if o.cashier else "Kasir"
        out.customer_name = o.customer.name if o.customer else "Umum"
        output.append(out)
    return output

def build_receipt_data(db: Session, order: SalesOrder) -> ReceiptOut:
    settings = db.query(StoreSettings).first()
    if not settings:
        settings = StoreSettings()
        
    items_out = [SalesOrderItemOut.model_validate(item) for item in order.items]
    
    return ReceiptOut(
        invoice_number=order.invoice_number,
        store_name=settings.store_name,
        store_tagline=settings.tagline,
        store_address=settings.address,
        store_phone=settings.phone,
        date_str=order.created_at.strftime("%d/%m/%Y %H:%M"),
        cashier_name=order.cashier.full_name if order.cashier else "Kasir",
        customer_name=order.customer.name if order.customer else None,
        customer_member_id=order.customer.member_id if order.customer else None,
        items=items_out,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        tax_amount=order.tax_amount,
        total_amount=order.total_amount,
        payment_method=order.payment_method.upper(),
        amount_paid=order.amount_paid,
        change_amount=order.change_amount,
        receipt_footer=settings.receipt_footer
    )
