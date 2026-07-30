import os
import sys
import glob
import random
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_9 = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments\exp9-balanced-domain-APPROVED-BACKUP"
ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"


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


def load_docs(n_per_cat=4, min_chars=3000):
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
            if picked >= n_per_cat:
                break
    return docs


def main():
    model = SentenceTransformer(MODEL_9)
    docs = load_docs()
    print(f"Loaded {len(docs)} documents across categories: {sorted(set(d['category'] for d in docs))}")

    vectors = {}
    chunks_by_doc = {}
    for d in docs:
        chunks = chunk_simple(d["text"])
        chunks_by_doc[d["path"]] = chunks
        vectors[d["path"]] = model.encode(chunks, show_progress_bar=False) if chunks else np.zeros((0, 384))

    top_matches = []
    for q in docs:
        for c in docs:
            if q["path"] == c["path"] or q["category"] == c["category"]:
                continue
            qv, cv = vectors[q["path"]], vectors[c["path"]]
            if len(qv) == 0 or len(cv) == 0:
                continue
            scores = cosine_similarity(qv, cv)
            idx = np.unravel_index(np.argmax(scores), scores.shape)
            top_matches.append((
                float(scores[idx]), q["category"], c["category"],
                chunks_by_doc[q["path"]][idx[0]], chunks_by_doc[c["path"]][idx[1]]
            ))

    top_matches.sort(key=lambda x: x[0], reverse=True)
    lines = ["===== TOP 12 highest-scoring chunk-pairs between GENUINELY UNRELATED documents ====="]
    for score, cat_q, cat_c, chunk_q, chunk_c in top_matches[:12]:
        lines.append(f"\nscore={score:.4f}  [{cat_q}]  vs  [{cat_c}]")
        lines.append(f"  Q: {chunk_q[:220]}")
        lines.append(f"  C: {chunk_c[:220]}")
    out_text = "\n".join(lines)
    out_path = os.path.join(os.path.dirname(__file__), "diagnose_output.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_text)
    print(out_text)
    print(f"\n(also written to {out_path})")


if __name__ == "__main__":
    main()
