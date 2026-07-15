"""RAG crop knowledge: retrieve curated fertigation facts to ground the LLM.

Knowledge lives in ``knowledge/crops_seed.json`` (+ optional ``knowledge/*.pdf``).
``build_index()`` embeds every chunk with Voyage and saves the index to
``data/knowledge_index.npz``. ``retrieve()`` embeds a query and returns the
top-k most similar chunks by cosine similarity (numpy brute-force). Retrieval
is best-effort: any failure returns ``[]`` so the assistant keeps working
without grounding.

# ponytail: numpy brute-force cosine; swap to Chroma/FAISS if chunks exceed ~5000
"""

import os
import json
import glob
import logging

import numpy as np

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_KNOWLEDGE_DIR = os.path.join(_ROOT, "knowledge")
_SEED = os.path.join(_KNOWLEDGE_DIR, "crops_seed.json")
_INDEX = os.path.join(_ROOT, "data", "knowledge_index.npz")

_EMBED_MODEL = "voyage-3"


def _cosine_top_k(query_vec, matrix, k):
    """Indices + scores of the k rows in `matrix` most similar to `query_vec`
    by cosine similarity, best first. `matrix` shape (n, dim)."""
    if matrix.shape[0] == 0:
        return np.array([], dtype=int), np.array([], dtype=np.float32)
    qn = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    mn = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    sims = mn @ qn
    k = min(k, sims.shape[0])
    top = np.argpartition(-sims, k - 1)[:k]
    order = top[np.argsort(-sims[top])]
    return order, sims[order]


def _voyage():
    """Voyage client from VOYAGE_API_KEY. Imported lazily so the app runs
    without voyageai installed until knowledge is actually used."""
    key = os.environ.get("VOYAGE_API_KEY")
    if not key:
        raise RuntimeError("VOYAGE_API_KEY is not set. Add it to your .env file.")
    import voyageai
    return voyageai.Client(api_key=key)


def _embed(texts, input_type):
    """Embed `texts` with Voyage. `input_type` is 'document' or 'query'.
    Returns an (n, dim) float32 array."""
    resp = _voyage().embed(texts, model=_EMBED_MODEL, input_type=input_type)
    return np.asarray(resp.embeddings, dtype=np.float32)
