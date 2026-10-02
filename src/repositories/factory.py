from __future__ import annotations

import os
from pathlib import Path

from .base import HeritageRepository
from .fallback import FallbackHeritageRepository
from .json_repository import JsonHeritageRepository
from .supabase_repository import SupabaseHeritageRepository, SupabaseTransport


def build_repository(
    json_root: Path,
    image_root: Path,
    *,
    supabase_url: str | None = None,
    service_role_key: str | None = None,
    analytics_path: Path | None = None,
    supabase_transport: SupabaseTransport | None = None,
    skip_missing_images: bool = False,
) -> HeritageRepository:
    fallback = JsonHeritageRepository(
        json_root=json_root,
        image_root=image_root,
        analytics_path=analytics_path,
        skip_missing_images=skip_missing_images,
    )
    if supabase_transport is not None:
        primary = SupabaseHeritageRepository(transport=supabase_transport)
        return FallbackHeritageRepository(primary, fallback)
    if supabase_url and service_role_key:
        primary = SupabaseHeritageRepository(supabase_url, service_role_key)
        return FallbackHeritageRepository(primary, fallback)
    return fallback


def build_repository_from_env(
    json_root: Path,
    image_root: Path,
    *,
    analytics_path: Path | None = None,
) -> HeritageRepository:
    return build_repository(
        json_root,
        image_root,
        supabase_url=os.getenv("SUPABASE_URL"),
        service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        analytics_path=analytics_path,
        skip_missing_images=True,
    )
