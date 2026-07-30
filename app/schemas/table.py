# app/schemas/table.py
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional

class TableBase(BaseModel):
    branch_id: UUID
    code: str
    name: str
    seats: int = 4
    status: str = "available"
    active: bool = True

class TableCreate(TableBase):
    pass

class TableUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    seats: Optional[int] = None
    status: Optional[str] = None
    active: Optional[bool] = None

class TableResponse(TableBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)