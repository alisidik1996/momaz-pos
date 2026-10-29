import pytest
from fastapi import HTTPException
from app.modules.shifts import service
from app.modules.shifts.schemas import ShiftOpenRequest, ShiftCloseRequest

def test_cashier_shift_lifecycle(db_session):
    # 1. Open Shift
    open_req = ShiftOpenRequest(starting_cash=200000, note="Shift Pagi")
    shift = service.open_shift(db_session, user_id=2, req=open_req)
    assert shift.id is not None
    assert shift.status == "open"
    assert shift.starting_cash == 200000
    assert shift.ending_cash_expected == 200000

    # 2. Cannot open another shift while one is already open
    with pytest.raises(HTTPException):
        service.open_shift(db_session, user_id=2, req=open_req)

    # 3. Simulate sales cash addition
    shift.total_sales_cash = 350000
    db_session.commit()

    # 4. Close Shift with exact cash count (Expected: 200k + 350k = 550k, Actual counted: 550k)
    close_req = ShiftCloseRequest(ending_cash_actual=550000, note="Kas pas")
    closed_shift = service.close_shift(db_session, shift_id=shift.id, user_id=2, req=close_req)

    assert closed_shift.status == "closed"
    assert closed_shift.ending_cash_expected == 550000
    assert closed_shift.ending_cash_actual == 550000
    assert closed_shift.cash_difference == 0
