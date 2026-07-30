# app/schemas/product.py
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class ProductBase(BaseModel):
    branch_id: UUID
    category_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    price: float
    tax_rate: float = 0
    print_station: str = "kitchen"
    active: bool = True

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    category_id: Optional[UUID] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    tax_rate: Optional[float] = None
    print_station: Optional[str] = None
    active: Optional[bool] = None

class ProductResponse(ProductBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)