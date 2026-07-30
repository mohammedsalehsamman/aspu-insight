import os
import re
import json

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MODEL_9 = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments\exp9-balanced-domain-APPROVED-BACKUP"
MODEL_10 = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments\exp10-backtranslation-augmented"
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
REFERENCE_PATH = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\commonness_reference_arpd.npy"

CONFIRMED_THRESHOLD = 0.75
COMMONNESS_THRESHOLD_CANDIDATES = [0.60, 0.75, 0.85, 0.90, 0.92, 0.95, 0.97]
COMMONNESS_MAX_COUNT_CANDIDATES = [5, 20, 50]


def evaluate(name, model_path, pairs):
    model = SentenceTransformer(model_path)
    reference_pool = np.load(REFERENCE_PATH)
    print(f"reference pool size: {len(reference_pool)}")

    positives = [p for p in pairs if p["label"] == 1]
    vec_a = model.encode([p["a"] for p in positives], show_progress_bar=False)
    vec_b = model.encode([p["b"] for p in positives], show_progress_bar=False)
    sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))
    was_confirmed = sims >= CONFIRMED_THRESHOLD

    print(f"\n===== {name}: commonness-count distribution across candidate similarity thresholds =====")
    print(f"  {len(positives)} known REAL positive (plagiarism/obfuscated) pairs, all currently confirmed (100%)")
    for t in COMMONNESS_THRESHOLD_CANDIDATES:
        commonness_counts = np.array([
            int((cosine_similarity(vec_a[i].reshape(1, -1), reference_pool)[0] >= t).sum())
            for i in range(len(positives))
        ])
        row = f"  threshold={t:.2f}: mean={commonness_counts.mean():.1f} median={int(np.median(commonness_counts))} " \
              f"p90={int(np.percentile(commonness_counts,90))} max={commonness_counts.max()}  |  recall at max_count="
        for max_count in COMMONNESS_MAX_COUNT_CANDIDATES:
            still_confirmed = was_confirmed & (commonness_counts <= max_count)
            row += f" {max_count}:{100*still_confirmed.sum()/len(positives):.0f}%"
        print(row)


def main():
    with open(os.path.join(DATA_DIR, "balanced_eval_pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)
    evaluate("Experiment 9 (production)", MODEL_9, pairs)
    evaluate("Experiment 10", MODEL_10, pairs)


if __name__ == "__main__":
    main()
