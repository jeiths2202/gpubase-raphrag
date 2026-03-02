"""Cosine-similarity based deduplication."""
from __future__ import annotations

import logging
from typing import List, Set

import numpy as np

from .config import GenerationConfig
from .models import DPORecord, SFTRecord

logger = logging.getLogger(__name__)


class Deduplicator:
    """Remove near-duplicate records using cosine similarity."""

    def __init__(self, config: GenerationConfig):
        self.config = config
        self.threshold = config.dedup_threshold
        self._encoder = None  # lazy-loaded

    def _get_encoder(self):
        """Lazy-load sentence-transformers model."""
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2"
            )
            logger.info("Loaded sentence-transformers model for dedup")
        return self._encoder

    def deduplicate_sft(self, records: List[SFTRecord]) -> List[SFTRecord]:
        """Remove SFT duplicates by user_text similarity."""
        if len(records) <= 1:
            return records

        texts = [r.user_text for r in records]
        remove_indices = self._find_duplicates(texts, self.threshold)

        result = [r for i, r in enumerate(records) if i not in remove_indices]
        removed = len(records) - len(result)
        logger.info(
            "SFT dedup: %d → %d (removed %d, threshold=%.2f)",
            len(records),
            len(result),
            removed,
            self.threshold,
        )
        return result

    def deduplicate_dpo(self, records: List[DPORecord]) -> List[DPORecord]:
        """Remove DPO duplicates by prompt+chosen combined similarity."""
        if len(records) <= 1:
            return records

        # Use combined prompt+chosen for dedup (prompt-only is too aggressive)
        texts = [f"{r.prompt} ||| {r.chosen[:200]}" for r in records]
        remove_indices = self._find_duplicates(texts, self.threshold)

        result = [r for i, r in enumerate(records) if i not in remove_indices]
        removed = len(records) - len(result)
        logger.info(
            "DPO dedup: %d → %d (removed %d)",
            len(records),
            len(result),
            removed,
        )
        return result

    def _find_duplicates(
        self,
        texts: List[str],
        threshold: float,
    ) -> Set[int]:
        """Return indices to remove (keep first in each dup group)."""
        if len(texts) <= 1:
            return set()

        encoder = self._get_encoder()
        batch_size = self.config.batch_size

        # Encode in batches
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            embeddings = encoder.encode(batch, show_progress_bar=False)
            all_embeddings.append(embeddings)

        embeddings_matrix = np.vstack(all_embeddings)

        # Compute cosine similarity in batches to manage memory
        remove: Set[int] = set()
        n = len(texts)

        # Process in blocks for large datasets
        block_size = min(batch_size, n)
        for i in range(0, n, block_size):
            i_end = min(i + block_size, n)
            block_a = embeddings_matrix[i:i_end]

            for j in range(i, n, block_size):
                j_end = min(j + block_size, n)
                block_b = embeddings_matrix[j:j_end]

                sim = _cosine_similarity_matrix(block_a, block_b)

                for bi in range(sim.shape[0]):
                    global_i = i + bi
                    if global_i in remove:
                        continue
                    for bj in range(sim.shape[1]):
                        global_j = j + bj
                        if global_i >= global_j:
                            continue
                        if global_j in remove:
                            continue
                        if sim[bi, bj] >= threshold:
                            remove.add(global_j)

        return remove


def _cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute pairwise cosine similarity matrix."""
    # Normalize
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return a_norm @ b_norm.T
