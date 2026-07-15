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


def _crop_to_text(crop):
    """Render a seed crop dict as readable text so its embedding captures it."""
    lines = [f"Crop: {crop.get('crop', '')}"]
    for st in crop.get("stages", []):
        tgt = st.get("targets", {})
        parts = [f"{k} {v.get('min')}-{v.get('max')}" for k, v in tgt.items()]
        lines.append(
            f"Stage {st.get('name', '')} "
            f"({st.get('duration_days', '?')} days): " + ", ".join(parts)
        )
    if crop.get("notes"):
        lines.append("Notes: " + crop["notes"])
    return "\n".join(lines)


def _pdf_chunks(path):
    """One chunk per readable PDF page. Best-effort — bad pages are skipped."""
    from pypdf import PdfReader
    out = []
    name = os.path.basename(path)
    try:
        reader = PdfReader(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot read PDF %s: %s", name, exc)
        return out
    for i, page in enumerate(reader.pages):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bad page %d in %s: %s", i + 1, name, exc)
            continue
        if text:
            out.append({"text": text, "source": f"{name}:p{i + 1}"})
    return out


def _load_chunks():
    """Load knowledge chunks: one per seed crop + one per PDF page."""
    chunks = []
    if os.path.exists(_SEED):
        with open(_SEED, encoding="utf-8") as f:
            for crop in json.load(f):
                chunks.append({
                    "text": _crop_to_text(crop),
                    "source": f"seed:{crop.get('crop', '?')}",
                })
    for pdf in sorted(glob.glob(os.path.join(_KNOWLEDGE_DIR, "*.pdf"))):
        chunks.extend(_pdf_chunks(pdf))
    return chunks


def build_index():
    """Embed all knowledge chunks and save the index to `data/`. Raises
    RuntimeError if there is nothing to index. Explicit maintenance step —
    fails loudly on embedding errors."""
    chunks = _load_chunks()
    if not chunks:
        raise RuntimeError(f"No knowledge found in {_KNOWLEDGE_DIR}")
    vectors = _embed([c["text"] for c in chunks], "document")
    os.makedirs(os.path.dirname(_INDEX), exist_ok=True)
    np.savez(
        _INDEX,
        vectors=vectors,
        texts=np.array([c["text"] for c in chunks], dtype=object),
        sources=np.array([c["source"] for c in chunks], dtype=object),
    )
    logger.info("Built knowledge index: %d chunks -> %s", len(chunks), _INDEX)
    return len(chunks)


def retrieve(query, k=4):
    """Up to k knowledge chunks most relevant to `query`, best first:
    [{"text", "source", "score"}]. Best-effort — returns [] on any failure
    (missing index/key, network) so the assistant never breaks over knowledge."""
    try:
        if not os.path.exists(_INDEX):
            logger.warning("Knowledge index missing (%s); run build_knowledge.py", _INDEX)
            return []
        data = np.load(_INDEX, allow_pickle=True)
        qvec = _embed([query], "query")[0]
        idx, scores = _cosine_top_k(qvec, data["vectors"], k)
        texts, sources = data["texts"], data["sources"]
        return [
            {"text": str(texts[i]), "source": str(sources[i]), "score": float(s)}
            for i, s in zip(idx, scores)
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Knowledge retrieval failed: %s", exc)
        return []
