"""The Hoomi app's own knowledge index: synthetic documents in rag_corpus/gtm plus KYC profiles from the workspace.

Separate from the evaluation index (.rag_index/chroma and rag_corpus/*.md), so evaluation results are never disturbed.
Everything is local: cached FastEmbed model (downloads blocked unless you pass --allow-model-download to the CLI) and Chroma.

    python -m rag.app_index                       build or refresh the index (no downloads)
    python -m rag.app_index --allow-model-download   first-time setup: also fetch the public embedding model (~67 MB)

Only documents that changed (a corpus file, or a KYC profile edited in the workspace) are re-embedded; a hash per document is stored beside the index.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from langchain_core.documents import Document

from gtm import kyc, validation
from rag import embeddings as emb
from rag.ingest import chunk_documents, load_documents
from rag.retriever import build_index, get_store

ROOT = Path(__file__).resolve().parent.parent
APP_CORPUS_DIR = ROOT / "rag_corpus" / "gtm"
APP_INDEX_DIR = ROOT / ".rag_index" / "app_chroma"
COLLECTION = "hoomi_app"
KYC_SECTIONS = [  # (heading, [(field key, how it reads)])
    ("Overview", [("business_model", "Business model"), ("hq_city", "Headquarters city"), ("employee_range", "Employees"),
                  ("annual_revenue_range", "Annual revenue range"), ("website", "Website"), ("icp_fit_notes", "ICP fit")]),
    ("Requested capabilities", [("requested_capabilities", "Requested capabilities")]),
    ("Buying committee", [("primary_contact", "Primary contact"), ("decision_makers", "Decision makers")]),
    ("Competition and vendors", [("current_vendors", "Current vendors"), ("competitors", "Competitors"), ("tech_stack", "Relevant tech stack")]),
    ("Budget and timeline", [("budget_range", "Budget range"), ("buying_timeline", "Buying timeline")]),
    ("Compliance", [("compliance_requirements", "Compliance and data requirements")]),
    ("Pain points and triggers", [("pain_points", "Pain points"), ("trigger_events", "Trigger events")]),
]


def kyc_documents(gtm_store):
    """One Document per account with a KYC profile, written as plain sentences so answers can quote them."""
    accounts = gtm_store.accounts().set_index("account_id")
    docs = []
    for row in gtm_store.df("SELECT account_id, data_json FROM kyc_profiles ORDER BY account_id").itertuples():
        data, acct = kyc.clean(json.loads(row.data_json)), accounts.loc[row.account_id]
        name = acct["account_name"]
        lines = [f"# KYC profile: {name} ({row.account_id})", "",
                 f"{name} is in the {acct['customer_segment']} segment and is headquartered in {acct['hq_region']}."]
        for heading, fields in KYC_SECTIONS:
            facts = [f"{label} for {name}: {data[key].rstrip('.')}." for key, label in fields if data.get(key)]
            if facts:
                lines += ["", f"## {heading}", *facts]
        docs.append(Document(page_content="\n".join(lines), metadata={
            "source": f"kyc_{row.account_id}.md", "title": f"KYC profile: {name} ({row.account_id})", "doc_type": "kyc",
            "account_id": row.account_id, "sanitized": True}))
    return docs


def build_documents(gtm_store=None, corpus_dir=None):
    docs = load_documents(corpus_dir or APP_CORPUS_DIR)                                  # refuses anything not marked `sanitized: true`
    return docs + (kyc_documents(gtm_store) if gtm_store is not None else [])


PARAMS = f"{emb.DEFAULT_MODEL}|title+section|450|60"       # anything that changes how every chunk is made or embedded


def doc_hash(doc):
    return hashlib.sha256(json.dumps([doc.metadata, doc.page_content], sort_keys=True, default=str).encode()).hexdigest()


def fingerprint(docs, params=PARAMS):
    """One short hash of the whole corpus (for display and tests)."""
    h = hashlib.sha256(params.encode())
    for d in sorted(docs, key=lambda d: d.metadata["source"]):
        h.update(doc_hash(d).encode())
    return h.hexdigest()


def ensure_index(embeddings, gtm_store=None, persist_dir=None, corpus_dir=None):
    """Open the app index, refreshing ONLY the documents that changed (a KYC edit re-embeds that account's few chunks).

    A marker file records each document's hash. Documents that were added, edited or removed have their old chunks deleted
    (by `source`) and their new chunks written; everything else is reused. Returns (store, info).
    """
    persist_dir, corpus_dir = Path(persist_dir or APP_INDEX_DIR), Path(corpus_dir or APP_CORPUS_DIR)     # resolved at call time
    docs = build_documents(gtm_store, corpus_dir)
    params = f"{getattr(embeddings, 'model_name', 'custom')}|title+section|450|60"
    store = get_store(embeddings, persist_dir=persist_dir, collection=COLLECTION)
    marker = persist_dir / "documents.json"
    try:
        old = json.loads(marker.read_text()) if marker.exists() else {}
    except ValueError:
        old = {}
    known = old.get("docs", {}) if old.get("params") == params and store._collection.count() > 0 else {}
    new = {d.metadata["source"]: doc_hash(d) for d in docs}
    removed = [src for src in known if src not in new]
    changed = [d for d in docs if known.get(d.metadata["source"]) != new[d.metadata["source"]]]
    for src in removed + [d.metadata["source"] for d in changed if d.metadata["source"] in known]:
        store._collection.delete(where={"source": src})                  # only this app index's own generated rows
    if not known:                                                          # new model/params or an empty index: start clean
        stale = store._collection.get(include=[])["ids"]
        if stale:
            store._collection.delete(ids=stale)
    if changed:
        build_index(store, chunk_documents(changed))
    if changed or removed or not marker.exists():
        persist_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"params": params, "docs": new}))
    kyc_n = sum(d.metadata.get("doc_type") == "kyc" for d in docs)
    return store, {"chunks": store._collection.count(), "documents": len(docs), "kyc_documents": kyc_n, "updated": len(changed), "removed": len(removed),
                   "rebuilt": bool(changed or removed), "fingerprint": fingerprint(docs, params)[:12]}


def account_in_question(question, gtm_store):
    """The account the question names (by name or ACC-id), longest name wins; None if none is mentioned."""
    q = " " + validation.name_key(question) + " "
    best = None
    for r in gtm_store.df("SELECT account_id, name_key FROM accounts").itertuples():
        if re.search(rf"\b{re.escape(r.account_id.lower())}\b", question.lower()) or (r.name_key and f" {r.name_key} " in q):
            if best is None or len(r.name_key) > len(best[1]):
                best = (r.account_id, r.name_key)
    return best[0] if best else None


def scope_filter(question, gtm_store):
    """Which chunks may be searched: general documents always; KYC profiles only for the account the question names."""
    aid = account_in_question(question, gtm_store) if gtm_store is not None else None
    if aid:
        return {"$or": [{"account_id": aid}, {"doc_type": {"$ne": "kyc"}}]}, aid
    return {"doc_type": {"$ne": "kyc"}}, None


def make_embeddings():
    return emb.FastEmbedEmbeddings()                                   # cached model only; downloads blocked


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--allow-model-download", action="store_true", help="allow the one-time download of the public embedding model")
    args = ap.parse_args(argv)
    from gtm.store import GTMStore
    store, info = ensure_index(emb.FastEmbedEmbeddings(allow_download=args.allow_model_download), GTMStore())
    print(f"App index ready: {info['chunks']} chunks from {info['documents']} documents ({info['updated']} updated, {info['removed']} removed).")


if __name__ == "__main__":
    main()
