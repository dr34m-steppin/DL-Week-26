from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
from openai import OpenAI
from pypdf import PdfReader


def extract_pdf_text(pdf_path: str | Path) -> str:
    pdf_path = Path(pdf_path)
    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> List[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        chunks.append(chunk)
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


@dataclass
class RetrievalChunk:
    text: str
    score: float


class LocalRAGStore:
    def __init__(self, chunks: List[str], embeddings: np.ndarray):
        self.chunks = chunks
        self.embeddings = embeddings
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        self.normed = self.embeddings / np.clip(norms, 1e-10, None)

    @classmethod
    def from_texts(
        cls,
        texts: List[str],
        openai_api_key: str,
        embedding_model: str = "text-embedding-3-small",
    ) -> "LocalRAGStore":
        client = OpenAI(api_key=openai_api_key)
        embeddings = []
        for text in texts:
            emb = client.embeddings.create(model=embedding_model, input=text)
            embeddings.append(emb.data[0].embedding)
        matrix = np.array(embeddings, dtype=np.float32)
        return cls(chunks=texts, embeddings=matrix)

    @classmethod
    def from_pdfs(
        cls,
        pdf_paths: List[str | Path],
        openai_api_key: str,
        embedding_model: str = "text-embedding-3-small",
    ) -> "LocalRAGStore":
        all_chunks: List[str] = []
        for pdf in pdf_paths:
            text = extract_pdf_text(pdf)
            all_chunks.extend(chunk_text(text))
        if not all_chunks:
            raise ValueError("No text chunks found in provided PDF files.")
        return cls.from_texts(all_chunks, openai_api_key=openai_api_key, embedding_model=embedding_model)

    def query(
        self, query_text: str, openai_api_key: str, top_k: int = 3, embedding_model: str = "text-embedding-3-small"
    ) -> List[RetrievalChunk]:
        client = OpenAI(api_key=openai_api_key)
        query_emb = client.embeddings.create(model=embedding_model, input=query_text).data[0].embedding
        q = np.array(query_emb, dtype=np.float32)
        q = q / np.clip(np.linalg.norm(q), 1e-10, None)
        scores = self.normed @ q
        top_idx = np.argsort(scores)[::-1][:top_k]
        return [RetrievalChunk(text=self.chunks[i], score=float(scores[i])) for i in top_idx]

    def save(self, path: str | Path) -> None:
        path = Path(path)
        payload = {
            "chunks": self.chunks,
            "embeddings": self.embeddings.tolist(),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "LocalRAGStore":
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        chunks = payload["chunks"]
        embeddings = np.array(payload["embeddings"], dtype=np.float32)
        return cls(chunks=chunks, embeddings=embeddings)

