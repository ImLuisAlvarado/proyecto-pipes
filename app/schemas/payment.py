# app/schemas/payment.py
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class PaymentCreate(BaseModel):
    method:          str            # 'cash' | 'card' | 'transfer' | 'mixed'
    amount:          float = Field(..., gt=0)
    tip_amount:      float = 0.0
    received_amount: Optional[float] = None   # efectivo entregado por el cliente
    change_amount:   Optional[float] = None   # cambio calculado
    seat_labels:     Optional[List[str]] = None  # asientos que cubre este pago
    notes:           Optional[str] = None
    received_by:     Optional[UUID] = None


class PaymentResponse(BaseModel):
    id:              UUID
    branch_id:       UUID
    order_id:        UUID
    method:          str
    amount:          float
    tip_amount:      float
    received_amount: Optional[float] = None
    change_amount:   Optional[float] = None
    seat_labels:     Optional[List[str]] = None
    received_by:     UUID
    paid_at:         datetime
    notes:           Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('id', 'branch_id', 'order_id', 'received_by')
    def ser_uuid(self, v): return str(v)

    @field_serializer('paid_at')
    def ser_dt(self, v): return int(v.timestamp()) if v else None