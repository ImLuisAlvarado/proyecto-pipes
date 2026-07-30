# app/schemas/category.py
"""
CategoryDTO.kt espera fechas como String (formato GMT), NO como epoch.
El mapper de Android usa parseDate() que acepta tanto String como Long,
pero por consistencia con el DTO usamos ISO string aquí.
"""
from pydantic import BaseModel, ConfigDict, field_serializer
from uuid import UUID
from datetime import datetime, timezone
from typing import Optional


def _iso(dt) -> str | None:
    if dt is None:
        return None
    # Formato compatible con SimpleDateFormat("EEE, dd MMM yyyy HH:mm:ss z")
    # Pydantic/Python isoformat es suficiente — parseDate() en Android tiene fallback
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


class CategoryBase(BaseModel):
    branch_id:  Optional[UUID] = None
    name:       str
    sort_order: int = 0
    active:     bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name:       Optional[str]  = None
    sort_order: Optional[int]  = None
    active:     Optional[bool] = None


class CategoryResponse(CategoryBase):
    id:         UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('id')
    def ser_id(self, v): return str(v)

    @field_serializer('branch_id')
    def ser_branch(self, v): return str(v) if v else None

    @field_serializer('created_at', 'updated_at')
    def ser_dt(self, v): return _iso(v)