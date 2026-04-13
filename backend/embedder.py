from __future__ import annotations

import time
from typing import List

import numpy as np
import requests

from backend.config import EMBEDDING_MODEL, HF_API_KEY

HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HF_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{HF_MODEL}"
HEADERS = {"Authorization": f"Bearer {HF_API_KEY}"} if HF_API_KEY else {}


def _normalize(vec: List[float]) -> np.ndarray:
    arr = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    return (arr / norm) if norm > 0 else arr


def _mean_pool_nested(vectors: list[list[float]]) -> np.ndarray:
    if not vectors:
        return np.zeros((384,), dtype=np.float32)
    normalized = [_normalize(vector) for vector in vectors]
    return np.asarray(np.mean(normalized, axis=0), dtype=np.float32)


def _call_hf(texts: List[str]) -> List[List[float] | list[list[float]]]:
    if not HF_API_KEY:
        raise RuntimeError("HF_API_KEY environment variable not set")

    for attempt in range(5):
        response = requests.post(
            HF_URL,
            headers=HEADERS,
            json={"inputs": texts, "options": {"wait_for_model": True}},
            timeout=60,
        )
        if response.status_code == 200:
            return response.json()
        if response.status_code == 503:
            wait_seconds = 10 * (attempt + 1)
            time.sleep(wait_seconds)
            continue
        raise RuntimeError(f"HF Inference API error: {response.status_code} {response.text}")
    raise RuntimeError("HF Inference API failed after 5 retries")


class Embedder:
    def __init__(self):
        self.remote = bool(HF_API_KEY)
        self.model = None
        if not self.remote:
            try:
                from sentence_transformers import SentenceTransformer
            except Exception as exc:  # pragma: no cover - fallback only when local package missing
                raise RuntimeError(
                    "Local embeddings unavailable: install sentence-transformers or set HF_API_KEY"
                ) from exc
            self.model = SentenceTransformer(EMBEDDING_MODEL)

    def embed_chunks(self, prefixed_texts: List[str]) -> np.ndarray:
        if self.remote:
            all_embeddings: list[np.ndarray] = []
            batch_size = 32
            for index in range(0, len(prefixed_texts), batch_size):
                batch = prefixed_texts[index : index + batch_size]
                raw = _call_hf(batch)
                for vec in raw:
                    if vec and isinstance(vec[0], list):
                        all_embeddings.append(_mean_pool_nested(vec))
                    else:
                        all_embeddings.append(_normalize(vec))  # type: ignore[arg-type]
            return np.stack(all_embeddings) if all_embeddings else np.empty((0, 384), dtype=np.float32)

        embeddings = self.model.encode(
            prefixed_texts,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        if self.remote:
            raw = _call_hf([query])
            vec = raw[0]
            if vec and isinstance(vec[0], list):
                return _mean_pool_nested(vec)  # type: ignore[arg-type]
            return _normalize(vec)  # type: ignore[arg-type]

        embedding = self.model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
        return np.asarray(embedding, dtype=np.float32)


_embedder_singleton: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder_singleton
    if _embedder_singleton is None:
        _embedder_singleton = Embedder()
    return _embedder_singleton
