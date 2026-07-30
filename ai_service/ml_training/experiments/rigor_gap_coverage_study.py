import os
import re
import glob
import json
import random

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics import roc_auc_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Mirrors ai_service/plagiarism/services/chunking.py::is_citation_chunk exactly (duplicated
# here, not imported, so this script can run standalone without django.setup()).
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
_QURANIC_LIGATURE_MIN_COUNT = 5


def is_citation_chunk(text):
    if not text:
        return False
    if len(_QURANIC_LIGATURE_RE.findall(text)) >= _QURANIC_LIGATURE_MIN_COUNT:
        return True
    return bool(_QUOTE_MARK_RE.search(text) and _CITATION_MARKER_RE.search(text))

MODELS_ROOT = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments"
MODEL_9 = os.path.join(MODELS_ROOT, "exp9-balanced-domain-APPROVED-BACKUP")
MODEL_10 = os.path.join(MODELS_ROOT, "exp10-backtranslation-augmented")
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"

CONFIRMED_THRESHOLD = 0.75
N_BOOTSTRAP = 1000
SEED = 20260730


# ---------- A: bootstrap confidence intervals ----------

def bootstrap_ci(sims, labels, threshold, n_boot=N_BOOTSTRAP, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(labels)
    aucs = []
    fp_rates = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        s, l = sims[idx], labels[idx]
        if len(set(l.tolist())) < 2:
            continue
        aucs.append(roc_auc_score(l, s))
        neg_mask = l == 0
        pred_pos = s >= threshold
        fp_rates.append(float((pred_pos & neg_mask).sum()) / max(neg_mask.sum(), 1))
    aucs = np.array(aucs)
    fp_rates = np.array(fp_rates)
    return {
        "auc_mean": float(aucs.mean()), "auc_ci95": (float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))),
        "fp_rate_mean": float(fp_rates.mean()), "fp_rate_ci95": (float(np.percentile(fp_rates, 2.5)), float(np.percentile(fp_rates, 97.5))),
    }


# ---------- B: baseline (non-ML) comparison methods ----------

def jaccard_scores(pairs):
    scores = []
    for p in pairs:
        set_a = set(p["a"].split())
        set_b = set(p["b"].split())
        union = len(set_a | set_b)
        scores.append(len(set_a & set_b) / union if union else 0.0)
    return np.array(scores)


def tfidf_scores(pairs):
    texts_a = [p["a"] for p in pairs]
    texts_b = [p["b"] for p in pairs]
    vectorizer = TfidfVectorizer()
    vectorizer.fit(texts_a + texts_b)
    vec_a = vectorizer.transform(texts_a)
    vec_b = vectorizer.transform(texts_b)
    scores = np.array([cosine_similarity(vec_a[i], vec_b[i])[0][0] for i in range(len(pairs))])
    return scores


# ---------- D: document-level false-positive simulation (multiple comparisons) ----------

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


def load_unrelated_documents(n_docs_per_category=10, min_chars=3000):
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
            if picked >= n_docs_per_category:
                break
    return docs


CORROBORATION_THRESHOLD = 0.50
MIN_CORROBORATING_CHUNKS = 2
DOC_THRESHOLD_CANDIDATES = [0.75, 0.80, 0.85, 0.90, 0.92, 0.94, 0.96]


def collect_document_pair_stats(model, n_docs_per_category=10):
    """For every genuinely-unrelated (cross-category) document pair in the corpus, compute the
    single best chunk-pair score AND how many of the query doc's chunks independently score
    >= CORROBORATION_THRESHOLD against that same other paper. Cached once, reused for every
    threshold/corroboration-rule combination tested afterwards (avoids re-embedding)."""
    docs = load_unrelated_documents(n_docs_per_category=n_docs_per_category)
    doc_vectors = {}
    total_chunks = 0
    total_dropped = 0
    for d in docs:
        key = d["path"]
        raw_chunks = chunk_simple(d["text"])
        total_chunks += len(raw_chunks)
        chunks = [c for c in raw_chunks if not is_citation_chunk(c)]
        total_dropped += len(raw_chunks) - len(chunks)
        doc_vectors[key] = model.encode(chunks, show_progress_bar=False) if chunks else np.zeros((0, 384))
    print(f"  (citation-quote filter: excluded {total_dropped}/{total_chunks} chunks flagged as declared quotations)")

    pair_stats = []  # (max_score, corroborating_chunks, n_own_chunks)
    for q in docs:
        qkey = q["path"]
        q_vec = doc_vectors[qkey]
        if len(q_vec) == 0:
            continue
        for c in docs:
            ckey = c["path"]
            if ckey == qkey or q["category"] == c["category"]:
                continue
            c_vec = doc_vectors[ckey]
            if len(c_vec) == 0:
                continue
            scores = cosine_similarity(q_vec, c_vec)
            max_score = float(scores.max())
            corroborating = int((scores.max(axis=1) >= CORROBORATION_THRESHOLD).sum())
            pair_stats.append((max_score, corroborating, len(q_vec), qkey))
    return pair_stats


def document_level_fpr_at(pair_stats, threshold, use_corroboration):
    by_query = {}
    for max_score, corroborating, n_own, qkey in pair_stats:
        if use_corroboration and n_own >= MIN_CORROBORATING_CHUNKS:
            is_confirmed = max_score >= threshold and corroborating >= MIN_CORROBORATING_CHUNKS
        else:
            is_confirmed = max_score >= threshold
        by_query.setdefault(qkey, False)
        if is_confirmed:
            by_query[qkey] = True
    n_scans = len(by_query)
    n_flagged = sum(1 for v in by_query.values() if v)
    return n_flagged, n_scans, (n_flagged / n_scans if n_scans else 0.0)


