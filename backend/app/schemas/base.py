from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampedModel(ApiModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None


JsonDict = dict[str, Any]
Uuid = UUID
