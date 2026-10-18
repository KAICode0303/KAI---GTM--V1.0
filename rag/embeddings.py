"""Local embeddings with FastEmbed (ONNX, runs on this Mac; text is never sent anywhere).

The model weights are a one-time download of PUBLIC model files from Hugging Face. To keep that deliberate,
downloads are blocked unless `allow_download=True` is passed. The model is loaded lazily, so importing or
constructing this class never touches the network or the disk cache.
"""
from pathlib import Path

from langchain_core.embeddings import Embeddings

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"     # 384 dimensions, ~67 MB, MIT licence
MODEL_CACHE_DIR = Path(__file__).resolve().parent.parent / ".rag_index" / "models"   # git-ignored


class FastEmbedEmbeddings(Embeddings):
    def __init__(self, model_name=DEFAULT_MODEL, cache_dir=MODEL_CACHE_DIR, allow_download=False):
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.allow_download = allow_download
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=str(self.cache_dir),
                                        local_files_only=not self.allow_download)
        return self._model

    def embed_documents(self, texts):
        return [v.tolist() for v in self._load().embed(list(texts))]

    def embed_query(self, text):
        return next(iter(self._load().query_embed(text))).tolist()
