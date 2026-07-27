import os
import json

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics import roc_auc_score

MODELS_ROOT = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models"
MODELS = {
    "Base (untouched)": os.path.join(MODELS_ROOT, "paraphrase-multilingual-MiniLM-L12-v2-base"),
    "Exp1 (STS-only)": os.path.join(MODELS_ROOT, "experiments", "exp1-sts-only"),
    "Exp2 (frozen 75%)": os.path.join(MODELS_ROOT, "experiments", "exp2-frozen-layers"),
    "Exp4 (early-stop)": os.path.join(MODELS_ROOT, "experiments", "exp4-early-stopping"),
    "Exp5 (frozen 50%)": os.path.join(MODELS_ROOT, "experiments", "exp5-lighter-freezing"),
}

DATA_PATH = r"C:\Users\hp\Desktop\plagiarism-training-data\domain_eval_pairs.json"


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        pairs = json.load(f)

    labels = np.array([p["label"] for p in pairs])
    print(f"Domain-specific evaluation set: {sum(labels)} real plagiarism pairs, {len(labels)-sum(labels)} unrelated pairs\n")

    results = {}
    for name, path in MODELS.items():
        if not os.path.exists(path):
            print(f"SKIP {name}: not found at {path}")
            continue
        model = SentenceTransformer(path)
        vec_a = model.encode([p["a"] for p in pairs], show_progress_bar=False)
        vec_b = model.encode([p["b"] for p in pairs], show_progress_bar=False)
        sims = np.sum(vec_a * vec_b, axis=1) / (
            np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1)
        )

        pos_mean = sims[labels == 1].mean()
        neg_mean = sims[labels == 0].mean()
        margin = pos_mean - neg_mean
        auc = roc_auc_score(labels, sims)
        acc_at_05 = ((sims >= 0.5).astype(int) == labels).mean()

        results[name] = {
            "pos_mean": float(pos_mean), "neg_mean": float(neg_mean),
            "margin": float(margin), "auc": float(auc), "acc_at_0.5": float(acc_at_05),
        }
        print(f"{name}: pos_sim={pos_mean:.4f} neg_sim={neg_mean:.4f} margin={margin:.4f} "
              f"AUC={auc:.4f} acc@0.5={acc_at_05:.4f}")

    out_path = r"C:\Users\hp\Desktop\plagiarism-training-data\domain_eval_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved results to", out_path)


if __name__ == "__main__":
    main()
