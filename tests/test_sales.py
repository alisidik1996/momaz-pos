import pytest
from fastapi import HTTPException
from app.modules.catalog import service as catalog_service
from app.modules.catalog.schemas import ProductCreate, MatrixGenerateRequest
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import CheckoutRequest, CheckoutItem
from app.modules.shifts import service as shift_service
from app.modules.shifts.schemas import ShiftOpenRequest

def test_sales_checkout_and_stock_deduction(db_session):
    # Setup product and 1 variant with stock = 5
    prod = catalog_service.create_product(db_session, ProductCreate(name="Kaos Raglan", base_price=80000))
    variants = catalog_service.generate_product_matrix(db_session, MatrixGenerateRequest(
        product_id=prod.id,
        colors=["Putih-Hitam"],
        sizes=["L"],
        cost_price=40000,
        sell_price=80000,
        initial_stock=5,
        sku_prefix="RGL"
    ))
    var = variants[0]

    # Open shift
    shift = shift_service.open_shift(db_session, user_id=2, req=ShiftOpenRequest(starting_cash=100000))

    # Perform Checkout: buy 2 pcs
    checkout_req = CheckoutRequest(
        shift_id=shift.id,
        items=[CheckoutItem(variant_id=var.id, quantity=2, unit_price=80000, discount_amount=0)],
        discount_amount=10000,
        tax_rate=0,
        payment_method="cash",
        amount_paid=200000
    )
    order = sales_service.process_checkout(db_session, checkout_req, cashier_id=2)

    assert order.id is not None
    assert order.invoice_number.startswith("INV-")
    assert order.subtotal == 160000
    assert order.discount_amount == 10000
    assert order.total_amount == 150000
    assert order.change_amount == 50000
    assert order.status == "completed"

    # Verify stock reduced from 5 to 3
    db_session.refresh(var)
    assert var.stock == 3

    # Shift cash increased
    db_session.refresh(shift)
    assert shift.total_sales_cash == 150000

def test_sales_reject_insufficient_stock(db_session):
    prod = catalog_service.create_product(db_session, ProductCreate(name="Jaket Denim", base_price=250000))
    variants = catalog_service.generate_product_matrix(db_session, MatrixGenerateRequest(
        product_id=prod.id,
        colors=["Biowash"],
        sizes=["XL"],
        cost_price=150000,
        sell_price=250000,
        initial_stock=2,
        sku_prefix="JKT"
    ))
    var = variants[0]

    # Attempt to buy 5 pcs (more than 2 available)
    checkout_req = CheckoutRequest(
        items=[CheckoutItem(variant_id=var.id, quantity=5, unit_price=250000)],
        amount_paid=1500000
    )

    with pytest.raises(HTTPException) as excinfo:
        sales_service.process_checkout(db_session, checkout_req, cashier_id=2)
    assert "tidak mencukupi" in excinfo.value.detail

def test_direct_product_checkout_and_stock(db_session):
    # Test checkout for standalone product without variants
    prod = catalog_service.create_product(db_session, ProductCreate(
        name="Kaos Polos Standalone",
        sku="KOS-STD-01",
        barcode="8997788990011",
        base_price=95000,
        discount_price=85000,
        cost_price=45000,
        stock=15,
        min_stock=5
    ))

    # Checkout 3 pcs using product_id
    checkout_req = CheckoutRequest(
        items=[CheckoutItem(product_id=prod.id, quantity=3, unit_price=85000)],
        payment_method="cash",
        amount_paid=300000
    )
    order = sales_service.process_checkout(db_session, checkout_req, cashier_id=2)

    assert order.id is not None
    assert order.total_amount == 255000
    assert order.change_amount == 45000

    # Verify direct stock reduction
    db_session.refresh(prod)
    assert prod.stock == 12
