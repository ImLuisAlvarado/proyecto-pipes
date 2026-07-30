# app/schemas/user.py
from pydantic import BaseModel, ConfigDict, field_serializer
from uuid import UUID
from datetime import datetime
from typing import Optional


def to_epoch(dt) -> int | None:
    """Convierte datetime a Unix timestamp (Long) — formato que espera Android."""
    if dt is None:
        return None
    return int(dt.timestamp())


class UserResponse(BaseModel):
    id: UUID
    branch_id: Optional[UUID] = None
    full_name: str
    username: str
    role: str
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer('id')
    def ser_id(self, v): return str(v)

    @field_serializer('branch_id')
    def ser_branch_id(self, v): return str(v) if v else None

    @field_serializer('created_at', 'updated_at')
    def ser_dt(self, v): return to_epoch(v)