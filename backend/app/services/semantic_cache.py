"""
In-memory semantic cache for RAG retrieval results.

Caches query embeddings + retrieval results. On cache hit (cosine similarity > threshold),
returns cached results without calling the retrieval pipeline.

TTL-based expiration prevents stale results.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_SIMILARITY_THRESHOLD = 0.95
DEFAULT_TTL_SECONDS = 300  # 5 minutes
DEFAULT_MAX_ENTRIES = 256


@dataclass
class CacheEntry:
    embedding: list[float]
    result: dict  # {"chunks": [...], "sources": [...]}
    created_at: float = field(default_factory=time.monotonic)
    hit_count: int = 0


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embedding_key(embedding: list[float], namespace: str = "") -> str:
    """Create a short hash key from an embedding for fast dict lookup."""
    raw = namespace + "|" + ",".join(f"{v:.6f}" for v in embedding[:16])  # first 16 dims as rough key
    return hashlib.md5(raw.encode()).hexdigest()[:12]


class SemanticCache:
    """In-memory semantic cache with TTL and similarity-based lookup."""

    def __init__(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ):
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, list[CacheEntry]] = {}  # bucket_key -> entries
        self._total_hits = 0
        self._total_misses = 0

    def lookup(self, query_embedding: list[float], namespace: str = "") -> dict | None:
        """Find a cached result for a semantically similar query."""
        now = time.monotonic()
        bucket_key = _embedding_key(query_embedding, namespace)

        entries = self._entries.get(bucket_key, [])
        for entry in entries:
            # Check TTL
            if now - entry.created_at > self.ttl_seconds:
                continue
            # Check similarity
            sim = _cosine_similarity(query_embedding, entry.embedding)
            if sim >= self.similarity_threshold:
                entry.hit_count += 1
                self._total_hits += 1
                logger.info(
                    f"Semantic cache HIT (sim={sim:.3f}, hits={entry.hit_count})"
                )
                return entry.result

        self._total_misses += 1
        return None

    def store(self, query_embedding: list[float], result: dict, namespace: str = "") -> None:
        """Cache a retrieval result."""
        bucket_key = _embedding_key(query_embedding, namespace)
        entry = CacheEntry(embedding=query_embedding, result=result)

        if bucket_key not in self._entries:
            self._entries[bucket_key] = []

        self._entries[bucket_key].append(entry)

        # Evict oldest if over capacity
        total = sum(len(v) for v in self._entries.values())
        if total > self.max_entries:
            self._evict_oldest()

        logger.debug(f"Semantic cache STORE (total entries={total})")

    def _evict_oldest(self) -> None:
        """Remove the oldest entry across all buckets."""
        oldest_key = None
        oldest_time = float("inf")
        for key, entries in self._entries.items():
            if entries and entries[0].created_at < oldest_time:
                oldest_time = entries[0].created_at
                oldest_key = key
        if oldest_key and self._entries[oldest_key]:
            self._entries[oldest_key].pop(0)
            if not self._entries[oldest_key]:
                del self._entries[oldest_key]

    def clear(self) -> None:
        self._entries.clear()
        self._total_hits = 0
        self._total_misses = 0

    def invalidate_by_document(self, document_id: str) -> int:
        """Phase 5.1: Invalidate all cached entries that reference a specific document.

        When a document is re-ingested, cached query results that included
        chunks from the old version must be purged to avoid stale answers.

        Returns:
            Number of entries invalidated.
        """
        invalidated = 0
        empty_buckets = []

        for bucket_key, entries in self._entries.items():
            surviving = []
            for entry in entries:
                # Check if any source in the cached result references this document
                sources = entry.result.get("sources", [])
                has_doc = any(
                    s.get("document_id") == document_id
                    for s in sources
                )
                if has_doc:
                    invalidated += 1
                else:
                    surviving.append(entry)
            self._entries[bucket_key] = surviving
            if not surviving:
                empty_buckets.append(bucket_key)

        # Clean up empty buckets
        for key in empty_buckets:
            del self._entries[key]

        if invalidated:
            logger.info(
                "Semantic cache: invalidated %d entries for document %s",
                invalidated, document_id,
            )
        return invalidated

    @property
    def stats(self) -> dict:
        total_entries = sum(len(v) for v in self._entries.values())
        return {
            "entries": total_entries,
            "hits": self._total_hits,
            "misses": self._total_misses,
            "hit_rate": (
                self._total_hits / (self._total_hits + self._total_misses)
                if (self._total_hits + self._total_misses) > 0
                else 0
            ),
        }


# Global cache instance
_cache: SemanticCache | None = None


def get_semantic_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache


def clear_semantic_cache(reason: str | None = None) -> None:
    cache = get_semantic_cache()
    cache.clear()
    logger.info("Semantic cache cleared%s", f": {reason}" if reason else "")


def invalidate_cache_for_document(document_id: str) -> int:
    """Phase 5.1: Invalidate cached entries that reference a specific document.

    Call this when a document is re-ingested to ensure stale results
    are not served from cache.
    """
    cache = get_semantic_cache()
    return cache.invalidate_by_document(document_id)
