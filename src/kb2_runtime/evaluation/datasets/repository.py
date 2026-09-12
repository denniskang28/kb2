from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import psycopg

from .contracts import DatasetCase, DatasetContent, GoldenDataset, ReviewEvent, canonical_bytes, content_digest


class DatasetRepository:
    """Append-only authoring catalog. Snapshot bytes remain in Artifact storage."""
    def __init__(self, connection: psycopg.AsyncConnection[Any]) -> None:
        self.connection = connection

    @classmethod
    async def connect(cls, **kwargs: Any) -> "DatasetRepository":
        return cls(await psycopg.AsyncConnection.connect(row_factory=dict_row, **kwargs))

    async def close(self) -> None:
        await self.connection.close()

    async def create(self, content: DatasetContent, operation: Literal["create", "import"] = "create") -> GoldenDataset:
        self._validate_operation(operation, ("create", "import"))
        identifier, revision_id = uuid4(), uuid4()
        persisted = self._without_reviews(content)
        initial_reviews = self._initial_reviews(content, operation)
        digest = content_digest(persisted)
        async with self.connection.cursor() as cursor:
            await cursor.execute("INSERT INTO golden_datasets (id, taxonomy_json) VALUES (%s, %s)", (identifier, Jsonb(content.taxonomy.model_dump(mode="json"))))
            await cursor.execute("INSERT INTO golden_dataset_revisions (id, dataset_id, revision, content_json, content_digest, operation) VALUES (%s,%s,1,%s,%s,%s) RETURNING created_at", (revision_id, identifier, Jsonb(persisted.model_dump(mode="json")), digest, operation))
            created_at = (await cursor.fetchone())["created_at"]
            await self._insert_reviews(cursor, revision_id, initial_reviews)
        await self.connection.commit()
        return await self.get(identifier, 1)

    async def edit(self, dataset_id: UUID, content: DatasetContent, operation: Literal["edit"] = "edit") -> GoldenDataset:
        self._validate_operation(operation, ("edit",))
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT r.id, r.revision, d.taxonomy_json FROM golden_dataset_revisions r JOIN golden_datasets d ON d.id=r.dataset_id WHERE r.dataset_id=%s ORDER BY r.revision DESC LIMIT 1 FOR UPDATE OF r, d", (dataset_id,))
            parent = await cursor.fetchone()
            if not parent: raise KeyError("dataset not found")
            if parent["taxonomy_json"] != content.taxonomy.model_dump(mode="json"):
                raise ValueError("dataset taxonomy is immutable")
            revision_id, number, persisted = uuid4(), parent["revision"] + 1, self._without_reviews(content)
            digest = content_digest(persisted)
            await cursor.execute("INSERT INTO golden_dataset_revisions (id, dataset_id, revision, parent_revision_id, content_json, content_digest, operation) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING created_at", (revision_id, dataset_id, number, parent["id"], Jsonb(persisted.model_dump(mode="json")), digest, operation))
            created_at = (await cursor.fetchone())["created_at"]
        await self.connection.commit()
        return GoldenDataset(id=dataset_id, revision_id=revision_id, revision=number, parent_revision_id=parent["id"], content=persisted, content_digest=digest, operation=operation, created_at=created_at)

    async def get(self, dataset_id: UUID, revision: int) -> GoldenDataset:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT id, parent_revision_id, content_json, content_digest, operation, created_at FROM golden_dataset_revisions WHERE dataset_id=%s AND revision=%s", (dataset_id, revision))
            row = await cursor.fetchone()
            if not row: raise KeyError("dataset revision not found")
            await cursor.execute("SELECT case_id, operation, reviewer, reviewed_at, reviewed_content_digest FROM golden_dataset_reviews WHERE dataset_revision_id=%s ORDER BY reviewed_at, id", (row["id"],))
            review_rows = await cursor.fetchall()
        content = DatasetContent.model_validate(row["content_json"])
        reviews: dict[str, list[ReviewEvent]] = {}
        for item in review_rows:
            reviews.setdefault(item["case_id"], []).append(ReviewEvent(operation=item["operation"], reviewer=item["reviewer"], reviewed_at=item["reviewed_at"], content_digest=item["reviewed_content_digest"]))
        def with_reviews(case: DatasetCase) -> DatasetCase:
            return case.model_copy(update={"reviews": tuple(reviews.get(case.id, ()))})
        hydrated = content.model_copy(update={"annotations": tuple(with_reviews(item) for item in content.annotations), "query_cases": tuple(with_reviews(item) for item in content.query_cases)})
        return GoldenDataset(id=dataset_id, revision_id=row["id"], revision=revision, parent_revision_id=row["parent_revision_id"], content=hydrated, content_digest=row["content_digest"], operation=row["operation"], created_at=row["created_at"])

    async def record_review(self, dataset_id: UUID, revision: int, case_id: str, review: ReviewEvent) -> None:
        async with self.connection.cursor() as cursor:
            await cursor.execute("SELECT id, content_json FROM golden_dataset_revisions WHERE dataset_id=%s AND revision=%s", (dataset_id, revision))
            row = await cursor.fetchone()
            if not row: raise KeyError("dataset revision not found")
            content = DatasetContent.model_validate(row["content_json"])
            case = next((item for item in (*content.annotations, *content.query_cases) if item.id == case_id), None)
            if not case or review.content_digest != hashlib.sha256(canonical_bytes(case)).hexdigest():
                raise ValueError("review does not bind the stored case revision")
            await cursor.execute("INSERT INTO golden_dataset_reviews (id, dataset_revision_id, case_id, operation, reviewer, reviewed_content_digest, reviewed_at) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uuid4(), row["id"], case_id, review.operation, review.reviewer, review.content_digest, review.reviewed_at))
        await self.connection.commit()

    @staticmethod
    def _without_reviews(content: DatasetContent) -> DatasetContent:
        def clear(case: DatasetCase) -> DatasetCase:
            return case.model_copy(update={"reviews": ()})
        return content.model_copy(update={"annotations": tuple(clear(case) for case in content.annotations), "query_cases": tuple(clear(case) for case in content.query_cases)})

    @staticmethod
    def _initial_reviews(content: DatasetContent, operation: str) -> DatasetContent:
        """Only a verified imported manual case may replay review provenance."""
        if operation != "import":
            return DatasetRepository._without_reviews(content)
        def permitted(case: DatasetCase) -> DatasetCase:
            if case.provenance.origin.value == "generated":
                return case.model_copy(update={"reviews": ()})
            digest = hashlib.sha256(canonical_bytes(case.model_copy(update={"reviews": ()}))).hexdigest()
            return case.model_copy(update={"reviews": tuple(item for item in case.reviews if item.content_digest == digest)})
        return content.model_copy(update={"annotations": tuple(permitted(case) for case in content.annotations), "query_cases": tuple(permitted(case) for case in content.query_cases)})

    @staticmethod
    def _validate_operation(operation: str, allowed: tuple[str, ...]) -> None:
        if operation not in allowed:
            raise ValueError("dataset revision operation is invalid")

    @staticmethod
    async def _insert_reviews(cursor: Any, revision_id: UUID, content: DatasetContent) -> None:
        for case in (*content.annotations, *content.query_cases):
            for review in case.reviews:
                if review.content_digest == hashlib.sha256(canonical_bytes(case.model_copy(update={"reviews": ()}))).hexdigest():
                    await cursor.execute("INSERT INTO golden_dataset_reviews (id, dataset_revision_id, case_id, operation, reviewer, reviewed_content_digest, reviewed_at) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uuid4(), revision_id, case.id, review.operation, review.reviewer, review.content_digest, review.reviewed_at))
