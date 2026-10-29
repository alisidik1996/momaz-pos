import io
import csv
from datetime import datetime, date, time, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.modules.sales.models import SalesOrder, SalesOrderItem
from app.modules.catalog.models import ProductVariant, Product
from app.core.models import StoreSettings

def get_store_settings(db: Session) -> StoreSettings:
    settings = db.query(StoreSettings).first()
    if not settings:
        settings = StoreSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

def update_store_settings(db: Session, data: dict) -> StoreSettings:
    settings = get_store_settings(db)
    for k, v in data.items():
        if hasattr(settings, k) and v is not None:
            setattr(settings, k, v)
    db.commit()
    db.refresh(settings)
    return settings

def get_dashboard_summary(db: Session) -> Dict[str, Any]:
    today = date.today()
    start_of_today = datetime.combine(today, time.min)
    end_of_today = datetime.combine(today, time.max)
    
    # Orders today
    today_orders = db.query(SalesOrder).filter(
        SalesOrder.created_at >= start_of_today,
        SalesOrder.created_at <= end_of_today,
        SalesOrder.status == "completed"
    ).all()
    
    today_revenue = sum(o.total_amount for o in today_orders)
    today_orders_count = len(today_orders)
    
    # Calculate Today Gross Profit (Omset - HPP)
    today_order_ids = [o.id for o in today_orders]
    today_cogs = 0.0
    if today_order_ids:
        items = db.query(SalesOrderItem).filter(SalesOrderItem.order_id.in_(today_order_ids)).all()
        today_cogs = sum(item.cost_price * item.quantity for item in items)
    today_gross_profit = today_revenue - today_cogs
    
    # Low stock count (products directly, plus variants if any)
    low_prod_count = db.query(Product).filter(
        Product.is_active == True,
        Product.stock <= Product.min_stock
    ).count()
    low_var_count = db.query(ProductVariant).filter(
        ProductVariant.is_active == True,
        ProductVariant.stock <= ProductVariant.min_stock
    ).count()
    low_stock_count = low_prod_count + low_var_count
    
    # Sales breakdown by payment method
    payment_breakdown = {}
    for o in today_orders:
        method = o.payment_method.lower()
        payment_breakdown[method] = payment_breakdown.get(method, 0.0) + o.total_amount
        
    # Top 5 Best Selling Items of all time or this month
    top_items_query = db.query(
        SalesOrderItem.product_name,
        SalesOrderItem.variant_info,
        SalesOrderItem.sku,
        func.sum(SalesOrderItem.quantity).label("total_qty"),
        func.sum(SalesOrderItem.subtotal).label("total_revenue")
    ).group_by(
        SalesOrderItem.sku,
        SalesOrderItem.product_name,
        SalesOrderItem.variant_info
    ).order_by(func.sum(SalesOrderItem.quantity).desc()).limit(5).all()
    
    top_items = []
    for item in top_items_query:
        suffix = f" ({item.variant_info})" if item.variant_info else ""
        top_items.append({
            "name": f"{item.product_name}{suffix}",
            "sku": item.sku,
            "qty_sold": item.total_qty,
            "revenue": item.total_revenue
        })
        
    return {
        "today_revenue": today_revenue,
        "today_orders_count": today_orders_count,
        "today_gross_profit": today_gross_profit,
        "low_stock_count": low_stock_count,
        "payment_breakdown": payment_breakdown,
        "top_items": top_items
    }

def get_sales_report(
    db: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    cashier_id: Optional[int] = None
) -> Dict[str, Any]:
    stmt = db.query(SalesOrder).options(
        joinedload(SalesOrder.cashier),
        joinedload(SalesOrder.items)
    ).filter(SalesOrder.status == "completed")
    
    if start_date:
        d_start = datetime.strptime(start_date, "%Y-%m-%d")
        stmt = stmt.filter(SalesOrder.created_at >= d_start)
    if end_date:
        d_end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        stmt = stmt.filter(SalesOrder.created_at < d_end)
    if cashier_id:
        stmt = stmt.filter(SalesOrder.cashier_id == cashier_id)
        
    orders = stmt.order_by(SalesOrder.created_at.desc()).all()
    
    total_revenue = sum(o.total_amount for o in orders)
    total_discount = sum(o.discount_amount for o in orders)
    total_tax = sum(o.tax_amount for o in orders)
    
    total_cogs = 0.0
    for o in orders:
        for it in o.items:
            total_cogs += (it.cost_price * it.quantity)
            
    total_profit = total_revenue - total_cogs
    
    return {
        "total_revenue": total_revenue,
        "total_cogs": total_cogs,
        "total_profit": total_profit,
        "total_discount": total_discount,
        "total_tax": total_tax,
        "orders_count": len(orders),
        "orders": orders
    }

def generate_sales_csv(
    db: Session,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> str:
    report = get_sales_report(db, start_date=start_date, end_date=end_date)
    orders = report["orders"]
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow([
        "Invoice", "Tanggal", "Kasir", "Pelanggan",
        "Subtotal", "Diskon", "PPN", "Total Transaksi",
        "Metode Pembayaran", "Jumlah Item"
    ])
    
    for o in orders:
        c_name = o.cashier.full_name if o.cashier else "-"
        cust_name = o.customer.name if o.customer else "Umum"
        items_cnt = sum(it.quantity for it in o.items)
        writer.writerow([
            o.invoice_number,
            o.created_at.strftime("%Y-%m-%d %H:%M"),
            c_name,
            cust_name,
            f"{o.subtotal:.2f}",
            f"{o.discount_amount:.2f}",
            f"{o.tax_amount:.2f}",
            f"{o.total_amount:.2f}",
            o.payment_method.upper(),
            items_cnt
        ])
        
    return output.getvalue()
