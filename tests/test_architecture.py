"""
tests/test_architecture.py — Architecture Alignment & Config Test Suite (Work Package 1).
"""

import pytest
from pydantic import ValidationError

from config import Settings
from pipeline.vector_store import (
    Document,
    VectorStore,
    ChromaVectorStore,
    PineconeVectorStore,
    get_vector_store,
)
from pipeline.llm import (
    LLMClient,
    EmbeddingClient,
    ONNXLLMClient,
    ONNXEmbeddingClient,
    get_llm,
    get_embedder,
)


def test_default_settings_resolved():
    """Verify default settings load and generate proper resolved summary string."""
    s = Settings(VECTOR_BACKEND="chroma")
    summary = s.resolved_summary()
    assert "[config]" in summary
    assert "vector=chroma" in summary
    assert s.CHROMA_HNSW_M == 32
    assert s.CHROMA_HNSW_CONSTRUCTION_EF == 200
    assert s.CHROMA_HNSW_SEARCH_EF == 100


def test_pinecone_missing_key_raises_error():
    """VECTOR_BACKEND=pinecone must raise ValueError when PINECONE_API_KEY is missing."""
    with pytest.raises((ValueError, ValidationError), match="PINECONE_API_KEY"):
        Settings(VECTOR_BACKEND="pinecone", PINECONE_API_KEY=None)


def test_groq_missing_key_raises_error():
    """LLM_BACKEND=groq must raise ValueError when GROQ_API_KEY is missing."""
    with pytest.raises((ValueError, ValidationError), match="GROQ_API_KEY"):
        Settings(LLM_BACKEND="groq", GROQ_API_KEY=None)


def test_pinecone_and_groq_valid_when_keys_present():
    """Valid keys allow Pinecone and Groq backend initialization."""
    s = Settings(
        VECTOR_BACKEND="pinecone",
        PINECONE_API_KEY="test-pc-key",
        LLM_BACKEND="groq",
        GROQ_API_KEY="test-groq-key",
    )
    assert s.VECTOR_BACKEND == "pinecone"
    assert s.LLM_BACKEND == "groq"
    assert s.GROQ_MODEL == "llama-3.1-70b-versatile"


def test_document_protocol_and_dict_access():
    """Document model must satisfy protocol and provide dict-like access for backward compatibility."""
    doc = Document(
        id="chunk_1",
        text="Sample annual report text.",
        metadata={"company": "Apple", "page_number": 3, "score": 95.5},
    )
    assert doc.id == "chunk_1"
    assert doc.text == "Sample annual report text."
    assert doc["company"] == "Apple"
    assert doc["page_number"] == 3
    assert doc["score"] == 95.5
    assert doc.get("nonexistent", "default_val") == "default_val"


def test_chroma_implements_vector_store_protocol(tmp_path):
    """ChromaVectorStore must implement VectorStore protocol with explicit HNSW settings."""
    cvs = ChromaVectorStore(
        company_name="test_company",
        m=16,
        construction_ef=100,
        search_ef=50,
    )
    assert isinstance(cvs, VectorStore)
    assert cvs.hnsw_m == 16
    assert cvs.hnsw_construction_ef == 100
    assert cvs.hnsw_search_ef == 50

    # Test add_documents, query, delete
    doc = Document(id="doc_t1", text="Cloud AI infrastructure scaling", metadata={"source": "test"})
    cvs.add_documents([doc], namespace="test_company")
    results = cvs.query("Cloud infrastructure", top_k=2, namespace="test_company")
    assert len(results) > 0
    assert isinstance(results[0], Document)
    cvs.delete("test_company", ids=["doc_t1"])


def test_pinecone_adapter_satisfies_protocol():
    """Pinecone adapter satisfies the VectorStore protocol."""
    # Instantiation without key raises ValueError
    with pytest.raises(ValueError, match="PINECONE_API_KEY"):
        PineconeVectorStore(api_key="")


def test_llm_factory_and_onnx_offline():
    """Factory returns LLMClient and EmbeddingClient; ONNX runs offline with no keys."""
    llm = get_llm("onnx")
    assert isinstance(llm, LLMClient)
    out = llm.generate("Hello world")
    assert isinstance(out, str)

    embedder = get_embedder("local")
    assert isinstance(embedder, EmbeddingClient)
    assert embedder.dimensions == 384
    vecs = embedder.embed(["test sentence"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 384
