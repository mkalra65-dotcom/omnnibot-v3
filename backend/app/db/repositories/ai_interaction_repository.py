from __future__ import annotations

from app.db.models.queries import AiInteractionFilters
from app.db.models.records import AiInteractionCreate, AiInteractionRead
from app.db.repositories.base_repository import BaseRepository


class AiInteractionRepository(
    BaseRepository[AiInteractionRead, AiInteractionCreate, dict, AiInteractionFilters]
):
    table_name = "ai_interactions"
    read_model = AiInteractionRead
    sortable_fields = {"created_at"}
