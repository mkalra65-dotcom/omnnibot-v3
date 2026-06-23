from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    conversations,
    customers,
    faq_entries,
    health,
    memberships,
    messages,
    organizations,
    products,
    whatsapp_outbound,
    whatsapp_webhooks,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(memberships.router, prefix="/memberships", tags=["memberships"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(faq_entries.router, prefix="/faq-entries", tags=["faq_entries"])
api_router.include_router(whatsapp_outbound.router, prefix="/whatsapp/outbound", tags=["whatsapp_outbound"])
api_router.include_router(
    whatsapp_webhooks.router,
    prefix="/webhooks/whatsapp",
    tags=["whatsapp_webhooks"],
)
