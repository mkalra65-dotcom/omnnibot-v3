from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


class SupabaseClientFactory:
    def __init__(self, url: str, anon_key: str, service_role_key: str) -> None:
        self._url = url
        self._anon_key = anon_key
        self._service_role_key = service_role_key

    def get_anon_client(self) -> Client:
        return create_client(self._url, self._anon_key)

    def get_service_client(self) -> Client:
        return create_client(self._url, self._service_role_key)


@lru_cache
def get_supabase_factory() -> SupabaseClientFactory:
    return SupabaseClientFactory(
        url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
        service_role_key=settings.supabase_service_role_key,
    )
