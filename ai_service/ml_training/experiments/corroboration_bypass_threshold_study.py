import os
import re
import glob
import random

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_9 = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments\exp9-balanced-domain-APPROVED-BACKUP"
ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"

CONFIRMED_THRESHOLD = 0.75
N_CANDIDATES = [1, 2, 3, 4, 5, 6, 8, 10, 15, 20]
SEED = 20260731

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


def load_documents(n_per_category=10, min_chars=3000):
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
                docs.append({"category": cat, "path": fp, "text": text})
                picked += 1
            if picked >= n_per_category:
                break
    return docs


def main():
    model = SentenceTransformer(MODEL_9)
    docs = load_documents()
    print(f"Loaded {len(docs)} real ARPD documents across categories")

    doc_chunks = {}
    doc_vectors = {}
    for d in docs:
        raw_chunks = chunk_simple(d["text"])
        chunks = [c for c in raw_chunks if not is_citation_chunk(c)]
        doc_chunks[d["path"]] = chunks
        doc_vectors[d["path"]] = model.encode(chunks, show_progress_bar=False) if chunks else np.zeros((0, 384))

    rng = random.Random(SEED)
    query_docs = rng.sample(docs, min(30, len(docs)))
    corpus_docs = docs

    print(f"\n{'N (own chunks)':>15} | {'false-positive rate (bypass, no corroboration)':>48} | {'comparisons':>12}")
    for n in N_CANDIDATES:
        false_positive_scans = 0
        total_scans = 0
        for q in query_docs:
            q_vec_full = doc_vectors[q["path"]]
            if len(q_vec_full) < n:
                continue
            # عيّنة عشوائية ثابتة من n مقطعاً من هذه الورقة، تحاكي ورقة قصيرة بالفعل بهذا الطول
            start = random.Random(hash(q["path"]) % (2**31)).randint(0, len(q_vec_full) - n)
            q_vec = q_vec_full[start:start + n]

            any_false_positive = False
            for c in corpus_docs:
                if c["path"] == q["path"] or c["category"] == q["category"]:
                    continue
                c_vec = doc_vectors[c["path"]]
                if len(c_vec) == 0:
                    continue
                scores = cosine_similarity(q_vec, c_vec)
                if float(scores.max()) >= CONFIRMED_THRESHOLD:
                    any_false_positive = True
                    break
            total_scans += 1
            if any_false_positive:
                false_positive_scans += 1

        fpr = false_positive_scans / total_scans if total_scans else 0.0
        print(f"{n:>15} | {fpr*100:>46.1f}% | {total_scans:>12}")


if __name__ == "__main__":
    main()
