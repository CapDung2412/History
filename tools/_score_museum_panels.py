from __future__ import annotations

from pathlib import Path

import numpy as np

from src.clip.encoder import ClipEncoder


ROOT = Path(__file__).resolve().parents[1]
PROMPTS = [
    "a museum information panel full of explanatory text",
    "a close-up photograph of a small museum object label with text",
    "a modern wall sign or title panel in a museum exhibition",
    "a historical paper document displayed in a museum",
    "a museum artifact displayed in a glass case",
    "a collection of historical objects in a museum display",
    "a museum room overview",
]


def main() -> None:
    files = sorted((ROOT / "images").glob("*.jpg"), key=lambda path: int(path.stem.split("_", 1)[0]))
    probe_indexes = [0, 2, 22, 23, 25, 28, 31, 33, 34, 37, 48, 57, 75, 78, 95, 96, 100, 115, 119, 125, 134, 140, 165, 173, 183, 215, 228, 230, 239, 241, 243, 247, 254]
    encoder = ClipEncoder("ViT-B-32", "laion2b_s34b_b79k", device="cpu")
    text = encoder.encode_texts(PROMPTS)
    image = encoder.encode_images([files[index] for index in probe_indexes], batch_size=8)
    scores = image @ text.T
    for index, row in zip(probe_indexes, scores, strict=True):
        best = np.argsort(row)[::-1][:3]
        compact = " ".join(f"p{candidate}={row[candidate]:.3f}" for candidate in best)
        print(f"{index:04d} {compact}")


if __name__ == "__main__":
    main()
