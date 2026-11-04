import pytest
from fastapi import HTTPException

from app.modules.catalog.schemas import ProductCreate
from app.modules.catalog.service import create_product
from app.modules.returns.models import ReturnOrder
from app.modules.returns.schemas import ReturnCreateRequest, ReturnItemRequest
from app.modules.returns.service import process_return_exchange
from app.modules.sales.schemas import CheckoutItem, CheckoutRequest
from app.modules.sales.service import process_checkout


@pytest.fixture
def sold_product(db_session):
    product = create_product(db_session, ProductCreate(name="Return validation", stock=5, base_price=100))
    order = process_checkout(db_session, CheckoutRequest(items=[
        CheckoutItem(product_id=product.id, quantity=2, unit_price=100),
    ], amount_paid=200), cashier_id=2)
    return product, order


def test_return_rejects_a_product_not_in_the_original_order(db_session, sold_product):
    _, order = sold_product
    unrelated = create_product(db_session, ProductCreate(name="Unrelated product", stock=5))
    with pytest.raises(HTTPException) as error:
        process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
            ReturnItemRequest(product_id=unrelated.id, quantity=1, refund_subtotal=100),
        ]), cashier_id=2)
    assert error.value.status_code == 400
    db_session.refresh(unrelated)
    assert unrelated.stock == 5


def test_return_quantity_cannot_exceed_quantity_purchased(db_session, sold_product):
    product, order = sold_product
    with pytest.raises(HTTPException) as error:
        process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
            ReturnItemRequest(product_id=product.id, quantity=3, refund_subtotal=300),
        ]), cashier_id=2)
    assert error.value.status_code == 400
    assert db_session.query(ReturnOrder).count() == 0


def test_same_purchase_cannot_be_refunded_repeatedly(db_session, sold_product):
    product, order = sold_product
    request = ReturnCreateRequest(order_id=order.id, items=[
        ReturnItemRequest(product_id=product.id, quantity=2, refund_subtotal=200),
    ])
    process_return_exchange(db_session, request, cashier_id=2)
    with pytest.raises(HTTPException) as error:
        process_return_exchange(db_session, request, cashier_id=2)
    assert error.value.status_code == 400
    db_session.refresh(product)
    assert product.stock == 5


def test_refund_cannot_exceed_the_amount_paid_for_the_items(db_session, sold_product):
    product, order = sold_product
    with pytest.raises(HTTPException) as error:
        process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
            ReturnItemRequest(product_id=product.id, quantity=1, refund_subtotal=9999),
        ]), cashier_id=2)
    assert error.value.status_code == 400


def test_return_cannot_bypass_limits_using_duplicate_lines(db_session, sold_product):
    product, order = sold_product
    with pytest.raises(HTTPException):
        process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
            ReturnItemRequest(product_id=product.id, quantity=2, refund_subtotal=200),
            ReturnItemRequest(product_id=product.id, quantity=2, refund_subtotal=200),
        ]), cashier_id=2)
    assert db_session.query(ReturnOrder).count() == 0


def test_refund_accounts_for_order_level_discount(db_session):
    product = create_product(db_session, ProductCreate(name="Discounted return", stock=2, base_price=100))
    order = process_checkout(db_session, CheckoutRequest(items=[
        CheckoutItem(product_id=product.id, quantity=1, unit_price=100),
    ], discount_amount=20, amount_paid=80), cashier_id=2)
    with pytest.raises(HTTPException):
        process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
            ReturnItemRequest(product_id=product.id, quantity=1, refund_subtotal=100),
        ]), cashier_id=2)
