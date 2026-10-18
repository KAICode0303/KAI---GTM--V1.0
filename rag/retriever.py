"""Chroma vector store (persistent, local) and cited retrieval.

Chroma's anonymous telemetry is switched off, so nothing leaves the machine.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from chromadb.config import Settings
from langchain_chroma import Chroma

from rag.ingest import chunk_documents, load_documents

INDEX_DIR = Path(__file__).resolve().parent.parent / ".rag_index" / "chroma"       # git-ignored
COLLECTION = "kai_gtm_v2"


def format_citation(md):
    """'[file › section]' for Markdown, '[file › section, p.N]' when a real page number exists (PDFs)."""
    where = md["source"]
    if md.get("section"):
        where += f" › {md['section']}"
    if md.get("page") is not None:
        where += f", p.{md['page']}"
    return f"[{where}]"


@dataclass
class Hit:
    text: str
    source: str
    section: str
    page: Optional[int]      # None for Markdown, the real page number for PDFs
    title: str
    doc_type: str
    distance: float          # Chroma's distance for this embedding model: smaller = closer match (not a 0-1 score)
    citation: str            # e.g. "[02_icp.md › Best-fit customers]"


def get_store(embeddings, persist_dir=INDEX_DIR, collection=COLLECTION):
    persist_dir = str(persist_dir)
    return Chroma(collection_name=collection, embedding_function=embeddings, persist_directory=persist_dir,
                  client_settings=Settings(is_persistent=True, persist_directory=persist_dir, anonymized_telemetry=False))


def build_index(store, chunks=None):
    """Add (or update) chunks. Stable ids make re-running safe: no duplicates. Returns the chunk count."""
    chunks = chunks if chunks is not None else chunk_documents(load_documents())
    store.add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])
    return len(chunks)


def retrieve(store, query, k=3, max_distance=None):
    """Top-k chunks for `query`, closest first, each with a ready-to-print citation.

    max_distance: drop chunks farther than this. None = keep all k (raw retrieval, no judgement about relevance).
    """
    hits = []
    for doc, dist in store.similarity_search_with_score(query, k=k):
        if max_distance is not None and dist > max_distance:
            continue
        md = doc.metadata
        hits.append(Hit(text=doc.page_content, source=md["source"], section=md.get("section", ""), page=md.get("page"),
                        title=md["title"], doc_type=md["doc_type"], distance=float(dist), citation=format_citation(md)))
    return hits
