from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class OrganizationStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class CustomerStatus(str, Enum):
    LEAD = "lead"
    CUSTOMER = "customer"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class LeadStage(str, Enum):
    NEW = "NEW"
    ENGAGED = "ENGAGED"
    INTERESTED = "INTERESTED"
    PAYMENT_SENT = "PAYMENT_SENT"
    WON = "WON"
    LOST = "LOST"


class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    MANUAL = "manual"
    WEB = "web"


class ConversationStatus(str, Enum):
    OPEN = "open"
    PENDING = "pending"
    CLOSED = "closed"
    ARCHIVED = "archived"


class MessageStatus(str, Enum):
    RECEIVED = "received"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    DELETED = "deleted"


class ProductStatus(str, Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    OUT_OF_STOCK = "out_of_stock"
    ARCHIVED = "archived"


class FaqStatus(str, Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class PaginationOptions:
    page: int | None = None
    page_size: int | None = None
    offset: int | None = None
    limit: int | None = None

    def resolve(self, default_page_size: int = 50) -> tuple[int, int]:
        if self.offset is not None or self.limit is not None:
            offset = max(self.offset or 0, 0)
            limit = max(self.limit or default_page_size, 1)
            return offset, limit

        page = max(self.page or 1, 1)
        page_size = max(self.page_size or default_page_size, 1)
        offset = (page - 1) * page_size
        return offset, page_size


TRecord = TypeVar("TRecord")


@dataclass(frozen=True, slots=True)
class RepositoryPage(Generic[TRecord]):
    items: list[TRecord]
    total: int
    page: int
    page_size: int
    offset: int
    limit: int


class BasePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaseIdRecord(BasePayload):
    id: UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class BaseRecord(BaseIdRecord):
    organization_id: UUID


class TimestampRange(BasePayload):
    created_from: datetime | None = None
    created_to: datetime | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
