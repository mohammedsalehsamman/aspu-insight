import os
import re
import glob
import random

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_9 = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments\exp9-balanced-domain-APPROVED-BACKUP"
ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"
OUT_PATH = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\commonness_reference_arpd.npy"

# Mirrors chunking.py::is_citation_chunk - citation/quotation chunks are excluded from the
# reference corpus too, since they'd otherwise dominate the "common phrase" signal for the
# wrong reason (shared scripture, not shared academic boilerplate style).
_QUOTE_MARK_RE = re.compile(r'["“”«»﴾﴿]')
_CITATION_MARKER_RE = re.compile(
    r'\[\d+(?:\s*,\s*\d+)*\]'
    r'|\([^()]{0,40}(?:19|20)\d{2}\)'
    r'|\([؀-ۿ\s]{2,25}:\s*\d{1,3}\)'
    r'|et\s+al\.?'
    r'|نقلاً?\s+عن|كما\s+ورد\s+في|المصدر\s*:|بحسب\s+',
    re.IGNORECASE,
)
_QURANIC_LIGATURE_RE = re.compile(r'[ﭐ-﷿ﹰ-﻿]')


def is_citation_chunk(text):
    if not text:
        return False
    if len(_QURANIC_LIGATURE_RE.findall(text)) >= 5:
        return True
    return bool(_QUOTE_MARK_RE.search(text) and _CITATION_MARKER_RE.search(text))


def chunk_simple(text, n_sentences=4, overlap=1):
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    chunks = []
    step = max(n_sentences - overlap, 1)
    for i in range(0, len(sentences), step):
        group = sentences[i:i + n_sentences]
        if group:
            chunks.append(". ".join(group) + ".")
        if i + n_sentences >= len(sentences):
            break
    return chunks


def load_documents(n_per_category=40, min_chars=3000):
    docs = []
    for cat in sorted(os.listdir(ARPD_ROOT)):
        cat_path = os.path.join(ARPD_ROOT, cat)
        if not os.path.isdir(cat_path):
            continue
        files = glob.glob(os.path.join(cat_path, "*.txt"))
        rng = random.Random(hash(cat) % (2**31))
        rng.shuffle(files)
        picked = 0
        for fp in files:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if len(text) >= min_chars:
                docs.append(text)
                picked += 1
            if picked >= n_per_category:
                break
    return docs


def main():
    model = SentenceTransformer(MODEL_9)
    docs = load_documents()
    print(f"Loaded {len(docs)} ARPD documents for the commonness-reference bootstrap corpus")

    all_chunks = []
    for text in docs:
        for c in chunk_simple(text):
            if not is_citation_chunk(c):
                all_chunks.append(c)
    print(f"{len(all_chunks)} non-citation chunks to embed as the reference pool")

    vectors = model.encode(all_chunks, show_progress_bar=True, batch_size=64)
    vectors = np.asarray(vectors, dtype=np.float32)
    np.save(OUT_PATH, vectors)
    print(f"Saved reference vector pool {vectors.shape} to {OUT_PATH}")


if __name__ == "__main__":
    main()
