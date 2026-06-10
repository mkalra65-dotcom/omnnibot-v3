from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    table_name = "users"
