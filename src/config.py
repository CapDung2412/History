from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    image_root: Path
    json_root: Path
    clip_model_name: str
    clip_pretrained: str
    clip_device: str | None
    pinecone_api_key: str | None
    pinecone_index_name: str
    pinecone_namespace: str
    pinecone_cloud: str
    pinecone_region: str

    @classmethod
    def load(cls, require_pinecone: bool = False) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        image_root = PROJECT_ROOT / os.getenv("IMAGE_ROOT", "images")
        json_root = PROJECT_ROOT / os.getenv("JSON_ROOT", "JSON")
        api_key = os.getenv("PINECONE_API_KEY")
        if require_pinecone and not api_key:
            raise ValueError("PINECONE_API_KEY is not configured")
        return cls(
            project_root=PROJECT_ROOT,
            image_root=image_root,
            json_root=json_root,
            clip_model_name=os.getenv("CLIP_MODEL_NAME", "ViT-B-32"),
            clip_pretrained=os.getenv("CLIP_PRETRAINED", "laion2b_s34b_b79k"),
            clip_device=os.getenv("CLIP_DEVICE") or None,
            pinecone_api_key=api_key,
            pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", "di-san-lens"),
            pinecone_namespace=os.getenv("PINECONE_NAMESPACE", "heritage-images-v1"),
            pinecone_cloud=os.getenv("PINECONE_CLOUD", "aws"),
            pinecone_region=os.getenv("PINECONE_REGION", "us-east-1"),
        )
