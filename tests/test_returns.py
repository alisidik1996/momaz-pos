import pytest
from app.modules.catalog import service as catalog_service
from app.modules.catalog.schemas import ProductCreate, MatrixGenerateRequest
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import CheckoutRequest, CheckoutItem
from app.modules.returns import service as returns_service
from app.modules.returns.schemas import ReturnCreateRequest, ReturnItemRequest

def test_clothing_return_and_size_exchange(db_session):
    # Setup clothing product with sizes M and L
    prod = catalog_service.create_product(db_session, ProductCreate(name="Kaos Henley Distro", base_price=90000))
    variants = catalog_service.generate_product_matrix(db_session, MatrixGenerateRequest(
        product_id=prod.id,
        colors=["Navy"],
        sizes=["M", "L"],
        cost_price=50000,
        sell_price=90000,
        initial_stock=5,
        sku_prefix="HNL"
    ))
    var_m = variants[0] # Size M
    var_l = variants[1] # Size L

    # 1. Customer buys Size M
    order = sales_service.process_checkout(db_session, CheckoutRequest(
        items=[CheckoutItem(variant_id=var_m.id, quantity=1, unit_price=90000)],
        amount_paid=100000
    ), cashier_id=2)

    db_session.refresh(var_m)
    assert var_m.stock == 4  # 5 - 1

    # 2. Customer comes back to exchange Size M for Size L (wrong size)
    return_req = ReturnCreateRequest(
        order_id=order.id,
        reason="wrong_size",
        items=[ReturnItemRequest(variant_id=var_m.id, quantity=1, refund_subtotal=90000)],
        exchange_variant_id=var_l.id,
        notes="Kekecilan, tukar ke ukuran L"
    )

    ret = returns_service.process_return_exchange(db_session, return_req, cashier_id=2)
    assert ret.id is not None
    assert ret.return_number.startswith("RET-")
    assert ret.exchange_variant_id == var_l.id

    # Verify stocks: Size M returned (+1 -> 5), Size L taken (-1 -> 4)
    db_session.refresh(var_m)
    db_session.refresh(var_l)
    assert var_m.stock == 5
    assert var_l.stock == 4

def test_direct_product_return_and_exchange(db_session):
    # Setup two products without variants
    prod_a = catalog_service.create_product(db_session, ProductCreate(
        name="Kemeja A",
        base_price=100000,
        stock=10
    ))
    prod_b = catalog_service.create_product(db_session, ProductCreate(
        name="Kemeja B",
        base_price=100000,
        stock=10
    ))

    # Buy Kemeja A
    order = sales_service.process_checkout(db_session, CheckoutRequest(
        items=[CheckoutItem(product_id=prod_a.id, quantity=1, unit_price=100000)],
        amount_paid=100000
    ), cashier_id=2)

    db_session.refresh(prod_a)
    assert prod_a.stock == 9

    # Return Kemeja A and exchange for Kemeja B
    return_req = ReturnCreateRequest(
        order_id=order.id,
        reason="defect",
        items=[ReturnItemRequest(product_id=prod_a.id, quantity=1, refund_subtotal=100000)],
        exchange_product_id=prod_b.id,
        notes="Tukar ke produk B"
    )
    ret = returns_service.process_return_exchange(db_session, return_req, cashier_id=2)
    assert ret.id is not None
    assert ret.exchange_product_id == prod_b.id

    db_session.refresh(prod_a)
    db_session.refresh(prod_b)
    assert prod_a.stock == 10
    assert prod_b.stock == 9
