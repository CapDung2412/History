from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Sequence

import numpy as np
import open_clip
import torch
from PIL import Image, ImageOps


class ClipEncoder:
    def __init__(self, model_name: str, pretrained: str, device: str | None = None) -> None:
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model_name = model_name
        self.pretrained = pretrained
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=self.device
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self._dimension: int | None = None

    def _context(self):
        return torch.autocast(device_type="cuda") if self.device.type == "cuda" else nullcontext()

    @staticmethod
    def _normalize(features: torch.Tensor) -> torch.Tensor:
        return features / features.norm(dim=-1, keepdim=True).clamp_min(1e-12)

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._dimension = int(self.encode_texts(["dimension probe"]).shape[1])
        return self._dimension

    def encode_images(self, paths: Sequence[Path], batch_size: int = 32) -> np.ndarray:
        outputs: list[np.ndarray] = []
        for start in range(0, len(paths), batch_size):
            tensors = []
            for path in paths[start : start + batch_size]:
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source).convert("RGB")
                    tensors.append(self.preprocess(image))
            batch = torch.stack(tensors).to(self.device)
            with torch.inference_mode(), self._context():
                features = self._normalize(self.model.encode_image(batch))
            outputs.append(features.float().cpu().numpy())
        return np.concatenate(outputs).astype(np.float32, copy=False)

    def encode_image(self, path: Path) -> np.ndarray:
        return self.encode_images([path], batch_size=1)[0]

    def encode_pil(self, image: Image.Image) -> np.ndarray:
        prepared = ImageOps.exif_transpose(image).convert("RGB")
        batch = self.preprocess(prepared).unsqueeze(0).to(self.device)
        with torch.inference_mode(), self._context():
            features = self._normalize(self.model.encode_image(batch))
        return features[0].float().cpu().numpy().astype(np.float32, copy=False)

    def encode_texts(self, texts: Sequence[str], batch_size: int = 64) -> np.ndarray:
        outputs: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            tokens = self.tokenizer(list(texts[start : start + batch_size])).to(self.device)
            with torch.inference_mode(), self._context():
                features = self._normalize(self.model.encode_text(tokens))
            outputs.append(features.float().cpu().numpy())
        return np.concatenate(outputs).astype(np.float32, copy=False)

    def encode_text(self, text: str) -> np.ndarray:
        return self.encode_texts([text], batch_size=1)[0]
