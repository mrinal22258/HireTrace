"""
Deterministic Offline FAISS Retrieval Layer for HireTrace.

Ensures 100% offline, local, zero-cost retrieval with stable, reproducible projections:
1. Deterministic hashed lexical/n-gram retrieval projection (384-dimensional dense vectors).
2. Source-isolated FAISS indices (cv, interview, assessment, project, jd) preventing evidence starvation.
3. Cosine-similarity top-k matching with exact citation mapping and confidence scores.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import re
import hashlib
from agents.evidence_loader import EvidenceSpan

try:
    import faiss
    _HAS_FAISS = True
except ImportError:
    faiss = None
    _HAS_FAISS = False


class _NumpyFlatIPIndex:
    """NumPy-based exact inner-product index fallback matching faiss.IndexFlatIP."""
    def __init__(self, d: int):
        self.d = d
        self.vectors = np.empty((0, d), dtype=np.float32)

    def add(self, x: np.ndarray):
        x = np.asarray(x, dtype=np.float32)
        if len(self.vectors) == 0:
            self.vectors = x
        else:
            self.vectors = np.vstack([self.vectors, x])

    def search(self, q: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        q = np.asarray(q, dtype=np.float32)
        if len(self.vectors) == 0:
            return np.empty((q.shape[0], 0), dtype=np.float32), np.empty((q.shape[0], 0), dtype=np.int64)
        sims = np.matmul(q, self.vectors.T)
        k = min(k, self.vectors.shape[0])
        top_indices = np.argsort(-sims, axis=1)[:, :k]
        top_scores = np.take_along_axis(sims, top_indices, axis=1)
        return top_scores, top_indices


def _create_flat_ip_index(d: int):
    """Creates a FAISS IndexFlatIP if available, else exact NumPy inner-product index."""
    if _HAS_FAISS and faiss is not None:
        return faiss.IndexFlatIP(d)
    return _NumpyFlatIPIndex(d)



def _stable_hash(token: str, seed: int = 0) -> int:
    """Stable, cross-process deterministic hash using SHA-256."""
    raw = f"{seed}:{token}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "little")


class EmbeddingModel:
    """
    Guaranteed offline, deterministic embedding projector.
    Maps token frequencies and n-grams into normalized 384-dimensional dense vectors
    using stable SHA-256 byte hashing, ensuring identical representations across runs.
    """
    def __init__(self, embedding_dim: int = 384):
        self._embedding_dim = embedding_dim

    def _embed_single(self, text: str) -> np.ndarray:
        vec = np.zeros(self._embedding_dim, dtype=np.float32)
        words = re.findall(r"\b\w+\b", text.lower())
        if not words:
            vec[0] = 1.0
            return vec

        # 1. Unigram frequency with position discounting
        for i, w in enumerate(words):
            h1 = _stable_hash(w, seed=1) % self._embedding_dim
            weight = 1.0 / (1.0 + float(i * 0.04))
            vec[h1] += float(weight)

        # 2. Bigrams for phrases (e.g. "apache kafka", "exactly once")
        for i in range(len(words) - 1):
            bg = f"{words[i]}_{words[i+1]}"
            h2 = _stable_hash(bg, seed=2) % self._embedding_dim
            vec[h2] += 1.5

        # 3. Character trigrams for morphological robustness
        clean_text = re.sub(r"\s+", " ", text.lower())
        for i in range(len(clean_text) - 2):
            tg = clean_text[i:i+3]
            h3 = _stable_hash(tg, seed=3) % self._embedding_dim
            vec[h3] += 0.35

        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        return vec

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        vecs = [self._embed_single(t) for t in texts]
        arr = np.stack(vecs).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return arr / norms


@dataclass
class RetrievedSpan:
    """An evidence span retrieved for a specific requirement query."""
    span: EvidenceSpan
    similarity_score: float

    def to_dict(self) -> Dict[str, Any]:
        d = self.span.to_dict()
        d["similarity_score"] = round(self.similarity_score, 3)
        return d


class EvidenceRetriever:
    """
    Multi-source isolated FAISS index manager.
    Maintains separate indices for CV, Interview, Assessment, Project, and JD
    to ensure balanced cross-source evidence retrieval without CV dominance.
    """

    KNOWN_SOURCES = ("cv", "interview", "assessment", "project", "jd")

    def __init__(self, spans: List[EvidenceSpan], embedding_model: Optional[EmbeddingModel] = None):
        self.spans = spans
        self.embedder = embedding_model or EmbeddingModel()
        
        # Source-isolated span containers and indices
        self.spans_by_source: Dict[str, List[EvidenceSpan]] = {s: [] for s in self.KNOWN_SOURCES}
        self.indices_by_source: Dict[str, Any] = {s: None for s in self.KNOWN_SOURCES}
        
        # Global fallback index across all spans
        self.global_index: Any = None
        self._build_indices()

    def _build_indices(self):
        if not self.spans:
            return

        # 1. Populate source buckets
        for span in self.spans:
            doc_type = span.document_type.lower()
            if doc_type in self.spans_by_source:
                self.spans_by_source[doc_type].append(span)
            else:
                self.spans_by_source.setdefault(doc_type, []).append(span)

        # 2. Build isolated FAISS index for each document source
        for doc_type, source_spans in self.spans_by_source.items():
            if source_spans:
                texts = [f"[{s.document_type.upper()}: {s.section}] {s.text}" for s in source_spans]
                embeddings = self.embedder.embed_texts(texts)
                dim = embeddings.shape[1]
                idx = _create_flat_ip_index(dim)
                idx.add(embeddings)
                self.indices_by_source[doc_type] = idx

        # 3. Build global index
        all_texts = [f"[{s.document_type.upper()}: {s.section}] {s.text}" for s in self.spans]
        all_embeddings = self.embedder.embed_texts(all_texts)
        self.global_index = _create_flat_ip_index(all_embeddings.shape[1])
        self.global_index.add(all_embeddings)

    def retrieve(self, query: str, top_k: int = 4, filter_doc_type: Optional[str] = None) -> List[RetrievedSpan]:
        """Retrieves top-k spans, searching the source-isolated index directly if filter_doc_type is specified."""
        if not self.spans:
            return []

        query_vec = self.embedder.embed_texts([query])

        # If a specific doc_type is requested, search its isolated index directly
        if filter_doc_type and filter_doc_type.lower() in self.indices_by_source:
            doc_type = filter_doc_type.lower()
            idx = self.indices_by_source.get(doc_type)
            doc_spans = self.spans_by_source.get(doc_type, [])
            if idx is None or not doc_spans:
                return []

            k = min(top_k, len(doc_spans))
            scores, indices = idx.search(query_vec, k)
            results = []
            for score, i in zip(scores[0], indices[0]):
                if 0 <= i < len(doc_spans):
                    results.append(RetrievedSpan(span=doc_spans[i], similarity_score=float(score)))
            return results

        # Otherwise search global index
        if self.global_index is None:
            return []

        k = min(top_k, len(self.spans))
        scores, indices = self.global_index.search(query_vec, k)
        results = []
        for score, i in zip(scores[0], indices[0]):
            if 0 <= i < len(self.spans):
                results.append(RetrievedSpan(span=self.spans[i], similarity_score=float(score)))
        return results

    def retrieve_per_source(self, query: str, top_k_per_source: int = 2) -> Dict[str, List[RetrievedSpan]]:
        """Retrieves top-k evidence spans independently from each document source."""
        results: Dict[str, List[RetrievedSpan]] = {}
        for source in ("cv", "interview", "assessment", "project", "jd"):
            results[source] = self.retrieve(query, top_k=top_k_per_source, filter_doc_type=source)
        return results
