import pytest
from fastapi import HTTPException

from app.core.models import StoreSettings
from app.modules.catalog.schemas import ProductCreate
from app.modules.catalog.service import create_product
from app.modules.customers.models import AffiliateCommission
from app.modules.customers.schemas import CustomerCreate
from app.modules.customers.service import create_customer
from app.modules.returns.schemas import ReturnCreateRequest, ReturnItemRequest
from app.modules.returns.service import process_return_exchange
from app.modules.sales.schemas import CheckoutItem, CheckoutRequest
from app.modules.sales.service import process_checkout


def test_checkout_rejects_a_price_that_differs_from_catalog(db_session):
    product = create_product(db_session, ProductCreate(name="Price validation", base_price=100, stock=1))
    with pytest.raises(HTTPException) as error:
        process_checkout(db_session, CheckoutRequest(items=[
            CheckoutItem(product_id=product.id, quantity=1, unit_price=1),
        ], amount_paid=1), cashier_id=2)
    assert error.value.status_code == 409
    db_session.refresh(product)
    assert product.stock == 1


def test_checkout_cannot_bypass_configured_tax(db_session):
    settings = db_session.query(StoreSettings).one()
    settings.is_tax_enabled = True
    settings.tax_rate = 11
    db_session.commit()
    product = create_product(db_session, ProductCreate(name="Tax validation", base_price=100, stock=1))
    with pytest.raises(HTTPException) as error:
        process_checkout(db_session, CheckoutRequest(items=[
            CheckoutItem(product_id=product.id, quantity=1, unit_price=100),
        ], amount_paid=100, tax_rate=0), cashier_id=2)
    assert error.value.status_code == 409


def test_refund_reverses_customer_spend_and_affiliate_credit(db_session):
    customer = create_customer(db_session, CustomerCreate(name="Affiliate member"))
    product = create_product(db_session, ProductCreate(name="Commission product", base_price=100, stock=1, affiliate_commission_value=10))
    order = process_checkout(db_session, CheckoutRequest(customer_id=customer.id, items=[
        CheckoutItem(product_id=product.id, quantity=1, unit_price=100),
    ], amount_paid=100), cashier_id=2)
    db_session.refresh(customer)
    assert customer.total_commission == 10
    process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
        ReturnItemRequest(product_id=product.id, quantity=1, refund_subtotal=100),
    ]), cashier_id=2)
    db_session.refresh(customer)
    assert customer.total_spend == 0
    assert customer.total_commission == 0
    assert sum(row.amount for row in db_session.query(AffiliateCommission).all()) == 0


def test_refunding_an_uncommissioned_item_preserves_other_items_credit(db_session):
    customer = create_customer(db_session, CustomerCreate(name="Partial refund member"))
    commissioned = create_product(db_session, ProductCreate(name="Commissioned", base_price=100, stock=1, affiliate_commission_value=10))
    plain = create_product(db_session, ProductCreate(name="Not commissioned", base_price=100, stock=1))
    order = process_checkout(db_session, CheckoutRequest(customer_id=customer.id, items=[
        CheckoutItem(product_id=commissioned.id, quantity=1, unit_price=100),
        CheckoutItem(product_id=plain.id, quantity=1, unit_price=100),
    ], amount_paid=200), cashier_id=2)
    process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
        ReturnItemRequest(product_id=plain.id, quantity=1, refund_subtotal=100),
    ]), cashier_id=2)
    db_session.refresh(customer)
    assert customer.total_commission == 10
    assert customer.total_spend == 100


def test_final_partial_refund_can_return_the_rounding_remainder(db_session):
    product = create_product(db_session, ProductCreate(name="Refund rounding", base_price=0.333, stock=3))
    order = process_checkout(db_session, CheckoutRequest(items=[
        CheckoutItem(product_id=product.id, quantity=3, unit_price=0.333),
    ], amount_paid=1), cashier_id=2)
    for amount in (0.33, 0.33, 0.34):
        process_return_exchange(db_session, ReturnCreateRequest(order_id=order.id, items=[
            ReturnItemRequest(product_id=product.id, quantity=1, refund_subtotal=amount),
        ]), cashier_id=2)
    db_session.refresh(product)
    assert product.stock == 3
