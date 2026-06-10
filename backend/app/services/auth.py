from __future__ import annotations

import logging
import secrets
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.records import OrganizationCreate
from app.db.repositories.organization_repository import OrganizationRepository
from app.db.repositories.subscription_repository import SubscriptionRepository
from app.schemas.auth import AuthOrganization, AuthResponse, AuthUser, LoginRequest, SignupRequest
from app.services.base import BaseService


logger = logging.getLogger(__name__)


class AuthService(BaseService):
    def __init__(self, supabase_factory: SupabaseClientFactory | None = None) -> None:
        self.supabase_factory = supabase_factory or get_supabase_factory()
        self.auth_client = self.supabase_factory.get_anon_client()
        self.service_client = self.supabase_factory.get_service_client()

    async def signup(self, payload: SignupRequest) -> AuthResponse:
        auth_response = self.auth_client.auth.sign_up(
            {
                "email": str(payload.email),
                "password": payload.password,
                "options": {
                    "data": {
                        "full_name": payload.full_name,
                        "organization_name": payload.organization_name,
                    }
                },
            }
        )
        auth_user = self._extract_auth_user(auth_response)
        if auth_user is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Supabase Auth did not return a user for signup",
            )

        user_id = UUID(str(self._read_attr(auth_user, "id")))
        email = self._read_attr(auth_user, "email") or str(payload.email)

        # TODO: Move signup orchestration into a DB RPC/transaction before production.
        try:
            self._create_user_profile(
                user_id=user_id,
                email=email,
                full_name=payload.full_name,
            )
            organization = self._create_organization(payload.organization_name)
            membership = self._create_owner_membership(
                organization_id=organization.id,
                user_id=user_id,
            )
            self._create_default_subscription_if_available(organization.id)
        except Exception as exc:
            logger.exception("Signup post-auth provisioning failed for auth user %s", user_id)
            self._cleanup_auth_user_after_failed_signup(user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Signup provisioning failed. Please try again.",
            ) from exc

        access_token = self._session_value(auth_response, "access_token")
        if not access_token:
            access_token = ""

        return AuthResponse(
            access_token=access_token,
            refresh_token=self._session_value(auth_response, "refresh_token"),
            user_id=user_id,
            organizations=[
                AuthOrganization(
                    organization_id=organization.id,
                    organization_name=organization.name,
                    organization_slug=organization.slug,
                    membership_id=UUID(str(membership["id"])),
                    role=membership["role"],
                    status=membership["status"],
                )
            ],
        )

    async def login(self, payload: LoginRequest) -> AuthResponse:
        auth_response = self.auth_client.auth.sign_in_with_password(
            {
                "email": str(payload.email),
                "password": payload.password,
            }
        )
        access_token = self._session_value(auth_response, "access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        auth_user = self._extract_auth_user(auth_response)
        if auth_user is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Supabase Auth did not return a user for login",
            )

        user_id = UUID(str(self._read_attr(auth_user, "id")))
        return AuthResponse(
            access_token=access_token,
            refresh_token=self._session_value(auth_response, "refresh_token"),
            user_id=user_id,
            organizations=self._list_user_organizations(user_id),
        )

    async def get_user_from_token(self, access_token: str) -> AuthUser:
        try:
            # Supabase's SDK validates this JWT with GoTrue and returns the auth user.
            # This codebase does not currently have a safer per-request authorized client wrapper.
            response = self.auth_client.auth.get_user(access_token)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
            ) from exc

        auth_user = self._extract_auth_user(response)
        if auth_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
            )
        return AuthUser(
            user_id=UUID(str(self._read_attr(auth_user, "id"))),
            email=self._read_attr(auth_user, "email"),
        )

    def _create_user_profile(self, user_id: UUID, email: str, full_name: str | None) -> None:
        self.service_client.table("users").upsert(
            {
                "id": str(user_id),
                "email": email,
                "full_name": full_name,
            }
        ).execute()

    def _create_organization(self, name: str):
        repository = OrganizationRepository(self.service_client)
        slug = self._generate_unique_organization_slug(repository, name)
        return repository.create(
            OrganizationCreate(
                name=name,
                slug=slug,
            )
        )

    def _create_owner_membership(self, organization_id: UUID, user_id: UUID) -> dict[str, Any]:
        response = (
            self.service_client.table("memberships")
            .insert(
                {
                    "organization_id": str(organization_id),
                    "user_id": str(user_id),
                    "role": "owner",
                    "status": "active",
                }
            )
            .execute()
        )
        row = self._first_row(response.data)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Membership creation returned no row",
            )
        return row

    def _create_default_subscription_if_available(self, organization_id: UUID) -> None:
        subscription_repository = SubscriptionRepository(self.service_client)
        plan = subscription_repository.get_plan_by_slug("starter")
        if plan is None:
            return

        today = date.today()
        subscription_repository.create_subscription(
            organization_id,
            {
                "subscription_plan_id": plan["id"],
                "status": "trialing",
                "current_period_start": today,
                "current_period_end": today + timedelta(days=30),
            },
        )

    def _list_user_organizations(self, user_id: UUID) -> list[AuthOrganization]:
        response = (
            self.service_client.table("memberships")
            .select("id, role, status, organization_id, organizations(id, name, slug)")
            .eq("user_id", str(user_id))
            .eq("status", "active")
            .execute()
        )
        organizations: list[AuthOrganization] = []
        for row in response.data or []:
            organization = row.get("organizations") or {}
            organizations.append(
                AuthOrganization(
                    organization_id=UUID(str(row["organization_id"])),
                    organization_name=organization.get("name", ""),
                    organization_slug=organization.get("slug"),
                    membership_id=UUID(str(row["id"])),
                    role=row["role"],
                    status=row["status"],
                )
            )
        return organizations

    def _extract_auth_user(self, response: Any) -> Any | None:
        return self._read_attr(response, "user")

    def _session_value(self, response: Any, key: str) -> str | None:
        session = self._read_attr(response, "session")
        if session is None:
            return None
        return self._read_attr(session, key)

    def _read_attr(self, value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _first_row(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return data[0] if data else {}
        if isinstance(data, dict):
            return data
        return {}

    def _slugify(self, value: str) -> str:
        normalized = "".join(char.lower() if char.isalnum() else "-" for char in value.strip())
        parts = [part for part in normalized.split("-") if part]
        return "-".join(parts) or "organization"

    def _generate_unique_organization_slug(
        self,
        repository: OrganizationRepository,
        organization_name: str,
    ) -> str:
        base_slug = self._slugify(organization_name)
        if repository.get_by_slug(base_slug) is None:
            return base_slug

        for _ in range(5):
            candidate = f"{base_slug}-{secrets.token_hex(2)}"
            if repository.get_by_slug(candidate) is None:
                return candidate

        raise RuntimeError("Unable to generate a unique organization slug")

    def _cleanup_auth_user_after_failed_signup(self, user_id: UUID) -> None:
        auth_admin = self._read_attr(self.service_client.auth, "admin")
        delete_user = self._read_attr(auth_admin, "delete_user")
        if not callable(delete_user):
            # TODO: Current Supabase SDK does not expose admin.delete_user here; add auth cleanup when available.
            logger.error("Supabase admin auth user deletion is not available; failed signup user remains: %s", user_id)
            return

        try:
            delete_user(str(user_id))
        except Exception:
            logger.exception("Failed to cleanup Supabase auth user after signup provisioning failure: %s", user_id)
