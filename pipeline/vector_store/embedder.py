"""
embedder.py — Text Embedding Generation

Priority chain (first available wins):
  1. OpenAI  text-embedding-3-small  (1536 dims) — needs OPENAI_API_KEY
  2. Google  embedding-001           (768 dims)  — needs GOOGLE_API_KEY
  3. ChromaDB built-in (onnxruntime) all-MiniLM-L6-v2 (384 dims) — FREE, no extra install
  4. sentence-transformers            (384 dims)  — if torch is compatible
  5. TF-IDF fallback                  (512 dims)  — always works, limited quality

Option 3 is the recommended free path — ChromaDB ships its own
embedding runtime (onnxruntime) that does NOT require a working torch install.

Usage:
  from pipeline.vector_store.embedder import Embedder
  emb = Embedder()
  print(emb.provider)           # which backend is active
  vectors = emb.embed(["hello world", "another text"])
"""

import os
from ..config import (
    OPENAI_API_KEY, GOOGLE_API_KEY,
    EMBEDDING_MODEL_OPENAI, EMBEDDING_MODEL_GOOGLE, EMBEDDING_MODEL_LOCAL,
    EMBEDDING_BATCH_SIZE,
)

_CHROMA_EF = None   # cached ChromaDB embedding function


class Embedder:
    """
    Universal embedding generator.
    Automatically selects the best available backend.
    """

    def __init__(self):
        self.provider:    str   = ""
        self.dimensions:  int   = 0
        self._model             = None
        self._tfidf_vectorizer  = None   # persisted across calls
        self._tfidf_fitted      = False
        self._tfidf_vocab:list  = []
        self._init_backend()

    # ─────────────────────────────────────────────
    # Backend initialisation
    # ─────────────────────────────────────────────

    def _init_backend(self):
        """Try each backend in priority order."""

        # ── 1. OpenAI ──────────────────────────────
        if OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=OPENAI_API_KEY)
                self._openai_client.models.list()
                self.provider   = "openai"
                self.dimensions = 1536
                print(f"    [EMBED] Using OpenAI ({EMBEDDING_MODEL_OPENAI}, {self.dimensions}d)")
                return
            except Exception as e:
                print(f"    [EMBED] OpenAI init failed: {e}")

        # ── 2. Google Gemini ────────────────────────
        if GOOGLE_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GOOGLE_API_KEY)
                test_res = genai.embed_content(
                    model=EMBEDDING_MODEL_GOOGLE,
                    content="healthcheck",
                    task_type="retrieval_document"
                )
                self._genai     = genai
                self.provider   = "google"
                self.dimensions = len(test_res["embedding"])
                print(f"    [EMBED] Using Google ({EMBEDDING_MODEL_GOOGLE}, {self.dimensions}d)")
                return
            except Exception as e:
                print(f"    [EMBED] Google init failed: {e}")

        # ── 3. ChromaDB built-in (onnxruntime) ─────
        # ChromaDB ships its own embedding function that runs MiniLM via
        # onnxruntime — no torch required, models auto-download on first use.
        try:
            from chromadb.utils.embedding_functions import (
                ONNXMiniLM_L6_V2,
            )
            global _CHROMA_EF
            if _CHROMA_EF is None:
                _CHROMA_EF = ONNXMiniLM_L6_V2()
            # Warm-up call to trigger model download
            _ = _CHROMA_EF(["warmup"])
            self._chroma_ef = _CHROMA_EF
            self.provider   = "chromadb-onnx"
            self.dimensions = 384
            print(f"    [EMBED] Using ChromaDB built-in ONNX embeddings ({self.dimensions}d)")
            return
        except Exception as e:
            print(f"    [EMBED] ChromaDB ONNX embedder failed: {e}")

        # ── 4. sentence-transformers (if torch works) ──
        try:
            from sentence_transformers import SentenceTransformer
            self._model     = SentenceTransformer(EMBEDDING_MODEL_LOCAL)
            self.provider   = "sentence-transformers"
            self.dimensions = self._model.get_sentence_embedding_dimension()
            print(f"    [EMBED] Using sentence-transformers ({self.dimensions}d)")
            return
        except Exception as e:
            print(f"    [EMBED] sentence-transformers failed: {e}")

        # ── 5. TF-IDF fallback ──────────────────────
        print("    [EMBED] WARNING: No neural embedding backend found.")
        print("            Using TF-IDF fallback (search quality limited).")
        print("            Tip: Set OPENAI_API_KEY or GOOGLE_API_KEY for best results.")
        self.provider   = "tfidf"
        self.dimensions = 512

    # ─────────────────────────────────────────────
    # Embedding generation
    # ─────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of text strings."""
        if not texts:
            return []
        if self.provider == "openai":
            return self._embed_openai(texts)
        elif self.provider == "google":
            return self._embed_google(texts)
        elif self.provider == "chromadb-onnx":
            return self._embed_chroma_onnx(texts)
        elif self.provider == "sentence-transformers":
            return self._embed_local(texts)
        else:
            return self._embed_tfidf(texts)

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        results = []
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = [t[:32000] for t in texts[i: i + EMBEDDING_BATCH_SIZE]]
            try:
                resp = self._openai_client.embeddings.create(
                    model=EMBEDDING_MODEL_OPENAI, input=batch
                )
                results.extend([e.embedding for e in resp.data])
            except Exception as e:
                print(f"    [EMBED] OpenAI batch error: {e}")
                results.extend([[0.0] * self.dimensions] * len(batch))
        return results

    def _embed_google(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            try:
                resp = self._genai.embed_content(
                    model=EMBEDDING_MODEL_GOOGLE,
                    content=text,
                    task_type="retrieval_document",
                )
                results.append(resp["embedding"])
            except Exception as e:
                print(f"    [EMBED] Google embed error: {e}")
                results.append([0.0] * self.dimensions)
        return results

    def _embed_chroma_onnx(self, texts: list[str]) -> list[list[float]]:
        """Use ChromaDB's built-in ONNX MiniLM embedding function."""
        try:
            vecs = self._chroma_ef(texts)
            # Convert np.float32 -> plain Python float (ChromaDB requires this)
            return [[float(x) for x in v] for v in vecs]
        except Exception as e:
            print(f"    [EMBED] ChromaDB ONNX error: {e}")
            return [[0.0] * self.dimensions] * len(texts)

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        try:
            vecs = self._model.encode(
                texts,
                batch_size=EMBEDDING_BATCH_SIZE,
                show_progress_bar=len(texts) > 50,
                convert_to_numpy=True,
            )
            return [v.tolist() for v in vecs]
        except Exception as e:
            print(f"    [EMBED] Local embed error: {e}")
            return [[0.0] * self.dimensions] * len(texts)

    def _embed_tfidf(self, texts: list[str]) -> list[list[float]]:
        """
        TF-IDF pseudo-embeddings.
        The vectorizer is fitted once on the first batch and REUSED for all
        subsequent calls (including single-query embedding) to keep dimensions
        consistent — fixing the ChromaDB dimension-mismatch error.
        """
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np

        if not self._tfidf_fitted:
            # First call: fit the vectorizer on the provided texts
            self._tfidf_vectorizer = TfidfVectorizer(max_features=512)
            matrix = self._tfidf_vectorizer.fit_transform(texts).toarray()
            self._tfidf_fitted = True
            self.dimensions = matrix.shape[1]
            return matrix.tolist()
        else:
            # Subsequent calls: transform only (same vocab → same dims)
            try:
                matrix = self._tfidf_vectorizer.transform(texts).toarray()
                # Pad or trim if needed (edge case)
                if matrix.shape[1] != self.dimensions:
                    padded = np.zeros((len(texts), self.dimensions))
                    cols = min(matrix.shape[1], self.dimensions)
                    padded[:, :cols] = matrix[:, :cols]
                    return padded.tolist()
                return matrix.tolist()
            except Exception as e:
                print(f"    [EMBED] TF-IDF transform error: {e}")
                return [[0.0] * self.dimensions] * len(texts)

    # ─────────────────────────────────────────────
    # Convenience
    # ─────────────────────────────────────────────

    def embed_one(self, text: str) -> list[float]:
        """Embed a single string — always uses same vectorizer as batch."""
        result = self.embed([text])
        return result[0] if result else []

    def info(self) -> str:
        return f"Embedder(provider={self.provider}, dims={self.dimensions})"
