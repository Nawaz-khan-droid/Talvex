"""
TALVEX Vector Search Service

Provides FAISS-based vector similarity search on job descriptions and applications.

Two backends are available:

- **SemanticVectorSearch** (default): Uses sentence-transformers ``all-MiniLM-L6-v2``
  to produce dense 384-dim embeddings.  Much higher search quality for natural
  language queries.  Falls back to :class:`LegacyVectorSearch` when the
  ``sentence_transformers`` package is not importable.

- **LegacyVectorSearch**: Original character n-gram hashing (256 dimensions).
  Lightweight, no heavy ML models, but not semantically aware.

The module-level singleton ``vector_search_service`` is an instance of whichever
backend is available (semantic preferred).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import faiss
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Utility: check whether sentence-transformers is importable
# ---------------------------------------------------------------------------

def _is_sentence_transformers_available() -> bool:
    """Return ``True`` if ``sentence_transformers`` can be imported."""
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


# ===================================================================
# LegacyVectorSearch — character n-gram hashing (original approach)
# ===================================================================

class LegacyVectorSearch:
    """FAISS vector search backed by character n-gram hashing.

    Kept for backward compatibility and as a fallback when
    ``sentence_transformers`` is not installed.
    """

    def __init__(self, index_path: str = "/home/z/my-project/db/faiss_index") -> None:
        self.index_path = Path(index_path)
        self.dimension = 256
        self.index: faiss.Index | None = None
        self.id_map: dict[str, str] = {}
        self._doc_metadata: dict[str, dict[str, Any]] = {}
        self._load_or_create_index()

    # -- I/O ----------------------------------------------------------

    def _load_or_create_index(self) -> None:
        """Load existing FAISS index or create a new one."""
        try:
            idx_file = self.index_path / "index.faiss"
            if idx_file.exists():
                self.index = faiss.read_index(str(idx_file))
                with open(self.index_path / "id_map.json") as fh:
                    self.id_map = json.load(fh)
                meta_path = self.index_path / "metadata.json"
                if meta_path.exists():
                    with open(meta_path) as fh:
                        self._doc_metadata = json.load(fh)
                logger.info(
                    "Loaded legacy FAISS index with %d vectors from %s",
                    self.index.ntotal,
                    self.index_path,
                )
            else:
                self.index = faiss.IndexFlatL2(self.dimension)
                self.index_path.mkdir(parents=True, exist_ok=True)
                logger.info("Created new legacy FAISS index")
        except Exception as exc:
            logger.error("Error loading legacy FAISS index: %s. Creating new.", exc)
            self.index = faiss.IndexFlatL2(self.dimension)
            self.index_path.mkdir(parents=True, exist_ok=True)

    def _save_index(self) -> None:
        """Persist FAISS index, ID map, and metadata to disk."""
        try:
            self.index_path.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(self.index_path / "index.faiss"))
            with open(self.index_path / "id_map.json", "w") as fh:
                json.dump(self.id_map, fh)
            with open(self.index_path / "metadata.json", "w") as fh:
                json.dump(self._doc_metadata, fh)
        except Exception as exc:
            logger.error("Error saving legacy FAISS index: %s", exc)

    # -- Embedding -----------------------------------------------------

    def _text_to_vector(self, text: str) -> np.ndarray:
        """Convert *text* to a 256-dim vector via character n-gram hashing."""
        vector = np.zeros(self.dimension, dtype=np.float32)
        text_lower = text.lower()

        # Character trigram hashing
        for i in range(len(text_lower) - 2):
            trigram = text_lower[i : i + 3]
            h = hash(trigram) % self.dimension
            vector[h] += 1.0

        # Character bigram hashing (weighted)
        for i in range(len(text_lower) - 1):
            bigram = text_lower[i : i + 2]
            h = hash(bigram) % self.dimension
            vector[h] += 0.5

        # Word-level hashing (weighted higher for meaningful terms)
        words = text_lower.split()
        meaningful_words = [w for w in words if len(w) > 3]
        for word in meaningful_words:
            h = hash(word) % self.dimension
            vector[h] += 2.0
            idx = words.index(word) if word in words else -1
            if 0 < idx < len(words) - 1:
                pair = f"{words[idx - 1]}_{word}"
                h2 = hash(pair) % self.dimension
                vector[h2] += 1.5

        # L2-normalize
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm

        return vector

    # -- CRUD ----------------------------------------------------------

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Add a single document. Returns the internal FAISS index ID."""
        if not text.strip():
            logger.warning("Empty text for document %s, skipping.", doc_id)
            return -1

        vector = self._text_to_vector(text).reshape(1, -1)
        idx = self.index.ntotal
        self.index.add(vector)
        self.id_map[str(idx)] = doc_id
        if metadata:
            self._doc_metadata[doc_id] = metadata
        self._save_index()
        logger.debug("Added document %s at index %d", doc_id, idx)
        return idx

    def add_documents_batch(self, documents: list[dict[str, Any]]) -> int:
        """Add multiple documents in batch. Returns count added."""
        if not documents:
            return 0

        vectors: list[np.ndarray] = []
        for doc in documents:
            text = doc.get("text", "")
            if text.strip():
                vectors.append(self._text_to_vector(text).reshape(1, -1))
                self._doc_metadata[doc["id"]] = doc.get("metadata", {})

        if not vectors:
            return 0

        batch_vectors = np.vstack(vectors)
        start_idx = self.index.ntotal
        self.index.add(batch_vectors)

        for i, doc in enumerate(documents):
            self.id_map[str(start_idx + i)] = doc["id"]

        self._save_index()
        logger.info("Batch added %d documents to legacy FAISS index", len(documents))
        return len(documents)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents. Returns list of ``{id, score, metadata}``."""
        if self.index.ntotal == 0 or not query.strip():
            return []

        query_vector = self._text_to_vector(query).reshape(1, -1)
        actual_k = min(top_k, self.index.ntotal)
        distances, indices = self.index.search(query_vector, actual_k)

        results: list[dict[str, Any]] = []
        for dist, idx_val in zip(distances[0], indices[0]):
            doc_id = self.id_map.get(str(int(idx_val)))
            if not doc_id:
                continue

            similarity = max(0.0, min(100.0, 100.0 - float(dist) * 10))
            result: dict[str, Any] = {"id": doc_id, "score": round(similarity, 1)}

            if doc_id in self._doc_metadata:
                result["metadata"] = self._doc_metadata[doc_id]

            if filter_metadata:
                meta = result.get("metadata", {})
                if not all(meta.get(k) == v for k, v in filter_metadata.items()):
                    continue

            results.append(result)
        return results

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document by rebuilding the index."""
        if (
            doc_id not in self._doc_metadata
            and doc_id not in self.id_map.values()
        ):
            return False

        ids_to_remove = {
            k for k, v in self.id_map.items() if v == doc_id
        }
        if not ids_to_remove:
            return False

        for k in ids_to_remove:
            del self.id_map[k]
        self._doc_metadata.pop(doc_id, None)
        self._rebuild_index()
        return True

    def _rebuild_index(self) -> None:
        """Rebuild the FAISS index from stored metadata texts."""
        self.index = faiss.IndexFlatL2(self.dimension)
        for doc_id, metadata in self._doc_metadata.items():
            text = metadata.get("text", "")
            if text:
                vector = self._text_to_vector(text).reshape(1, -1)
                idx = self.index.ntotal
                self.index.add(vector)
                old_idx = next(
                    (k for k, v in self.id_map.items() if v == doc_id), None
                )
                if old_idx:
                    del self.id_map[old_idx]
                self.id_map[str(idx)] = doc_id
        self._save_index()

    def get_index_stats(self) -> dict[str, Any]:
        """Return statistics about the FAISS index."""
        return {
            "totalDocuments": self.index.ntotal if self.index else 0,
            "dimension": self.dimension,
            "indexType": "IndexFlatL2",
            "backend": "legacy_ngram",
            "indexPath": str(self.index_path),
        }


