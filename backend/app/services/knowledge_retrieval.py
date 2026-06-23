from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.supabase import SupabaseClientFactory, get_supabase_factory
from app.db.models.common import FaqStatus, PaginationOptions, ProductStatus, SortDirection
from app.db.models.queries import SortOptions
from app.db.models.records import FaqRead, ProductRead
from app.db.repositories.base_repository import OrganizationContext
from app.db.repositories.faq_repository import FaqRepository
from app.db.repositories.product_repository import ProductRepository


POLICY_KEYWORDS = frozenset(
    {
        "policy",
        "policies",
        "store",
        "shipping",
        "delivery",
        "return",
        "returns",
        "refund",
        "refunds",
        "exchange",
        "exchanges",
        "cancellation",
        "cancel",
    }
)
SCORING_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "can",
        "do",
        "for",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "policies",
        "policy",
        "show",
        "the",
        "to",
        "what",
        "when",
        "with",
        "you",
        "your",
    }
)
TOKEN_RE = re.compile(r"[a-z0-9]+")


class KnowledgeRetrievalService:
    def __init__(
        self,
        supabase_factory: SupabaseClientFactory | None = None,
        faq_repository: FaqRepository | None = None,
        product_repository: ProductRepository | None = None,
        max_candidates: int = 100,
    ) -> None:
        self.max_candidates = max_candidates
        if faq_repository is not None and product_repository is not None:
            self.faq_repository = faq_repository
            self.product_repository = product_repository
            return

        self.supabase_factory = supabase_factory or get_supabase_factory()
        service_client = self.supabase_factory.get_service_client()
        self.faq_repository = faq_repository or FaqRepository(service_client)
        self.product_repository = product_repository or ProductRepository(service_client)

    def retrieve_context(
        self,
        organization_id: UUID | OrganizationContext,
        customer_message: str,
        *,
        faq_limit: int = 5,
        product_limit: int = 5,
        policy_limit: int = 5,
    ) -> dict[str, list[dict[str, Any]]]:
        context = self._organization_context(organization_id)
        faqs = self.retrieve_faqs(context, customer_message, limit=faq_limit)
        products = self.retrieve_products(context, customer_message, limit=product_limit)
        policies = self.retrieve_policies(context, customer_message, limit=policy_limit)
        return {
            "faqs": [self._faq_payload(faq) for faq in faqs],
            "products": [self._product_payload(product) for product in products],
            "policies": [self._faq_payload(policy) for policy in policies],
            "sources": self._sources(faqs=faqs, products=products, policies=policies),
        }

    def retrieve_faqs(
        self,
        organization_id: UUID | OrganizationContext,
        customer_message: str,
        *,
        limit: int = 5,
    ) -> list[FaqRead]:
        context = self._organization_context(organization_id)
        candidates = self._active_faqs(context)
        ranked = self._rank_records(
            candidates,
            customer_message,
            text_getter=lambda faq: [faq.question, faq.answer, faq.category, *self._metadata_terms(faq.metadata)],
        )
        return [faq for faq in ranked if not self._is_policy_faq(faq)][:limit]

    def retrieve_products(
        self,
        organization_id: UUID | OrganizationContext,
        customer_message: str,
        *,
        limit: int = 5,
    ) -> list[ProductRead]:
        context = self._organization_context(organization_id)
        candidates = self._active_products(context)
        ranked = self._rank_records(
            candidates,
            customer_message,
            text_getter=lambda product: [
                product.name,
                product.sku,
                product.category,
                product.brand,
                product.color,
                product.size,
                product.material,
                *self._tag_terms(product),
            ],
        )
        return ranked[:limit]

    def retrieve_policies(
        self,
        organization_id: UUID | OrganizationContext,
        customer_message: str,
        *,
        limit: int = 5,
    ) -> list[FaqRead]:
        context = self._organization_context(organization_id)
        candidates = [faq for faq in self._active_faqs(context) if self._is_policy_faq(faq)]
        ranked = self._rank_records(
            candidates,
            customer_message,
            text_getter=lambda faq: [faq.question, faq.answer, faq.category, *self._metadata_terms(faq.metadata)],
        )
        if not ranked and self._policy_terms(customer_message):
            ranked = self._rank_records(
                candidates,
                customer_message,
                text_getter=lambda faq: [
                    faq.question,
                    faq.answer,
                    faq.category,
                    *self._metadata_terms(faq.metadata),
                ],
                include_zero_score=True,
            )
        return ranked[:limit]

    def _active_faqs(self, context: OrganizationContext) -> list[FaqRead]:
        page = self.faq_repository.list_active(
            context,
            pagination=PaginationOptions(limit=self.max_candidates),
            sort=SortOptions(field="created_at", direction=SortDirection.ASC),
        )
        return [faq for faq in page.items if faq.status == FaqStatus.ACTIVE]

    def _active_products(self, context: OrganizationContext) -> list[ProductRead]:
        page = self.product_repository.list_active(
            context,
            pagination=PaginationOptions(limit=self.max_candidates),
            sort=SortOptions(field="created_at", direction=SortDirection.ASC),
        )
        return [product for product in page.items if product.status == ProductStatus.ACTIVE]

    def _rank_records(
        self,
        records: Iterable[Any],
        customer_message: str,
        *,
        text_getter,
        include_zero_score: bool = False,
    ) -> list[Any]:
        normalized_message = self._normalize(customer_message)
        message_tokens = set(self._scoring_tokens(customer_message))
        ranked: list[tuple[int, str, Any]] = []

        for record in records:
            score = self._score_texts(
                normalized_message=normalized_message,
                message_tokens=message_tokens,
                texts=text_getter(record),
            )
            if score > 0 or include_zero_score:
                ranked.append((score, self._stable_key(record), record))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [record for _, _, record in ranked]

    def _score_texts(
        self,
        *,
        normalized_message: str,
        message_tokens: set[str],
        texts: Iterable[str | None],
    ) -> int:
        score = 0
        for text in texts:
            if not text:
                continue
            normalized_text = self._normalize(text)
            if not normalized_text:
                continue
            text_tokens = set(self._scoring_tokens(normalized_text))
            if normalized_text in normalized_message:
                score += 20
            if normalized_message and normalized_message in normalized_text:
                score += 12
            score += len(message_tokens & text_tokens) * 3
        return score

    def _is_policy_faq(self, faq: FaqRead) -> bool:
        terms = {
            *self._tokens(faq.category or ""),
            *self._tokens(str(faq.metadata.get("type", ""))),
            *self._tokens(str(faq.metadata.get("source_type", ""))),
            *self._tokens(str(faq.metadata.get("policy_type", ""))),
        }
        return bool(terms & POLICY_KEYWORDS)

    def _policy_terms(self, customer_message: str) -> set[str]:
        return set(self._tokens(customer_message)) & POLICY_KEYWORDS

    def _metadata_terms(self, metadata: dict[str, Any]) -> list[str]:
        terms: list[str] = []
        for key in ("type", "source_type", "policy_type", "tags"):
            value = metadata.get(key)
            if isinstance(value, list):
                terms.extend(str(item) for item in value)
            elif value is not None:
                terms.append(str(value))
        return terms

    def _tag_terms(self, product: ProductRead) -> list[str]:
        terms: list[str] = []
        for container in (product.attributes, product.metadata):
            tags = container.get("tags")
            if isinstance(tags, list):
                terms.extend(str(tag) for tag in tags)
            elif isinstance(tags, str):
                terms.append(tags)
        return terms

    def _faq_payload(self, faq: FaqRead) -> dict[str, Any]:
        return {
            "id": str(faq.id),
            "organization_id": str(faq.organization_id),
            "question": faq.question,
            "answer": faq.answer,
            "category": faq.category,
            "metadata": faq.metadata,
        }

    def _product_payload(self, product: ProductRead) -> dict[str, Any]:
        return {
            "id": str(product.id),
            "organization_id": str(product.organization_id),
            "name": product.name,
            "sku": product.sku,
            "description": product.description,
            "category": product.category,
            "brand": product.brand,
            "price": self._json_safe(product.price),
            "currency": product.currency,
            "inventory_quantity": product.inventory_quantity,
            "image_url": product.image_url,
            "product_url": product.product_url,
            "attributes": product.attributes,
            "metadata": product.metadata,
        }

    def _sources(
        self,
        *,
        faqs: Iterable[FaqRead],
        products: Iterable[ProductRead],
        policies: Iterable[FaqRead],
    ) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = []
        sources.extend(self._source("faq", faq) for faq in faqs)
        sources.extend(self._source("product", product) for product in products)
        sources.extend(self._source("policy", policy) for policy in policies)
        return sources

    def _source(self, source_type: str, record: FaqRead | ProductRead) -> dict[str, str]:
        return {
            "type": source_type,
            "id": str(record.id),
            "organization_id": str(record.organization_id),
        }

    def _organization_context(self, value: UUID | OrganizationContext) -> OrganizationContext:
        if isinstance(value, OrganizationContext):
            return value
        return OrganizationContext(organization_id=value)

    def _stable_key(self, record: FaqRead | ProductRead) -> str:
        created_at = record.created_at.isoformat() if record.created_at else ""
        return f"{created_at}:{record.id}"

    def _tokens(self, value: str) -> list[str]:
        return TOKEN_RE.findall(value.lower())

    def _scoring_tokens(self, value: str) -> list[str]:
        return [
            token
            for token in self._tokens(value)
            if token not in SCORING_STOPWORDS and not token.isdigit()
        ]

    def _normalize(self, value: str) -> str:
        return " ".join(self._tokens(value))

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        return value
