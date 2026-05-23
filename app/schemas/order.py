from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from enum import Enum


class OrderStatusEnum(str, Enum):
    open = 'open'
    sent = 'sent'
    in_preparation = 'in_preparation'
    ready = 'ready'
    closed = 'closed'
    cancelled = 'cancelled'


class OrderItemCreate(BaseModel):
    product_id: UUID
    seat_number: int = Field(default=1, ge=1)
    qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    unit_price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    tax_rate: Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=5, decimal_places=2)
    notes: Optional[str] = None
    station: str = Field(..., max_length=40)
    is_refill: bool = False

class OrderItemResponse(OrderItemCreate):
    id: UUID
    order_id: UUID
    refill_id: Optional[UUID] = None
    seat_number: int
    printed_at: Optional[datetime] = None
    created_at: datetime

    # Configuración de Pydantic v2 para leer directo desde modelos de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)


class OrderRefillCreate(BaseModel):
    created_by: UUID
    reason: Optional[str] = None
    items: List[OrderItemCreate]  # Una ronda de refill trae sus propios productos

class OrderRefillResponse(BaseModel):
    id: UUID
    order_id: UUID
    created_by: UUID
    reason: Optional[str] = None
    refill_no: int
    created_at: datetime
    items: List[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)

class OrderCreate(BaseModel):
    branch_id: UUID
    table_id: UUID
    opened_by: UUID
    customer_id: Optional[UUID] = None
    notes: Optional[str] = None
    # Al abrir una orden, se puede iniciar con una lista de ítems base
    items: List[OrderItemCreate] = []

class OrderResponse(BaseModel):
    id: UUID
    branch_id: UUID
    table_id: UUID
    customer_id: Optional[UUID] = None
    opened_by: UUID
    closed_by: Optional[UUID] = None
    status: OrderStatusEnum
    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total: Decimal
    notes: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    
    # Incluimos los detalles anidados al responder
    items: List[OrderItemResponse]
    refills: List[OrderRefillResponse]

    model_config = ConfigDict(from_attributes=True)

class OrderClose(BaseModel):
    closed_by: UUID