def analyze_model(name, model_path, eval_pairs):
    print(f"\n===== {name} =====")
    model = SentenceTransformer(model_path)

    vec_a = model.encode([p["a"] for p in eval_pairs], show_progress_bar=False)
    vec_b = model.encode([p["b"] for p in eval_pairs], show_progress_bar=False)
    sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))
    labels = np.array([p["label"] for p in eval_pairs])

    print("\n-- (A) Bootstrap 95% confidence intervals (n=1000 resamples) --")
    ci = bootstrap_ci(sims, labels, CONFIRMED_THRESHOLD)
    print(f"  AUC = {ci['auc_mean']:.4f}  95% CI [{ci['auc_ci95'][0]:.4f}, {ci['auc_ci95'][1]:.4f}]")
    print(f"  False-positive rate @0.75 = {ci['fp_rate_mean']:.4f}  95% CI "
          f"[{ci['fp_rate_ci95'][0]:.4f}, {ci['fp_rate_ci95'][1]:.4f}]")

    print("\n-- (D) Document-level false-positive simulation (real chunking, real max-per-paper logic) --")
    pair_stats = collect_document_pair_stats(model)
    max_scores = np.array([p[0] for p in pair_stats])
    print(f"  {len(set(p[3] for p in pair_stats))} query documents x cross-category corpus, "
          f"{len(pair_stats)} genuinely-unrelated document-pair comparisons total")
    print(f"  max cross-document chunk-pair score observed: {max_scores.max():.4f} (p95={np.percentile(max_scores,95):.4f})")

    print("\n  Threshold sweep on the DOCUMENT-LEVEL false-accusation rate (the metric that actually matters):")
    print(f"  {'threshold':>9} | {'no-corrob. FPR':>15} | {'w/ corrob. FPR':>15}")
    for t in DOC_THRESHOLD_CANDIDATES:
        _, _, fpr_plain = document_level_fpr_at(pair_stats, t, use_corroboration=False)
        _, _, fpr_corrob = document_level_fpr_at(pair_stats, t, use_corroboration=True)
        marker = " <- current production" if t == CONFIRMED_THRESHOLD else ""
        print(f"  {t:>9.2f} | {fpr_plain*100:>13.1f}% | {fpr_corrob*100:>13.1f}%{marker}")

    return sims, labels


def genuine_paraphrase_subset():
    """The backtranslation-specific positives/negatives inside exp10's training file.
    Fair, unseen-data check for model 9 (never trained on this); for model 10 this subset
    WAS part of its own training data, so it is reported separately and clearly labelled."""
    with open(os.path.join(DATA_DIR, "balanced_train_pairs_v2_backtranslation.json"), encoding="utf-8") as f:
        all_pairs = json.load(f)
    subset = [p for p in all_pairs if p.get("obfuscation") == "backtranslation" or p.get("kind") == "backtranslation-balance"]
    return subset


def main():
    with open(os.path.join(DATA_DIR, "balanced_eval_pairs.json"), encoding="utf-8") as f:
        eval_pairs = json.load(f)

    print("===== (B) Baseline (non-ML) methods on the SAME eval set (easy/hard negatives + obfuscated positives) =====")
    jac = jaccard_scores(eval_pairs)
    tfidf = tfidf_scores(eval_pairs)
    labels = np.array([p["label"] for p in eval_pairs])
    print(f"Jaccard word-overlap:  AUC = {roc_auc_score(labels, jac):.4f}")
    print(f"TF-IDF cosine:         AUC = {roc_auc_score(labels, tfidf):.4f}")

    para_pairs = genuine_paraphrase_subset()
    para_labels = np.array([p["label"] for p in para_pairs])
    print(f"\n===== (B-refined) Baseline methods SPECIFICALLY on genuine-paraphrase-type pairs (n={len(para_pairs)}) =====")
    print("(unseen for model 9; part of model 10's OWN training data - labelled accordingly below)")
    jac_p = jaccard_scores(para_pairs)
    tfidf_p = tfidf_scores(para_pairs)
    print(f"Jaccard word-overlap:  AUC = {roc_auc_score(para_labels, jac_p):.4f}")
    print(f"TF-IDF cosine:         AUC = {roc_auc_score(para_labels, tfidf_p):.4f}")

    for name, model_path, seen in (
        ("Experiment 9 (production, APPROVED-BACKUP)", MODEL_9, "UNSEEN by this model"),
        ("Experiment 10 (backtranslation-augmented)", MODEL_10, "WAS IN this model's own training set - not a fair held-out check"),
    ):
        model = SentenceTransformer(model_path)
        vec_a = model.encode([p["a"] for p in para_pairs], show_progress_bar=False)
        vec_b = model.encode([p["b"] for p in para_pairs], show_progress_bar=False)
        sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))
        print(f"{name} embeddings ({seen}): AUC = {roc_auc_score(para_labels, sims):.4f}")

    analyze_model("Experiment 9 (production, APPROVED-BACKUP)", MODEL_9, eval_pairs)
    analyze_model("Experiment 10 (backtranslation-augmented)", MODEL_10, eval_pairs)


if __name__ == "__main__":
    main()
