"""
core/embeddings.py
==================
Local embedding engine using sentence-transformers.
Model downloads once (~90MB), then runs fully offline.
ZERO API cost — no rate limits, no key needed.

Model: all-MiniLM-L6-v2
  - 384-dim vectors
  - Fast (14,000 sentences/sec on CPU)
  - Good semantic similarity for job matching
"""

import logging
from typing import List, Union
from functools import lru_cache

import numpy as np

logger = logging.getLogger("job_agent.embeddings")

# ── Singleton model loader ────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_model():
    """Load the embedding model once and cache it in memory."""
    from sentence_transformers import SentenceTransformer
    from core.config import EMBED_MODEL

    logger.info("Loading embedding model: %s (first run downloads ~90MB)", EMBED_MODEL)
    model = SentenceTransformer(EMBED_MODEL)
    logger.info("Embedding model loaded.")
    return model


# ── Public API ────────────────────────────────────────────────────────────────

def embed_text(text: str) -> List[float]:
    """
    Embed a single text string.

    Args:
        text: Any text (job description, candidate profile, etc.)

    Returns:
        List of 384 floats (embedding vector)
    """
    model = _load_model()
    vector = model.encode(text, convert_to_numpy=True)
    return vector.tolist()


def embed_texts(texts: List[str], batch_size: int = 32,
                show_progress: bool = False) -> List[List[float]]:
    """
    Embed a list of texts in batches (efficient for many documents).

    Args:
        texts:         List of strings to embed
        batch_size:    How many to encode per batch
        show_progress: Show tqdm progress bar

    Returns:
        List of embedding vectors
    """
    model = _load_model()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
    )
    return vectors.tolist()


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    Returns value between -1 and 1 (higher = more similar).
    """
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def rank_by_similarity(query_vec: List[float],
                       candidates: List[dict],
                       vec_key: str = "embedding",
                       top_k: int = 10) -> List[dict]:
    """
    Rank a list of candidate dicts by cosine similarity to a query vector.

    Args:
        query_vec:   The query embedding (candidate profile vector)
        candidates:  List of dicts, each must have a vec_key field
        vec_key:     Key in each dict that holds the embedding
        top_k:       Return top K results

    Returns:
        Sorted list of candidates with added "match_score" field (0–100)
    """
    scored = []
    for item in candidates:
        if vec_key not in item:
            continue
        score = cosine_similarity(query_vec, item[vec_key])
        item_copy = dict(item)
        item_copy["match_score"] = round(score * 100, 1)  # convert to 0-100
        scored.append(item_copy)

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored[:top_k]