from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from app.core.validation import Money, UTCResponse

class ShiftOpenRequest(BaseModel):
    starting_cash: Money
    note: Optional[str] = None

class ShiftCloseRequest(BaseModel):
    ending_cash_actual: Money
    note: Optional[str] = None

class ShiftOut(UTCResponse):
    id: int
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    starting_cash: float
    total_sales_cash: float
    total_sales_non_cash: float
    total_refunds: float
    ending_cash_expected: float
    ending_cash_actual: Optional[float] = None
    cash_difference: float
    status: str
    note: Optional[str] = None
    cashier_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
