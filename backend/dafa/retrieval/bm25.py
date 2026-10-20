"""BM25 written out by hand (about 40 lines) so every line can be explained.

Why BM25 and not embeddings for v1: statutes are written in a fixed legal
vocabulary, and users very often quote exact terms or numbers ("420",
"qatl-i-amd", "fundamental rights"). Lexical matching handles that precisely,
runs in milliseconds on Render's free tier with zero extra services, and the
LLM query rewriter maps everyday language onto that vocabulary. The eval
harness measures whether this is good enough.
"""

from __future__ import annotations

import math
from collections import Counter


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(d) for d in docs]
        self.lengths = [len(d) for d in docs]
        self.avg_len = (sum(self.lengths) / len(docs)) if docs else 0.0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(docs)
        # Smoothed IDF: rare terms count for more, and the +1 keeps it positive.
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: list[str], i: int) -> float:
        doc, dl = self.docs[i], self.lengths[i]
        s = 0.0
        for t in set(query):
            tf = doc.get(t, 0)
            if not tf:
                continue
            norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avg_len))
            s += self.idf.get(t, 0.0) * norm * query.count(t) ** 0.5
        return s

    def top(self, query: list[str], k: int, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        idxs = allowed if allowed is not None else range(len(self.docs))
        scored = [(i, self.score(query, i)) for i in idxs]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]
