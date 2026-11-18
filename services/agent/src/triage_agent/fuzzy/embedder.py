"""Local 1536-d feature hashing. No network and no model provider.

pgvector stores ``vector(1536)``. This embedder fills that width so CI can
seed and search the corpus without calling an embedding API. A later
deployment can inject a different callable with the same signature.
"""

from __future__ import annotations

import hashlib
import math
import re

EMBEDDING_DIM = 1536


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    bigrams = [f"{left}_{right}" for left, right in zip(words, words[1:], strict=False)]
    return words + bigrams


class HashingEmbedder:
    """Signed feature hashing, L2-normalised so pgvector cosine distance works."""

    dim = EMBEDDING_DIM

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        found = tokens(text)
        if not found:
            vector[0] = 1.0
            return vector
        for token in found:
            digest = hashlib.sha256(token.encode()).digest()
            bucket = int.from_bytes(digest[:2], "big") % self.dim
            sign = 1.0 if digest[2] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector]