# ===================================================================
# SemanticVectorSearch — sentence-transformers embeddings
# ===================================================================

class SemanticVectorSearch:
    """FAISS vector search backed by sentence-transformer embeddings.

    Uses ``all-MiniLM-L6-v2`` (384 dimensions) for high-quality semantic
    search.  The model is loaded lazily on first use to keep import time
    low and avoid pulling weights unless actually needed.

    Fallback behaviour
    ------------------
    If ``sentence_transformers`` cannot be imported at all (package not
    installed), every public method gracefully degrades to the legacy
    n-gram approach via :class:`LegacyVectorSearch`.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    DIMENSION = 384

    def __init__(self, index_path: str = "/home/z/my-project/db/faiss_semantic_index") -> None:
        self.index_path = Path(index_path)
        self.dimension = self.DIMENSION
        self.index: faiss.Index | None = None
        self.id_map: dict[str, str] = {}
        self._doc_metadata: dict[str, dict[str, Any]] = {}
        self._doc_texts: dict[str, str] = {}  # raw text cache for rebuilds

        # Lazy-loaded model — set on first call that needs embeddings
        self._model: Any | None = None
        self._model_failed: bool = False

        # Fallback engine used when sentence-transformers is unavailable
        self._fallback: LegacyVectorSearch | None = None

        self._load_or_create_index()

    # -- Model loading (lazy) ------------------------------------------

    @property
    def _backend(self) -> LegacyVectorSearch:
        """Return the fallback engine, creating it on first access."""
        if self._fallback is None:
            self._fallback = LegacyVectorSearch(
                index_path="/home/z/my-project/db/faiss_index"
            )
        return self._fallback

    @property
    def using_semantic(self) -> bool:
        """``True`` if the semantic model is actively being used."""
        return self._model is not None and not self._model_failed

    def _get_model(self) -> Any:
        """Lazily load the sentence-transformer model.

        Returns the model instance, or ``None`` if loading fails.
        """
        if self._model is not None:
            return self._model
        if self._model_failed:
            return None

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "Loading sentence-transformer model '%s' (first time may download weights)...",
                self.MODEL_NAME,
            )
            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("Model '%s' loaded successfully.", self.MODEL_NAME)
            return self._model
        except Exception as exc:
            logger.warning(
                "Failed to load sentence-transformer model: %s. "
                "Falling back to legacy n-gram search.",
                exc,
            )
            self._model_failed = True
            return None

    # -- I/O ----------------------------------------------------------

    def _load_or_create_index(self) -> None:
        """Load existing semantic FAISS index or create a new one."""
        try:
            idx_file = self.index_path / "index.faiss"
            if idx_file.exists():
                self.index = faiss.read_index(str(idx_file))
                with open(self.index_path / "id_map.json") as fh:
                    self.id_map = json.load(fh)
                meta_path = self.index_path / "metadata.json"
                if meta_path.exists():
                    with open(meta_path) as fh:
                        self._doc_metadata = json.load(fh)
                texts_path = self.index_path / "doc_texts.json"
                if texts_path.exists():
                    with open(texts_path) as fh:
                        self._doc_texts = json.load(fh)
                logger.info(
                    "Loaded semantic FAISS index with %d vectors from %s",
                    self.index.ntotal,
                    self.index_path,
                )
            else:
                self.index = faiss.IndexFlatL2(self.dimension)
                self.index_path.mkdir(parents=True, exist_ok=True)
                logger.info("Created new semantic FAISS index")

            # Migrate old index if no semantic index existed yet
            self._migrate_if_needed()
        except Exception as exc:
            logger.error("Error loading semantic FAISS index: %s. Creating new.", exc)
            self.index = faiss.IndexFlatL2(self.dimension)
            self.index_path.mkdir(parents=True, exist_ok=True)

    def _migrate_if_needed(self) -> None:
        """Gracefully migrate the legacy n-gram index on first semantic run.

        Only copies metadata references — the old index stays intact so the
        legacy path still works.
        """
        if self.index.ntotal > 0:
            return  # Already have a semantic index

        legacy_dir = Path("/home/z/my-project/db/faiss_index")
        meta_file = legacy_dir / "metadata.json"
        if not meta_file.exists():
            return

        try:
            with open(meta_file) as fh:
                legacy_meta = json.load(fh)
            if not legacy_meta:
                return

            logger.info(
                "Migrating %d documents from legacy index to semantic index.",
                len(legacy_meta),
            )
            # Re-index each document using semantic embeddings
            documents = []
            for doc_id, meta in legacy_meta.items():
                text = meta.get("text", "")
                if text.strip():
                    documents.append({
                        "id": doc_id,
                        "text": text,
                        "metadata": meta,
                    })
            if documents:
                self.add_documents_batch(documents)
                logger.info(
                    "Migration complete: %d documents re-indexed semantically.",
                    len(documents),
                )
        except Exception as exc:
            logger.warning("Legacy index migration failed (non-fatal): %s", exc)

    def _save_index(self) -> None:
        """Persist FAISS index, ID map, metadata, and raw texts to disk."""
        try:
            self.index_path.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(self.index_path / "index.faiss"))
            with open(self.index_path / "id_map.json", "w") as fh:
                json.dump(self.id_map, fh)
            with open(self.index_path / "metadata.json", "w") as fh:
                json.dump(self._doc_metadata, fh)
            with open(self.index_path / "doc_texts.json", "w") as fh:
                json.dump(self._doc_texts, fh)
        except Exception as exc:
            logger.error("Error saving semantic FAISS index: %s", exc)

    # -- Embedding -----------------------------------------------------

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Encode *texts* into normalized embedding vectors.

        Falls back to the legacy n-gram encoder if the model is unavailable.
        """
        model = self._get_model()
        if model is not None:
            embeddings = model.encode(texts, normalize_embeddings=True)
            return np.array(embeddings, dtype=np.float32)

        # Fallback: use legacy n-gram encoder
        logger.debug("Using legacy n-gram encoder for %d text(s).", len(texts))
        vectors = np.vstack(
            [self._backend._text_to_vector(t).reshape(1, -1) for t in texts]
        )
        return vectors

    # -- CRUD ----------------------------------------------------------

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Add a single document. Returns the internal FAISS index ID."""
        if not text.strip():
            logger.warning("Empty text for document %s, skipping.", doc_id)
            return -1

        vector = self._embed([text])  # shape: (1, dim)
        idx = self.index.ntotal
        self.index.add(vector)
        self.id_map[str(idx)] = doc_id
        self._doc_texts[doc_id] = text

        if metadata:
            self._doc_metadata[doc_id] = metadata

        self._save_index()
        logger.debug("Added document %s at index %d", doc_id, idx)
        return idx

    def add_documents_batch(self, documents: list[dict[str, Any]]) -> int:
        """Add multiple documents in batch. Returns count added."""
        if not documents:
            return 0

        valid_docs = [d for d in documents if d.get("text", "").strip()]
        if not valid_docs:
            return 0

        texts = [d["text"] for d in valid_docs]
        vectors = self._embed(texts)  # shape: (N, dim)
        start_idx = self.index.ntotal
        self.index.add(vectors)

        for i, doc in enumerate(valid_docs):
            self.id_map[str(start_idx + i)] = doc["id"]
            self._doc_texts[doc["id"]] = doc["text"]
            self._doc_metadata[doc["id"]] = doc.get("metadata", {})

        self._save_index()
        logger.info(
            "Batch added %d documents to semantic FAISS index.", len(valid_docs)
        )
        return len(valid_docs)

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for semantically similar documents.

        Returns a list of ``{id, score, text, metadata}`` dicts, ordered by
        descending relevance.  *score* is in ``[0, 100]``.
        """
        if self.index.ntotal == 0 or not query.strip():
            return []

        query_vector = self._embed([query])  # shape: (1, dim)
        actual_k = min(top_k, self.index.ntotal)
        distances, indices = self.index.search(query_vector, actual_k)

        results: list[dict[str, Any]] = []
        for dist, idx_val in zip(distances[0], indices[0]):
            doc_id = self.id_map.get(str(int(idx_val)))
            if not doc_id:
                continue

            # For cosine-similarity–style scores, convert L2 distance.
            # With normalized embeddings: cosine_sim = 1 - dist²/2
            # Map to a 0–100 percentage for API consistency.
            if self.using_semantic:
                cosine_sim = 1.0 - float(dist) ** 2 / 2.0
                similarity = max(0.0, min(100.0, cosine_sim * 100))
            else:
                similarity = max(0.0, min(100.0, 100.0 - float(dist) * 10))

            result: dict[str, Any] = {
                "id": doc_id,
                "score": round(similarity, 1),
            }

            # Attach original text snippet if available
            doc_text = self._doc_texts.get(doc_id, "")
            if doc_text:
                result["text"] = doc_text[:500]  # Truncate for API response

            if doc_id in self._doc_metadata:
                result["metadata"] = self._doc_metadata[doc_id]

            # Apply optional metadata filter
            if filter_metadata:
                meta = result.get("metadata", {})
                if not all(meta.get(k) == v for k, v in filter_metadata.items()):
                    continue

            results.append(result)

        return results

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document by rebuilding the index from cached texts."""
        if (
            doc_id not in self._doc_metadata
            and doc_id not in self._doc_texts
        ):
            return False

        self._doc_metadata.pop(doc_id, None)
        self._doc_texts.pop(doc_id, None)
        self._rebuild_from_texts()
        return True

    def _rebuild_from_texts(self) -> None:
        """Rebuild the entire FAISS index from cached raw texts."""
        self.index = faiss.IndexFlatL2(self.dimension)
        self.id_map.clear()

        if not self._doc_texts:
            self._save_index()
            return

        doc_ids = list(self._doc_texts.keys())
        texts = [self._doc_texts[did] for did in doc_ids]
        vectors = self._embed(texts)

        self.index.add(vectors)
        for i, did in enumerate(doc_ids):
            self.id_map[str(i)] = did

        self._save_index()
        logger.info(
            "Rebuilt semantic index with %d documents from cached texts.",
            len(doc_ids),
        )

    def reindex_all(self, applications: list[dict[str, Any]]) -> int:
        """Rebuild the semantic index from a list of application dicts.

        Each *application* dict should contain:
        - ``id``: unique identifier
        - ``roleTitle``: job role title
        - ``jobDescription``: full job description text
        - ``extractedKeywords``: JSON-encoded list of keyword strings (optional)
        - Additional fields (company, location, workMode, etc.) used as metadata

        Returns the number of documents re-indexed.
        """
        logger.info(
            "Starting full reindex of %d applications into semantic FAISS index.",
            len(applications),
        )

        # Clear current state
        self.index = faiss.IndexFlatL2(self.dimension)
        self.id_map.clear()
        self._doc_metadata.clear()
        self._doc_texts.clear()

        documents: list[dict[str, Any]] = []
        for app in applications:
            # Combine role + description + keywords into a single embedding text
            text_parts = [app.get("roleTitle", ""), app.get("jobDescription", "")]
            keywords_raw = app.get("extractedKeywords")
            if keywords_raw:
                try:
                    keywords = json.loads(keywords_raw)
                    if isinstance(keywords, list):
                        text_parts.append(" ".join(keywords))
                except (json.JSONDecodeError, TypeError):
                    pass
            text = " ".join(p for p in text_parts if p)

            documents.append({
                "id": app["id"],
                "text": text,
                "metadata": {
                    "text": text,
                    "company": app.get("company"),
                    "role": app.get("roleTitle"),
                    "status": app.get("status"),
                    "platform": app.get("platform"),
                },
            })

        added = self.add_documents_batch(documents)
        logger.info("Reindex complete: %d documents indexed.", added)
        return added

    def get_index_stats(self) -> dict[str, Any]:
        """Return statistics about the FAISS index."""
        return {
            "totalDocuments": self.index.ntotal if self.index else 0,
            "dimension": self.dimension,
            "indexType": "IndexFlatL2",
            "backend": "semantic" if self.using_semantic else "legacy_ngram_fallback",
            "model": self.MODEL_NAME if self.using_semantic else None,
            "indexPath": str(self.index_path),
        }


# ===================================================================
# Module-level singleton
# ===================================================================

if _is_sentence_transformers_available():
    vector_search_service = SemanticVectorSearch()
    logger.info("Using SemanticVectorSearch (sentence-transformers) as default.")
else:
    vector_search_service = LegacyVectorSearch()
    logger.info("sentence-transformers not available; using LegacyVectorSearch.")
