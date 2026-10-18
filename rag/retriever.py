"""Chroma vector store (persistent, local) and cited retrieval.

Chroma's anonymous telemetry is switched off, so nothing leaves the machine.
"""
from dataclasses import dataclass
from pathlib import Path

from chromadb.config import Settings
from langchain_chroma import Chroma

from rag.ingest import chunk_documents, load_documents

INDEX_DIR = Path(__file__).resolve().parent.parent / ".rag_index" / "chroma"       # git-ignored
COLLECTION = "kai_gtm_v2"


@dataclass
class Hit:
    text: str
    source: str
    page: int
    title: str
    doc_type: str
    distance: float          # smaller = closer match
    citation: str            # e.g. "[01_capabilities.md, p.1]"


def get_store(embeddings, persist_dir=INDEX_DIR, collection=COLLECTION):
    persist_dir = str(persist_dir)
    return Chroma(collection_name=collection, embedding_function=embeddings, persist_directory=persist_dir,
                  client_settings=Settings(is_persistent=True, persist_directory=persist_dir, anonymized_telemetry=False))


def build_index(store, chunks=None):
    """Add (or update) chunks. Stable ids make re-running safe: no duplicates. Returns the chunk count."""
    chunks = chunks if chunks is not None else chunk_documents(load_documents())
    store.add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])
    return len(chunks)


def retrieve(store, query, k=3):
    """Top-k chunks for `query`, closest first, each with a ready-to-print citation."""
    hits = []
    for doc, dist in store.similarity_search_with_score(query, k=k):
        md = doc.metadata
        hits.append(Hit(text=doc.page_content, source=md["source"], page=md["page"], title=md["title"],
                        doc_type=md["doc_type"], distance=float(dist), citation=f"[{md['source']}, p.{md['page']}]"))
    return hits
