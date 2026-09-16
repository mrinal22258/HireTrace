"""
High-Performance FAISS Retrieval Layer with Real Semantic Embeddings & Persistent Caching.

Features:
1. Multi-backend embeddings:
   - Sentence-Transformers (offline dense neural embeddings)
   - Ollama embeddings (nomic-embed-text / all-minilm via local daemon)
   - Hashed lexical n-gram projection (guaranteed 100% offline zero-download fallback)
2. Integrated multi-tier embedding cache with persistent disk backing.
3. Source-isolated FAISS indices (cv, interview, assessment, project, jd) preventing evidence starvation.
4. Batch-embedding across candidates for efficient bulk ingestion.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional
import os
import re
import hashlib
import logging
import numpy as np
import requests

from agents.evidence_loader import EvidenceSpan
from agents.embedding_cache import EMBEDDING_CACHE

logger = logging.getLogger("hiretrace.retrieval")

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
    """Stable cross-process deterministic hash using SHA-256."""
    raw = f"{seed}:{token}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:8], "little")


class BaseEmbeddingModel:
    """Abstract base class for embedding models with caching support."""

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        raise NotImplementedError


class HashedLexicalEmbeddingModel(BaseEmbeddingModel):
    """
    Guaranteed offline, deterministic lexical & n-gram embedding projector.
    Zero network calls, zero external model downloads.
    """
    def __init__(self, embedding_dim: int = 384):
        self._embedding_dim = embedding_dim

    def _embed_single(self, text: str) -> np.ndarray:
        vec = np.zeros(self._embedding_dim, dtype=np.float32)
        words = re.findall(r"\b\w+\b", text.lower())
        if not words:
            vec[0] = 1.0
            return vec

        for i, w in enumerate(words):
            h1 = _stable_hash(w, seed=1) % self._embedding_dim
            weight = 1.0 / (1.0 + float(i * 0.04))
            vec[h1] += float(weight)

        for i in range(len(words) - 1):
            bg = f"{words[i]}_{words[i+1]}"
            h2 = _stable_hash(bg, seed=2) % self._embedding_dim
            vec[h2] += 1.5

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
        cached_map, missing = EMBEDDING_CACHE.get_batch(texts)
        results = [None] * len(texts)

        for idx, vec in cached_map.items():
            results[idx] = vec

        new_entries = []
        for idx, text in missing:
            vec = self._embed_single(text)
            results[idx] = vec
            new_entries.append((text, vec))

        if new_entries:
            EMBEDDING_CACHE.set_batch(new_entries)

        arr = np.stack(results).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return arr / norms


class OllamaEmbeddingModel(BaseEmbeddingModel):
    """Ollama local embedding endpoint (e.g. nomic-embed-text)."""

    def __init__(self, base_url: Optional[str] = None, model: str = "nomic-embed-text"):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = os.getenv("OLLAMA_EMBED_MODEL", model)
        self.fallback = HashedLexicalEmbeddingModel()

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        cached_map, missing = EMBEDDING_CACHE.get_batch(texts)
        results = [None] * len(texts)

        for idx, vec in cached_map.items():
            results[idx] = vec

        new_entries = []
        for idx, text in missing:
            try:
                res = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=10.0
                )
                if res.status_code == 200:
                    vec = np.array(res.json().get("embedding", []), dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec /= norm
                else:
                    vec = self.fallback._embed_single(text)
            except Exception:
                vec = self.fallback._embed_single(text)

            results[idx] = vec
            new_entries.append((text, vec))

        if new_entries:
            EMBEDDING_CACHE.set_batch(new_entries)

        arr = np.stack(results).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return arr / norms


class SentenceTransformerEmbeddingModel(BaseEmbeddingModel):
    """Sentence-Transformers neural embeddings runnable on CPU."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = os.getenv("EMBEDDING_MODEL_NAME", model_name)
        self.fallback = HashedLexicalEmbeddingModel()
        self._model = None
        self._init_failed = False

    def _get_model(self):
        if self._model is None and not self._init_failed:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.warning(f"Failed to load sentence_transformers ({e}); using HashedLexical fallback.")
                self._init_failed = True
        return self._model

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        model = self._get_model()
        if model is None:
            return self.fallback.embed_texts(texts)

        cached_map, missing = EMBEDDING_CACHE.get_batch(texts)
        results = [None] * len(texts)

        for idx, vec in cached_map.items():
            results[idx] = vec

        if missing:
            missing_texts = [m[1] for m in missing]
            try:
                computed = model.encode(missing_texts, normalize_embeddings=True, convert_to_numpy=True)
                new_entries = []
                for (orig_idx, orig_text), vec in zip(missing, computed):
                    results[orig_idx] = vec
                    new_entries.append((orig_text, vec))
                EMBEDDING_CACHE.set_batch(new_entries)
            except Exception as e:
                logger.warning(f"sentence_transformers encode failed ({e}); using hashed fallback.")
                fallback_vecs = self.fallback.embed_texts(missing_texts)
                for (orig_idx, _), vec in zip(missing, fallback_vecs):
                    results[orig_idx] = vec

        arr = np.stack(results).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return arr / norms


