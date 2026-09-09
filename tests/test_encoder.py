from __future__ import annotations

import numpy as np
import torch

from src.clip.encoder import ClipEncoder


def test_normalize_is_float_unit_vector() -> None:
    values = torch.tensor([[3.0, 4.0]])
    normalized = ClipEncoder._normalize(values).numpy().astype(np.float32)
    assert normalized.dtype == np.float32
    assert np.allclose(np.linalg.norm(normalized, axis=1), 1.0)
