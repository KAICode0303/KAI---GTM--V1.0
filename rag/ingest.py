"""Load sanitized Markdown documents from rag_corpus/ and split them into chunks that carry source metadata.

Every document must declare `sanitized: true` in its front matter, otherwise it is refused. This is a guard
against real company material slipping into the index by accident.
"""
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

CORPUS_DIR = Path(__file__).resolve().parent.parent / "rag_corpus"


def _parse(text):
    """Split `---` front matter (simple `key: value` lines) from the body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), None)
    if end is None:
        return {}, text
    meta = {}
    for ln in lines[1:end]:
        key, _, value = ln.partition(":")
        meta[key.strip()] = value.strip()
    return meta, "\n".join(lines[end + 1:]).strip()


def load_documents(corpus_dir=CORPUS_DIR):
    """One Document per .md file. Raises ValueError if a file is not marked `sanitized: true`."""
    docs = []
    for path in sorted(Path(corpus_dir).glob("*.md")):
        meta, body = _parse(path.read_text(encoding="utf-8"))
        if meta.get("sanitized", "").lower() != "true":
            raise ValueError(f"{path.name} is not marked 'sanitized: true' - refusing to index it.")
        docs.append(Document(page_content=body, metadata={
            "source": path.name, "title": meta.get("title", path.stem), "doc_type": meta.get("doc_type", "other"),
            "page": 1, "sanitized": True}))       # Markdown has no pages; PDFs will carry real page numbers
    return docs


def chunk_documents(docs, chunk_size=450, chunk_overlap=60):
    """Split into chunks; each keeps its source metadata and gets a stable `chunk_id` (used as the Chroma id)."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = splitter.split_documents(docs)
    counts = {}
    for c in chunks:
        n = counts[c.metadata["source"]] = counts.get(c.metadata["source"], -1) + 1
        c.metadata["chunk_id"] = f"{c.metadata['source']}#{n}"
    return chunks
