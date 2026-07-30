# app/schemas/bill.py
from pydantic import BaseModel
from uuid import UUID
from typing import List, Optional


class BillItemResponse(BaseModel):
    product_id: UUID
    name: str
    qty: float
    unit_price: float
    total: float
    notes: Optional[str] = None
    seat_label: Optional[str] = None
    print_station: str


class BillResponse(BaseModel):
    order_id: UUID
    branch_id: UUID
    table_id: UUID
    order_number: Optional[str] = None
    items: List[BillItemResponse]
    subtotal: float
    tax: float
    total: float
    print_station: str
    status: str = "bill_printed"