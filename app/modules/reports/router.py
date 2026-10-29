from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from app.database import get_db
from app.modules.auth.service import get_current_user, require_admin
from app.modules.auth.models import User
from app.modules.reports import service

router = APIRouter(prefix="/api", tags=["Reports, Analytics & Settings"])

@router.get("/reports/dashboard")
def get_dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return service.get_dashboard_summary(db)

@router.get("/reports/sales")
def get_sales_report(
    start_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    cashier_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    report = service.get_sales_report(db, start_date=start_date, end_date=end_date, cashier_id=cashier_id)
    # Format orders to dict for json
    orders_json = []
    for o in report["orders"]:
        orders_json.append({
            "id": o.id,
            "invoice_number": o.invoice_number,
            "date": o.created_at.strftime("%Y-%m-%d %H:%M"),
            "cashier": o.cashier.full_name if o.cashier else "-",
            "subtotal": o.subtotal,
            "discount": o.discount_amount,
            "tax": o.tax_amount,
            "total": o.total_amount,
            "payment_method": o.payment_method.upper(),
            "items_count": sum(it.quantity for it in o.items)
        })
    return {
        "total_revenue": report["total_revenue"],
        "total_cogs": report["total_cogs"],
        "total_profit": report["total_profit"],
        "total_discount": report["total_discount"],
        "total_tax": report["total_tax"],
        "orders_count": report["orders_count"],
        "orders": orders_json
    }

@router.get("/reports/sales/csv")
def export_sales_csv(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    csv_data = service.generate_sales_csv(db, start_date=start_date, end_date=end_date)
    filename = f"laporan-penjualan-{start_date or 'all'}-sd-{end_date or 'today'}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    s = service.get_store_settings(db)
    return {
        "store_name": s.store_name,
        "tagline": s.tagline,
        "address": s.address,
        "phone": s.phone,
        "email": s.email,
        "receipt_footer": s.receipt_footer,
        "return_policy_days": s.return_policy_days,
        "tax_rate": s.tax_rate,
        "is_tax_enabled": s.is_tax_enabled,
        "currency_symbol": s.currency_symbol
    }

@router.put("/settings")
def update_settings(
    data: Dict[str, Any],
    db: Session = Depends(get_db),
    _: User = Depends(require_admin)
):
    s = service.update_store_settings(db, data)
    return {"message": "Pengaturan toko berhasil diperbarui."}
