from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.config import PROJECT_ROOT
from src.dataset.validate_dataset import validate
from src.repositories import RepositoryError, SupabaseRestClient
from src.repositories.content import build_category_challenge
from src.repositories.loader import load_artifacts


@dataclass(frozen=True)
class TableSpec:
    table: str
    key_fields: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]

    @property
    def on_conflict(self) -> str:
        return ",".join(self.key_fields)

    @property
    def columns(self) -> str:
        names = sorted({key for row in self.rows for key in row})
        return ",".join(names or self.key_fields)


@dataclass(frozen=True)
class TablePlan:
    spec: TableSpec
    added: tuple[dict[str, Any], ...]
    updated: tuple[dict[str, Any], ...]
    skipped: tuple[dict[str, Any], ...]

    @property
    def changed(self) -> tuple[dict[str, Any], ...]:
        return self.added + self.updated

    def summary(self) -> dict[str, int]:
        return {
            "desired": len(self.spec.rows),
            "added": len(self.added),
            "updated": len(self.updated),
            "skipped": len(self.skipped),
            "errors": 0,
        }


def _row_key(row: dict[str, Any], fields: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(row.get(field) for field in fields)


def plan_table(spec: TableSpec, existing_rows: list[dict[str, Any]]) -> TablePlan:
    desired_keys: set[tuple[Any, ...]] = set()
    for row in spec.rows:
        key = _row_key(row, spec.key_fields)
        if any(value is None for value in key) or key in desired_keys:
            raise ValueError(f"Desired table {spec.table} contains a missing or duplicate key {key!r}")
        desired_keys.add(key)
    existing: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in existing_rows:
        key = _row_key(row, spec.key_fields)
        if key in existing:
            raise ValueError(f"Remote table {spec.table} contains duplicate key {key!r}")
        existing[key] = row

    added: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for desired in spec.rows:
        current = existing.get(_row_key(desired, spec.key_fields))
        if current is None:
            added.append(desired)
            continue
        comparable = {field: current.get(field) for field in desired}
        if comparable == desired:
            skipped.append(desired)
        else:
            updated.append(desired)
    return TablePlan(spec, tuple(added), tuple(updated), tuple(skipped))


def build_table_specs(json_root: Path, image_root: Path) -> tuple[TableSpec, ...]:
    artifacts = load_artifacts(json_root, image_root)
    categories = tuple(sorted({artifact.category for artifact in artifacts.values()}))

    items: list[dict[str, Any]] = []
    stories: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    tags: dict[str, dict[str, Any]] = {}
    item_tags: list[dict[str, Any]] = []
    challenges: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []

    for artifact in artifacts.values():
        items.append(
            {
                "id": artifact.id,
                "slug": artifact.slug,
                "name": artifact.name,
                "category": artifact.category,
                "dataset_name": artifact.dataset_name,
                "dataset_version": artifact.dataset_version,
                "address": artifact.location.address,
                "city": artifact.location.city,
                "province": artifact.location.province,
                "country": artifact.location.country,
                "latitude": artifact.location.latitude,
                "longitude": artifact.location.longitude,
                "published": artifact.published,
            }
        )
        history = artifact.historical_info
        stories.append(
            {
                "item_id": artifact.id,
                "title": history.title,
                "description": history.description,
                "historical_period": history.historical_period,
                "historical_year": history.year,
                "event_name": history.event,
                "source_text": history.source,
            }
        )
        images.extend(
            {
                "id": image.id,
                "item_id": artifact.id,
                "filename": image.filename,
                "relative_path": image.relative_path,
                "drive_url": image.drive_url,
                "caption": image.caption,
                "image_year": image.year,
                "view_name": image.view,
                "sort_order": image.sort_order,
            }
            for image in artifact.images
        )
        sources.extend(source.to_dict() for source in artifact.sources)
        for tag in artifact.tags:
            tags[tag] = {"slug": tag, "label": tag}
            item_tags.append({"item_id": artifact.id, "tag_slug": tag})

        challenge = build_category_challenge(artifact, categories)
        if challenge:
            challenges.append(
                {
                    "id": challenge.id,
                    "item_id": artifact.id,
                    "question_type": challenge.type,
                    "question": challenge.question,
                    "explanation": challenge.explanation,
                    "source_field": challenge.source_field,
                    "published": True,
                }
            )
            options.extend(
                {
                    "id": option.id,
                    "challenge_id": challenge.id,
                    "label": option.label,
                    "is_correct": option.is_correct,
                    "sort_order": option.sort_order,
                }
                for option in challenge.options
            )

    return (
        TableSpec("heritage_items", ("id",), tuple(items)),
        TableSpec("heritage_stories", ("item_id",), tuple(stories)),
        TableSpec("heritage_images", ("id",), tuple(images)),
        TableSpec("heritage_sources", ("id",), tuple(sources)),
        TableSpec("heritage_tags", ("slug",), tuple(tags[key] for key in sorted(tags))),
        TableSpec("heritage_item_tags", ("item_id", "tag_slug"), tuple(item_tags)),
        TableSpec("heritage_challenges", ("id",), tuple(challenges)),
        TableSpec("heritage_challenge_options", ("id",), tuple(options)),
    )


def fetch_existing(
    client: SupabaseRestClient,
    spec: TableSpec,
    *,
    page_size: int = 500,
) -> list[dict[str, Any]]:
    if page_size < 1:
        raise ValueError("page_size must be positive")
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.select(
            spec.table,
            columns=spec.columns,
            order=",".join(f"{field}.asc" for field in spec.key_fields),
            limit=page_size,
            offset=offset,
        )
        rows.extend(page)
        # A project can configure max_rows below the requested page size.
        # Continue until empty instead of silently truncating at that server cap.
        if not page:
            return rows
        offset += len(page)


def apply_plan(client: SupabaseRestClient, plan: TablePlan, *, batch_size: int = 200) -> None:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    rows = plan.changed
    for start in range(0, len(rows), batch_size):
        client.insert(
            plan.spec.table,
            list(rows[start : start + batch_size]),
            on_conflict=plan.spec.on_conflict,
        )


def report_for_plans(
    plans: tuple[TablePlan, ...],
    *,
    mode: str,
    remote_compared: bool,
) -> dict[str, Any]:
    table_reports = {plan.spec.table: plan.summary() for plan in plans}
    totals = {
        key: sum(report[key] for report in table_reports.values())
        for key in ("desired", "added", "updated", "skipped", "errors")
    }
    return {
        "mode": mode,
        "remote_compared": remote_compared,
        "tables": table_reports,
        "totals": totals,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Idempotently import canonical heritage JSON into Supabase"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--compare-remote",
        action="store_true",
        help="Read Supabase and report changes without writing",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Read Supabase and upsert only added or changed rows",
    )
    parser.add_argument("--json", type=Path, default=PROJECT_ROOT / "JSON")
    parser.add_argument("--images", type=Path, default=PROJECT_ROOT / "images")
    parser.add_argument(
        "--schema",
        type=Path,
        default=PROJECT_ROOT / "schemas" / "heritage-item.schema.json",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--skip-dataset-validation", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 1000:
        print("--batch-size must be between 1 and 1000", file=sys.stderr)
        return 2

    try:
        validation_summary: dict[str, Any] | None = None
        if not args.skip_dataset_validation:
            validation_report = validate(args.images, args.json, args.schema)
            validation_summary = validation_report["summary"]
            if validation_summary["errors"]:
                output = {
                    "mode": "validation_failed",
                    "dataset": validation_summary,
                    "totals": {"desired": 0, "added": 0, "updated": 0, "skipped": 0, "errors": 1},
                }
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return 1

        specs = build_table_specs(args.json, args.images)
        remote_mode = args.compare_remote or args.apply
        if remote_mode:
            load_dotenv(PROJECT_ROOT / ".env")
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not url or not key:
                raise ValueError(
                    "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for remote mode"
                )
            client = SupabaseRestClient(url, key)
            plans = tuple(plan_table(spec, fetch_existing(client, spec)) for spec in specs)
            if args.apply:
                for plan in plans:
                    apply_plan(client, plan, batch_size=args.batch_size)
            report = report_for_plans(
                plans,
                mode="apply" if args.apply else "compare-remote",
                remote_compared=True,
            )
        else:
            plans = tuple(plan_table(spec, []) for spec in specs)
            report = report_for_plans(plans, mode="local-dry-run", remote_compared=False)
            report["note"] = "Counts assume an empty database; no network request or write was made."
        if validation_summary is not None:
            report["dataset"] = validation_summary
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RepositoryError) as exc:
        output = {
            "mode": "failed",
            "error": type(exc).__name__,
            "message": str(exc),
            "totals": {"desired": 0, "added": 0, "updated": 0, "skipped": 0, "errors": 1},
        }
        print(json.dumps(output, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