class Model2VecEmbeddingModel(BaseEmbeddingModel):
    """Static distilled embeddings: a table lookup, not a transformer forward pass.

    Roughly 100x faster than MiniLM on CPU. Falls back cleanly to HashedLexical if
    model2vec is not installed.
    """

    def __init__(self, model_name: str = "minishlab/potion-base-8M"):
        self.model_name = os.getenv("STATIC_EMBEDDING_MODEL", model_name)
        self.fallback = HashedLexicalEmbeddingModel()
        self._model = None
        self._init_failed = False

    def _ensure(self):
        if self._model is None and not self._init_failed:
            try:
                from model2vec import StaticModel
                self._model = StaticModel.from_pretrained(self.model_name)
            except Exception as e:
                logger.warning(f"Failed to load model2vec ({e}); using HashedLexical fallback.")
                self._init_failed = True
        return self._model

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        model = self._ensure()
        if model is None:
            return self.fallback.embed_texts(texts)

        cached_map, missing = EMBEDDING_CACHE.get_batch(texts)
        results = [None] * len(texts)

        for idx, vec in cached_map.items():
            results[idx] = vec

        if missing:
            missing_texts = [m[1] for m in missing]
            try:
                vectors = model.encode(missing_texts)
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                norms[norms == 0.0] = 1.0
                vectors = (vectors / norms).astype("float32")
                new_entries = []
                for (orig_idx, orig_text), vec in zip(missing, vectors):
                    results[orig_idx] = vec
                    new_entries.append((orig_text, vec))
                EMBEDDING_CACHE.set_batch(new_entries)
            except Exception as e:
                logger.warning(f"model2vec encode failed ({e}); using hashed fallback.")
                fallback_vecs = self.fallback.embed_texts(missing_texts)
                for (orig_idx, _), vec in zip(missing, fallback_vecs):
                    results[orig_idx] = vec

        arr = np.stack(results).astype(np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return arr / norms


# Backwards compatible alias
EmbeddingModel = HashedLexicalEmbeddingModel


def get_default_embedding_model() -> BaseEmbeddingModel:
    """Factory selecting the appropriate embedding model based on configuration."""
    backend = (os.getenv("EMBEDDING_BACKEND") or os.getenv("HIRETRACE_EMBEDDING_BACKEND", "auto")).lower()
    if backend in ("static", "model2vec"):
        return Model2VecEmbeddingModel()
    elif backend == "ollama":
        return OllamaEmbeddingModel()
    elif backend in ("minilm", "sentence_transformers"):
        return SentenceTransformerEmbeddingModel()
    elif backend == "hashed":
        return HashedLexicalEmbeddingModel()

    # In "auto" mode: attempt SentenceTransformer if installed, otherwise fallback to HashedLexical
    try:
        import sentence_transformers
        return SentenceTransformerEmbeddingModel()
    except Exception:
        return HashedLexicalEmbeddingModel()


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
    with per-chunk embedding caching.
    """

    KNOWN_SOURCES = ("cv", "interview", "assessment", "project", "jd")

    def __init__(self, spans: List[EvidenceSpan], embedding_model: Optional[BaseEmbeddingModel] = None):
        self.spans = spans
        self.embedder = embedding_model or get_default_embedding_model()
        
        self.spans_by_source: Dict[str, List[EvidenceSpan]] = {s: [] for s in self.KNOWN_SOURCES}
        self.indices_by_source: Dict[str, Any] = {s: None for s in self.KNOWN_SOURCES}
        self.global_index: Any = None
        self._build_indices()

    def _build_indices(self):
        if not self.spans:
            return

        for span in self.spans:
            doc_type = span.document_type.lower()
            if doc_type in self.spans_by_source:
                self.spans_by_source[doc_type].append(span)
            else:
                self.spans_by_source.setdefault(doc_type, []).append(span)

        for doc_type, source_spans in self.spans_by_source.items():
            if source_spans:
                texts = [f"[{s.document_type.upper()}: {s.section}] {s.text}" for s in source_spans]
                embeddings = self.embedder.embed_texts(texts)
                dim = embeddings.shape[1]
                idx = _create_flat_ip_index(dim)
                idx.add(embeddings)
                self.indices_by_source[doc_type] = idx

        all_texts = [f"[{s.document_type.upper()}: {s.section}] {s.text}" for s in self.spans]
        all_embeddings = self.embedder.embed_texts(all_texts)
        self.global_index = _create_flat_ip_index(all_embeddings.shape[1])
        self.global_index.add(all_embeddings)

        # Trigger on-disk cache persistence
        EMBEDDING_CACHE.save_to_disk()

    def retrieve(self, query: str, top_k: int = 4, filter_doc_type: Optional[str] = None) -> List[RetrievedSpan]:
        if not self.spans:
            return []

        query_vec = self.embedder.embed_texts([query])

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
        results: Dict[str, List[RetrievedSpan]] = {}
        for source in ("cv", "interview", "assessment", "project", "jd"):
            results[source] = self.retrieve(query, top_k=top_k_per_source, filter_doc_type=source)
        return results


def batch_embed_across_candidates(candidates_spans: List[List[EvidenceSpan]], embedder: Optional[BaseEmbeddingModel] = None) -> List[EvidenceRetriever]:
    """
    Builds retrieval indices for multiple candidates in a single batched embedding pass.
    Drastically accelerates bulk candidate ingestion.
    """
    embed = embedder or get_default_embedding_model()
    
    # Collect all unique span texts across all candidates
    all_texts = []
    for spans in candidates_spans:
        for s in spans:
            all_texts.append(f"[{s.document_type.upper()}: {s.section}] {s.text}")

    # Single batched embedding pass
    if all_texts:
        embed.embed_texts(all_texts)
        EMBEDDING_CACHE.save_to_disk()

    # Build individual candidate retrievers using already-cached embeddings
    retrievers = []
    for spans in candidates_spans:
        retrievers.append(EvidenceRetriever(spans, embedding_model=embed))

    return retrievers
