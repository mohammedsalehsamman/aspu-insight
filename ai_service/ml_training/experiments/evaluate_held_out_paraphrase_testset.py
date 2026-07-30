import os
import json

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer

MODELS_ROOT = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments"
MODEL_9 = os.path.join(MODELS_ROOT, "exp9-balanced-domain-APPROVED-BACKUP")
MODEL_10 = os.path.join(MODELS_ROOT, "exp10-backtranslation-augmented")
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"

CONFIRMED_THRESHOLD = 0.75
SUSPECTED_THRESHOLD = 0.25


def evaluate(name, model_path, pairs):
    model = SentenceTransformer(model_path)
    vec_a = model.encode([p["a"] for p in pairs], show_progress_bar=False)
    vec_b = model.encode([p["b"] for p in pairs], show_progress_bar=False)
    sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))

    confirmed = int((sims >= CONFIRMED_THRESHOLD).sum())
    suspected = int(((sims >= SUSPECTED_THRESHOLD) & (sims < CONFIRMED_THRESHOLD)).sum())
    missed = int((sims < SUSPECTED_THRESHOLD).sum())

    print(f"\n===== {name} on held-out genuine-paraphrase test set (n={len(pairs)}) =====")
    print(f"  mean={sims.mean():.4f}  median={np.median(sims):.4f}  min={sims.min():.4f}  max={sims.max():.4f}")
    print(f"  p25={np.percentile(sims,25):.4f}  p75={np.percentile(sims,75):.4f}")
    print(f"  confirmed (>=0.75): {confirmed}/{len(pairs)} ({100*confirmed/len(pairs):.1f}%)")
    print(f"  suspected (0.25-0.75): {suspected}/{len(pairs)} ({100*suspected/len(pairs):.1f}%)")
    print(f"  missed entirely (<0.25): {missed}/{len(pairs)} ({100*missed/len(pairs):.1f}%)")
    return sims


def main():
    with open(os.path.join(DATA_DIR, "held_out_paraphrase_testset.json"), encoding="utf-8") as f:
        pairs = json.load(f)
    print(f"Loaded {len(pairs)} independent held-out genuine-paraphrase pairs (NOT used in exp9 or exp10 training)")

    evaluate("Experiment 9 (production)", MODEL_9, pairs)
    evaluate("Experiment 10 (backtranslation-augmented)", MODEL_10, pairs)


if __name__ == "__main__":
    main()
