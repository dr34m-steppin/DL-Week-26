import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import List

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "to", "for", "with", "on", "at", "from", "by", "is", "are", "was", "were", "be", "this", "that", "it", "as", "we", "you", "your", "their", "they", "can", "will", "should", "into", "about", "over", "under", "than", "if", "not", "do", "does", "did", "have", "has", "had", "using", "use", "used"
}


def _tokenize(text: str) -> List[str]:
    return [
        token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text.lower())
        if token not in _STOPWORDS and len(token) > 2
    ]


def split_into_chunks(text: str, chunk_size: int = 900, overlap: int = 140) -> List[str]:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunk = cleaned[start:end]
        if end < len(cleaned):
            last_break = max(chunk.rfind("\n"), chunk.rfind(". "))
            if last_break > chunk_size * 0.5:
                end = start + last_break + 1
                chunk = cleaned[start:end]
        chunks.append(chunk.strip())
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return [c for c in chunks if c]


@dataclass
class RetrievedChunk:
    chunk_id: int
    text: str
    score: float


class LexicalRetriever:
    def __init__(self, chunks: List[str]):
        self.chunks = chunks
        self.doc_freq: Counter[str] = Counter()
        self.chunk_term_counts: List[Counter[str]] = []
        self.chunk_norms: List[float] = []
        self._index()

    def _index(self) -> None:
        total_docs = len(self.chunks) or 1
        for chunk in self.chunks:
            term_counts = Counter(_tokenize(chunk))
            self.chunk_term_counts.append(term_counts)
            for term in term_counts:
                self.doc_freq[term] += 1

        for term_counts in self.chunk_term_counts:
            norm = 0.0
            for term, tf in term_counts.items():
                idf = math.log((1 + total_docs) / (1 + self.doc_freq[term])) + 1
                norm += (tf * idf) ** 2
            self.chunk_norms.append(math.sqrt(norm) if norm > 0 else 1.0)

    def search(self, query: str, top_k: int = 3) -> List[RetrievedChunk]:
        q_terms = Counter(_tokenize(query))
        total_docs = len(self.chunks) or 1
        q_norm = 0.0
        weighted_q = {}
        for term, tf in q_terms.items():
            idf = math.log((1 + total_docs) / (1 + self.doc_freq.get(term, 0))) + 1
            weighted_q[term] = tf * idf
            q_norm += weighted_q[term] ** 2

        q_norm = math.sqrt(q_norm) if q_norm > 0 else 1.0

        scores = []
        for idx, term_counts in enumerate(self.chunk_term_counts):
            dot = 0.0
            for term, q_weight in weighted_q.items():
                if term in term_counts:
                    idf = math.log((1 + total_docs) / (1 + self.doc_freq.get(term, 0))) + 1
                    dot += q_weight * (term_counts[term] * idf)
            score = dot / (self.chunk_norms[idx] * q_norm)
            scores.append((idx, score))

        ranked = sorted(scores, key=lambda item: item[1], reverse=True)
        return [
            RetrievedChunk(chunk_id=idx, text=self.chunks[idx], score=score)
            for idx, score in ranked[:top_k]
            if score > 0
        ]
