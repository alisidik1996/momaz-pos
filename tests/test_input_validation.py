import pytest
from pydantic import ValidationError

from app.modules.auth.schemas import UserCreate
from app.modules.catalog.schemas import ProductCreate, VariantCreate
from app.modules.inventory.schemas import StockInItem
from app.modules.returns.schemas import ReturnItemRequest
from app.modules.sales.schemas import CheckoutItem, CheckoutRequest
from app.modules.shifts.schemas import ShiftOpenRequest


@pytest.mark.parametrize("quantity", [0, -1])
@pytest.mark.parametrize("schema,extra", [
    (CheckoutItem, {"unit_price": 10}),
    (StockInItem, {}),
    (ReturnItemRequest, {"refund_subtotal": 10}),
])
def test_item_quantities_must_be_positive(schema, extra, quantity):
    with pytest.raises(ValidationError):
        schema(product_id=1, quantity=quantity, **extra)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_checkout_money_must_be_finite_and_nonnegative(value):
    with pytest.raises(ValidationError):
        CheckoutItem(product_id=1, quantity=1, unit_price=value)


def test_line_discount_cannot_exceed_line_price():
    with pytest.raises(ValidationError):
        CheckoutItem(product_id=1, quantity=1, unit_price=10, discount_amount=11)


def test_cart_requires_at_least_one_item():
    with pytest.raises(ValidationError):
        CheckoutRequest(items=[], amount_paid=0)


def test_password_length_is_validated_in_bytes_before_bcrypt():
    with pytest.raises(ValidationError):
        UserCreate(username="cashier", full_name="Cashier", password="界" * 25)


def test_user_role_is_restricted_to_supported_roles():
    with pytest.raises(ValidationError):
        UserCreate(username="cashier", full_name="Cashier", password="review-password", role="superadmin")


def test_starting_cash_cannot_be_negative():
    with pytest.raises(ValidationError):
        ShiftOpenRequest(starting_cash=-10)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_catalog_rejects_invalid_prices(value):
    with pytest.raises(ValidationError):
        ProductCreate(name="Invalid price", base_price=value)


def test_variant_creation_requires_a_parent_product():
    with pytest.raises(ValidationError):
        VariantCreate(size="M", color="Blue")
