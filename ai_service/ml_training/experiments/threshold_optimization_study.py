import os
import json

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics import roc_auc_score, roc_curve

MODELS_ROOT = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments"
MODEL_9 = os.path.join(MODELS_ROOT, "exp9-balanced-domain-APPROVED-BACKUP")
MODEL_10 = os.path.join(MODELS_ROOT, "exp10-backtranslation-augmented")
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"

CANDIDATES = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]



def load_scores(model_path):
    model = SentenceTransformer(model_path)
    with open(os.path.join(DATA_DIR, "balanced_eval_pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)
    vec_a = model.encode([p["a"] for p in pairs], show_progress_bar=False)
    vec_b = model.encode([p["b"] for p in pairs], show_progress_bar=False)
    sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))
    labels = np.array([p["label"] for p in pairs])
    return sims, labels, pairs


def analyze(name, model_path):
    print(f"\n===== {name} =====")
    sims, labels, pairs = load_scores(model_path)
    n_pos = int(labels.sum())
    n_neg = int((labels == 0).sum())
    print(f"held-out eval set: {n_pos} positive pairs, {n_neg} negative pairs (n={len(labels)})")

    auc = roc_auc_score(labels, sims)
    print(f"ROC-AUC = {auc:.6f}")

    fpr, tpr, roc_thresholds = roc_curve(labels, sims)
    j_scores = tpr - fpr
    best_idx = int(np.argmax(j_scores))
    youden_threshold = float(roc_thresholds[best_idx])
    print(f"Youden's J-optimal threshold = {youden_threshold:.4f}  (TPR={tpr[best_idx]:.4f}, FPR={fpr[best_idx]:.4f})")

    neg_scores = sims[labels == 0]
    pos_scores = sims[labels == 1]
    zero_error_min = float(pos_scores.min())
    zero_error_max = float(neg_scores.max())
    print(f"Perfect-separation zone (zero classification error on this eval set): "
          f"any threshold in ({zero_error_max:.4f}, {zero_error_min:.4f}] achieves 100% precision AND 100% recall here")

    print(f"\n{'threshold':>9} | {'false_pos':>9} | {'false_neg':>9} | {'precision':>9} | {'recall':>9} | {'F1':>7}")
    for t in CANDIDATES:
        predicted_pos = sims >= t
        tp = int(((predicted_pos) & (labels == 1)).sum())
        fp = int(((predicted_pos) & (labels == 0)).sum())
        fn = int(((~predicted_pos) & (labels == 1)).sum())
        precision = tp / (tp + fp) if (tp + fp) else float('nan')
        recall = tp / (tp + fn) if (tp + fn) else float('nan')
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else float('nan')
        print(f"{t:>9.2f} | {fp:>9d} | {fn:>9d} | {precision:>9.4f} | {recall:>9.4f} | {f1:>7.4f}")

    return {
        "auc": auc, "youden_threshold": youden_threshold,
        "zero_error_min": zero_error_min, "zero_error_max": zero_error_max,
    }


def main():
    r9 = analyze("Experiment 9 (production, APPROVED-BACKUP)", MODEL_9)
    r10 = analyze("Experiment 10 (backtranslation-augmented)", MODEL_10)
    print("\n===== SUMMARY =====")
    for name, r in (("exp9", r9), ("exp10", r10)):
        print(f"{name}: AUC={r['auc']:.4f}, Youden-optimal={r['youden_threshold']:.4f}, "
              f"zero-error-zone=({r['zero_error_max']:.4f}, {r['zero_error_min']:.4f}]")


if __name__ == "__main__":
    main()
