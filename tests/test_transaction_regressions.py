from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.modules.auth.models import User
from app.modules.catalog.models import Product
from app.modules.catalog.schemas import ProductCreate, VariantCreate
from app.modules.catalog.service import create_product, create_variant
from app.modules.inventory.models import StockMovement
from app.modules.inventory.schemas import StockInItem, StockInRequest
from app.modules.inventory.service import process_stock_in, record_stock_movement
from app.modules.sales.models import SalesOrder
from app.modules.sales.schemas import CheckoutItem, CheckoutRequest
from app.modules.sales.service import generate_invoice_number, process_checkout
from app.modules.shifts.schemas import ShiftCloseRequest, ShiftOpenRequest
from app.modules.shifts.service import close_shift, open_shift


def test_stock_updates_do_not_overwrite_another_sessions_change(db_session):
    product = create_product(db_session, ProductCreate(name="Concurrent stock", stock=5))
    with Session(db_session.bind) as first, Session(db_session.bind) as second:
        first.get(Product, product.id)
        stale_product = second.get(Product, product.id)
        record_stock_movement(first, -2, "sale", product_id=product.id)
        first.commit()
        record_stock_movement(second, -2, "sale", product_id=stale_product.id)
        second.commit()
    db_session.refresh(product)
    assert product.stock == 1


def test_stale_stock_cannot_be_sold_twice(db_session):
    product = create_product(db_session, ProductCreate(name="Last stock", stock=5))
    with Session(db_session.bind) as first, Session(db_session.bind) as second:
        stale_product = second.get(Product, product.id)
        record_stock_movement(first, -4, "sale", product_id=product.id)
        first.commit()
        with pytest.raises(HTTPException) as error:
            record_stock_movement(second, -4, "sale", product_id=stale_product.id)
        assert error.value.status_code == 400
        second.rollback()
    db_session.refresh(product)
    assert product.stock == 1


def test_failed_multi_line_checkout_rolls_back_every_write(db_session):
    product = create_product(db_session, ProductCreate(name="Duplicate cart lines", stock=3, base_price=10))
    request = CheckoutRequest(items=[
        CheckoutItem(product_id=product.id, quantity=2, unit_price=10),
        CheckoutItem(product_id=product.id, quantity=2, unit_price=10),
    ], amount_paid=40)
    with pytest.raises(HTTPException):
        process_checkout(db_session, request, cashier_id=2)
    # A service failure must not leave partial writes for a later commit.
    db_session.commit()
    db_session.refresh(product)
    assert product.stock == 3
    assert db_session.query(SalesOrder).count() == 0
    assert db_session.query(StockMovement).count() == 0


def test_stock_in_with_unknown_item_is_not_partially_committed(db_session):
    product = create_product(db_session, ProductCreate(name="Batch restock", stock=1))
    request = StockInRequest(items=[
        StockInItem(product_id=product.id, quantity=2),
        StockInItem(product_id=999999, quantity=2),
    ])
    with pytest.raises(HTTPException) as error:
        process_stock_in(db_session, request, user_id=2)
    assert error.value.status_code == 404
    db_session.commit()
    db_session.refresh(product)
    assert product.stock == 1
    assert db_session.query(StockMovement).count() == 0


def test_variant_checkout_with_parent_id_deducts_variant_stock(db_session):
    product = create_product(db_session, ProductCreate(name="Variant parent", base_price=10))
    variant = create_variant(db_session, VariantCreate(product_id=product.id, size="M", color="Blue", stock=5, sell_price=10))
    order = process_checkout(db_session, CheckoutRequest(items=[
        CheckoutItem(product_id=product.id, variant_id=variant.id, quantity=1, unit_price=10),
    ], amount_paid=10), cashier_id=2)
    db_session.refresh(product)
    db_session.refresh(variant)
    assert product.stock == 0
    assert variant.stock == 4
    assert order.items[0].variant_id == variant.id


def test_cashier_cannot_close_another_cashiers_shift(db_session):
    shift = open_shift(db_session, 2, ShiftOpenRequest(starting_cash=0))
    with pytest.raises(HTTPException) as error:
        close_shift(db_session, shift.id, 1, ShiftCloseRequest(ending_cash_actual=0))
    assert error.value.status_code == 403
    db_session.refresh(shift)
    assert shift.status == "open"


def test_checkout_cannot_be_assigned_to_another_cashiers_shift(db_session):
    product = create_product(db_session, ProductCreate(name="Shift ownership", stock=1, base_price=10))
    shift = open_shift(db_session, 1, ShiftOpenRequest(starting_cash=0))
    with pytest.raises(HTTPException) as error:
        process_checkout(db_session, CheckoutRequest(shift_id=shift.id, items=[
            CheckoutItem(product_id=product.id, quantity=1, unit_price=10),
        ], amount_paid=10), cashier_id=2)
    assert error.value.status_code == 403


def test_invoice_number_does_not_reuse_a_gap(db_session):
    prefix = f"INV-{datetime.now(timezone.utc):%Y%m%d}-"
    db_session.add_all([SalesOrder(invoice_number=prefix + "0001"), SalesOrder(invoice_number=prefix + "0003")])
    db_session.commit()
    assert generate_invoice_number(db_session) == prefix + "0004"


def test_checkout_uses_currency_rounding_for_fractional_prices(db_session):
    product = create_product(db_session, ProductCreate(name="Fractional price", stock=3, base_price=0.1))
    order = process_checkout(db_session, CheckoutRequest(items=[
        CheckoutItem(product_id=product.id, quantity=3, unit_price=0.1),
    ], amount_paid=0.3), cashier_id=2)
    assert order.total_amount == 0.3
    assert order.change_amount == 0


def test_concurrent_checkout_sells_the_last_item_only_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            User(id=1, username="cashier1", password_hash="unused", full_name="Cashier 1"),
            User(id=2, username="cashier2", password_hash="unused", full_name="Cashier 2"),
            Product(id=1, name="Last item", stock=1, base_price=10),
        ])
        db.commit()
    barrier = Barrier(2)

    def checkout(cashier_id):
        with Session(engine, autoflush=False) as db:
            barrier.wait(timeout=10)
            try:
                process_checkout(db, CheckoutRequest(items=[
                    CheckoutItem(product_id=1, quantity=1, unit_price=10),
                ], amount_paid=10), cashier_id=cashier_id)
                return 200
            except HTTPException as error:
                return error.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(checkout, [1, 2]))
        assert sorted(results) == [200, 400]
        with Session(engine) as db:
            assert db.get(Product, 1).stock == 0
            assert db.query(SalesOrder).count() == 1
            assert db.query(StockMovement).count() == 1
    finally:
        engine.dispose()
