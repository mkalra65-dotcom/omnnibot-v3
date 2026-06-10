from typing import Any

from supabase import Client


class BaseRepository:
    table_name: str

    def __init__(self, client: Client) -> None:
        self.client = client

    def table(self) -> Any:
        return self.client.table(self.table_name)
