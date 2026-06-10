from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository):
    table_name = "messages"
