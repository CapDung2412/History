from __future__ import annotations

from pathlib import Path

import pytest

from scripts.import_supabase import (
    TableSpec,
    apply_plan,
    build_table_specs,
    fetch_existing,
    plan_table,
)
from tests.test_repositories import make_dataset


def test_import_specs_keep_original_ids_and_fk_order(tmp_path: Path) -> None:
    json_root, image_root = make_dataset(tmp_path)
    specs = build_table_specs(json_root, image_root)

    assert [spec.table for spec in specs] == [
        "heritage_items",
        "heritage_stories",
        "heritage_images",
        "heritage_sources",
        "heritage_tags",
        "heritage_item_tags",
        "heritage_challenges",
        "heritage_challenge_options",
    ]
    by_table = {spec.table: spec for spec in specs}
    assert [row["id"] for row in by_table["heritage_items"].rows] == [
        "item-1",
        "item-2",
        "item-3",
        "item-4",
    ]
    assert len(by_table["heritage_images"].rows) == 4
    assert len(by_table["heritage_challenges"].rows) == 4
    assert len(by_table["heritage_challenge_options"].rows) == 16


def test_import_plan_is_idempotent_and_detects_changed_rows() -> None:
    spec = TableSpec(
        "heritage_items",
        ("id",),
        (
            {"id": "item-1", "name": "A"},
            {"id": "item-2", "name": "B"},
            {"id": "item-3", "name": "C"},
        ),
    )
    existing = [
        {"id": "item-1", "name": "A"},
        {"id": "item-2", "name": "Old"},
    ]
    plan = plan_table(spec, existing)
    assert [row["id"] for row in plan.added] == ["item-3"]
    assert [row["id"] for row in plan.updated] == ["item-2"]
    assert [row["id"] for row in plan.skipped] == ["item-1"]

    after_upsert = list(spec.rows)
    second = plan_table(spec, after_upsert)
    assert second.added == ()
    assert second.updated == ()
    assert second.skipped == spec.rows


def test_import_plan_rejects_duplicate_desired_keys_before_remote_writes() -> None:
    spec = TableSpec("heritage_item_tags", ("item_id", "tag_slug"), (
        {"item_id": "item-1", "tag_slug": "historical_map"},
        {"item_id": "item-1", "tag_slug": "historical_map"},
    ))
    with pytest.raises(ValueError, match="duplicate key"):
        plan_table(spec, [])


class BatchClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], str | None]] = []

    def insert(self, table: str, rows: list[dict], *, on_conflict: str | None = None):
        self.calls.append((table, rows, on_conflict))


def test_apply_plan_batches_only_added_and_updated_rows() -> None:
    spec = TableSpec(
        "heritage_items",
        ("id",),
        tuple({"id": f"item-{index}", "name": str(index)} for index in range(5)),
    )
    plan = plan_table(spec, [{"id": "item-0", "name": "0"}])
    client = BatchClient()
    apply_plan(client, plan, batch_size=2)  # type: ignore[arg-type]
    assert [len(rows) for _, rows, _ in client.calls] == [2, 2]
    assert all(conflict == "id" for _, _, conflict in client.calls)


class PagingClient:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.offsets: list[int] = []
        self.orders: list[str] = []

    def select(
        self,
        _table: str,
        *,
        limit: int,
        offset: int,
        **kwargs,
    ) -> list[dict]:
        self.offsets.append(offset)
        self.orders.append(kwargs["order"])
        return self.rows[offset : offset + limit]


def test_fetch_existing_paginates_tables_larger_than_postgrest_default() -> None:
    rows = [{"item_id": f"item-{index}", "tag_slug": "tag"} for index in range(1201)]
    client = PagingClient(rows)
    spec = TableSpec("heritage_item_tags", ("item_id", "tag_slug"), ())
    assert fetch_existing(client, spec, page_size=500) == rows  # type: ignore[arg-type]
    assert client.offsets == [0, 500, 1000, 1201]
    assert set(client.orders) == {"item_id.asc,tag_slug.asc"}


def test_fetch_existing_handles_server_row_cap_below_requested_page_size() -> None:
    class CappedClient(PagingClient):
        def select(self, table: str, *, limit: int, offset: int, **kwargs):
            return super().select(table, limit=min(limit, 2), offset=offset, **kwargs)

    rows = [{"id": str(index)} for index in range(5)]
    client = CappedClient(rows)
    spec = TableSpec("heritage_items", ("id",), ())
    assert fetch_existing(client, spec, page_size=500) == rows  # type: ignore[arg-type]
    assert client.offsets == [0, 2, 4, 5]


def test_migration_enables_rls_and_blocks_client_writes() -> None:
    migration = Path("supabase/migrations/202609070001_initial_heritage.sql").read_text(
        encoding="utf-8"
    )
    assert "enable row level security" in migration
    assert "revoke all on public.recognition_requests from anon, authenticated" in migration
    assert "validate_recognition_feedback" in migration
    assert "grant all on public.recognition_requests to service_role" in migration
    assert "(?:[-_][a-z0-9]+)*" in migration
