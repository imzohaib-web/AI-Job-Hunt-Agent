"""
core/vector_store.py
====================
Pinecone vector database client (free tier).
Free tier: 1 index, 100,000 vectors, serverless.

Sign up at: https://www.pinecone.io (no credit card needed)

Falls back to in-memory store if Pinecone key not configured,
so the system works even without the vector DB during development.
"""

import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger("job_agent.vectorstore")


# ── In-Memory Fallback (for dev/testing without Pinecone key) ─────────────────

class InMemoryVectorStore:
    """Simple in-memory vector store for development / no-key fallback."""

    def __init__(self):
        self._store: Dict[str, Dict] = {}
        logger.warning("Using IN-MEMORY vector store. Data lost on restart. "
                       "Set PINECONE_API_KEY in .env for persistence.")

    def upsert(self, vectors: List[Dict]) -> None:
        for v in vectors:
            self._store[v["id"]] = {"values": v["values"], "metadata": v.get("metadata", {})}

    def query(self, vector: List[float], top_k: int = 10,
              filter: Optional[Dict] = None) -> List[Dict]:
        from core.embeddings import cosine_similarity
        results = []
        for vid, data in self._store.items():
            score = cosine_similarity(vector, data["values"])
            results.append({"id": vid, "score": score, "metadata": data["metadata"]})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete(self, ids: List[str]) -> None:
        for vid in ids:
            self._store.pop(vid, None)

    def describe_index_stats(self) -> Dict:
        return {"total_vector_count": len(self._store)}


# ── Pinecone Store ─────────────────────────────────────────────────────────────

class PineconeVectorStore:
    """
    Wrapper around Pinecone serverless index.
    Creates the index automatically on first use.
    """

    DIMENSION = 384      # all-MiniLM-L6-v2 output dimension
    METRIC = "cosine"

    def __init__(self):
        from core.config import PINECONE_API_KEY, PINECONE_INDEX
        from pinecone import Pinecone, ServerlessSpec

        self.pc = Pinecone(api_key=PINECONE_API_KEY)
        self.index_name = PINECONE_INDEX

        # Create index if it doesn't exist yet
        existing = [idx.name for idx in self.pc.list_indexes()]
        if self.index_name not in existing:
            logger.info("Creating Pinecone index '%s'...", self.index_name)
            self.pc.create_index(
                name=self.index_name,
                dimension=self.DIMENSION,
                metric=self.METRIC,
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),  # free tier region
            )
            logger.info("Index created.")

        self.index = self.pc.Index(self.index_name)
        stats = self.index.describe_index_stats()
        logger.info("Pinecone connected. Vectors stored: %d",
                    stats.get("total_vector_count", 0))

    def upsert(self, vectors: List[Dict]) -> None:
        """
        Upsert vectors into Pinecone.

        Args:
            vectors: List of {"id": str, "values": List[float], "metadata": dict}
        """
        # Pinecone recommends batches of 100
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i: i + batch_size]
            self.index.upsert(vectors=batch)
        logger.info("Upserted %d vectors to Pinecone.", len(vectors))

    def query(self, vector: List[float], top_k: int = 10,
              filter: Optional[Dict] = None) -> List[Dict]:
        """
        Query top-K similar vectors.

        Returns:
            List of {"id", "score", "metadata"} dicts
        """
        kwargs = {"vector": vector, "top_k": top_k, "include_metadata": True}
        if filter:
            kwargs["filter"] = filter

        response = self.index.query(**kwargs)
        return [
            {"id": m.id, "score": m.score, "metadata": m.metadata}
            for m in response.matches
        ]

    def delete(self, ids: List[str]) -> None:
        self.index.delete(ids=ids)

    def describe_index_stats(self) -> Dict:
        return dict(self.index.describe_index_stats())


# ── Factory ────────────────────────────────────────────────────────────────────

def get_vector_store():
    """
    Return Pinecone store if key configured, else in-memory fallback.
    Singleton pattern — same instance reused across calls.
    """
    from core.config import PINECONE_API_KEY

    if not hasattr(get_vector_store, "_instance"):
        if PINECONE_API_KEY:
            try:
                get_vector_store._instance = PineconeVectorStore()
            except Exception as e:
                logger.error("Pinecone init failed (%s). Using in-memory store.", e)
                get_vector_store._instance = InMemoryVectorStore()
        else:
            get_vector_store._instance = InMemoryVectorStore()

    return get_vector_store._instance