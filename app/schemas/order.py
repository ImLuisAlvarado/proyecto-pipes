# app/schemas/order.py
"""
Schemas de Pydantic para órdenes.

Nota crítica de compatibilidad Android:
  OrderDTO.kt espera fechas como Unix timestamp (Long), NO como ISO string.
  Todos los field_serializer de datetime convierten a int(epoch).
"""
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from enum import Enum


# ── helpers ────────────────────────────────────────────────────────────────

def _epoch(dt) -> int | None:
    return int(dt.timestamp()) if dt else None

def _str(v) -> str | None:
    return str(v) if v else None


# ── enums ──────────────────────────────────────────────────────────────────

class OrderStatusEnum(str, Enum):
    open           = 'open'
    sent           = 'sent'
    in_preparation = 'in_preparation'
    ready          = 'ready'
    closed         = 'closed'
    cancelled      = 'cancelled'


# ── item ───────────────────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    product_id: UUID
    seat_label: Optional[str] = None
    qty:        Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    unit_price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    tax_rate:   Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=5, decimal_places=2)
    notes:      Optional[str] = None
    station:    str = Field(..., max_length=40)
    is_refill:  bool = False


class OrderItemResponse(BaseModel):
    id:         UUID
    order_id:   UUID
    refill_id:  Optional[UUID] = None
    product_id: UUID
    qty:        Decimal
    unit_price: Decimal
    tax_rate:   Decimal
    notes:      Optional[str] = None
    station:    str
    is_refill:  bool
    seat_label: Optional[str] = None
    printed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('id', 'order_id', 'product_id')
    def ser_uuid(self, v): return str(v)

    @field_serializer('refill_id')
    def ser_opt_uuid(self, v): return str(v) if v else None

    @field_serializer('qty', 'unit_price', 'tax_rate')
    def ser_decimal(self, v): return float(v)

    @field_serializer('printed_at', 'created_at')
    def ser_dt(self, v): return _epoch(v)


# ── refill ─────────────────────────────────────────────────────────────────

class OrderRefillCreate(BaseModel):
    created_by: UUID
    reason:     Optional[str] = None
    items:      List[OrderItemCreate]


class OrderRefillResponse(BaseModel):
    id:         UUID
    order_id:   UUID
    created_by: UUID
    reason:     Optional[str] = None
    refill_no:  int
    created_at: datetime
    items:      List[OrderItemResponse] = []

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('id', 'order_id', 'created_by')
    def ser_uuid(self, v): return str(v)

    @field_serializer('created_at')
    def ser_dt(self, v): return _epoch(v)


# ── order create ───────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    branch_id:   UUID
    table_id:    UUID
    opened_by:   UUID
    customer_id: Optional[UUID] = None
    notes:       Optional[str] = None
    items:       List[OrderItemCreate] = []


# ── order response  ────────────────────────────────────────────────────────
# Espejo de OrderDTO.kt — todas las fechas como epoch Long

class OrderResponse(BaseModel):
    id:             UUID
    branch_id:      UUID
    table_id:       UUID
    customer_id:    Optional[UUID] = None
    opened_by:      UUID
    closed_by:      Optional[UUID] = None
    status:         OrderStatusEnum
    subtotal:       Decimal
    tax_total:      Decimal
    discount_total: Decimal
    total:          Decimal
    notes:          Optional[str] = None
    opened_at:      datetime
    closed_at:      Optional[datetime] = None
    offline_uuid:   UUID
    sync_status:    str
    synced_at:      Optional[datetime] = None
    # updated_at no existe en el modelo Order, usamos opened_at como fallback
    items:          List[OrderItemResponse] = []
    refills:        List[OrderRefillResponse] = []

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('id', 'branch_id', 'table_id', 'opened_by', 'offline_uuid')
    def ser_uuid(self, v): return str(v)

    @field_serializer('customer_id', 'closed_by', 'synced_at')
    def ser_opt(self, v): return str(v) if v else None

    @field_serializer('subtotal', 'tax_total', 'discount_total', 'total')
    def ser_decimal(self, v): return float(v)

    @field_serializer('opened_at')
    def ser_opened(self, v): return _epoch(v)

    @field_serializer('closed_at')
    def ser_closed(self, v): return _epoch(v)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        # Android espera updated_at; usamos opened_at como proxy hasta tener el campo real
        data.setdefault('updated_at', data.get('opened_at'))
        return data


# ── misc ───────────────────────────────────────────────────────────────────

class OrderClose(BaseModel):
    closed_by: Optional[UUID] = None
    payment_method: Optional[str] = None


class OrderTransfer(BaseModel):
    new_table_id: UUID