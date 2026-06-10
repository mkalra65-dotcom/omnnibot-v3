from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.base import JsonDict, TimestampedModel


class ProductBase(TimestampedModel):
    organization_id: UUID
    name: str
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    color: str | None = None
    size: str | None = None
    price: Decimal | None = None
    currency: str = "INR"
    inventory_quantity: int | None = None
    image_url: str | None = None
    status: str = "active"
    metadata: JsonDict = Field(default_factory=dict)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(TimestampedModel):
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    color: str | None = None
    size: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    inventory_quantity: int | None = None
    image_url: str | None = None
    status: str | None = None
    metadata: JsonDict | None = None


class ProductRead(ProductBase):
    id: UUID
