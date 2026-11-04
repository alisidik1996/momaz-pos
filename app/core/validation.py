"""Shared input constraints for identities, stock references, and money."""
from typing import Annotated, Literal, Optional
from datetime import datetime, timezone

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator, field_validator

Money = Annotated[float, Field(ge=0, allow_inf_nan=False)]
PositiveId = Annotated[int, Field(gt=0)]
PositiveQuantity = Annotated[int, Field(gt=0, le=2_147_483_647)]
StockQuantity = Annotated[int, Field(ge=0, le=2_147_483_647)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
UserRole = Literal["admin", "manager", "cashier"]


def validate_password(password: str) -> str:
    if not password or len(password.encode("utf-8")) > 72:
        raise ValueError("Kata sandi harus berisi 1–72 byte UTF-8.")
    return password


Password = Annotated[str, AfterValidator(validate_password)]


class UTCResponse(BaseModel):
    @field_validator("created_at", "updated_at", "start_time", "end_time", check_fields=False)
    @classmethod
    def serialize_utc_datetime(cls, value: Optional[datetime]):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ItemReference(BaseModel):
    product_id: Optional[PositiveId] = None
    variant_id: Optional[PositiveId] = None

    @model_validator(mode="after")
    def require_item_reference(self):
        if self.product_id is None and self.variant_id is None:
            raise ValueError("ID produk atau varian harus ditentukan.")
        return self
