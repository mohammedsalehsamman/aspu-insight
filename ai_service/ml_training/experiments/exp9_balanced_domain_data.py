import os
import json

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import torch
from datasets import Dataset
from sentence_transformers import (
    SentenceTransformer,
    SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
    losses,
)
from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
from sklearn.metrics import roc_auc_score

BASE_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "paraphrase-multilingual-MiniLM-L12-v2-base"
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp9-balanced-domain"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"


def load_scored_csv(filename, scale=1.0):
    import pandas as pd
    df = pd.read_csv(os.path.join(DATA_DIR, filename))
    score_col = next(c for c in ("label", "score", "similarity_score") if c in df.columns)
    labels = [float(s) / scale for s in df[score_col]]
    return Dataset.from_dict({
        "sentence1": df["sentence1"].tolist(),
        "sentence2": df["sentence2"].tolist(),
        "label": labels,
    })


def build_evaluator(dataset, name):
    return EmbeddingSimilarityEvaluator(
        sentences1=dataset["sentence1"], sentences2=dataset["sentence2"],
        scores=dataset["label"], name=name,
    )


def load_balanced_train():
    with open(os.path.join(DATA_DIR, "balanced_train_pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)
    return Dataset.from_dict({
        "sentence1": [p["a"] for p in pairs],
        "sentence2": [p["b"] for p in pairs],
        "label": [float(p["label"]) for p in pairs],
    })


def evaluate_balanced(model, label):
    with open(os.path.join(DATA_DIR, "balanced_eval_pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)
    labels = np.array([p["label"] for p in pairs])
    vec_a = model.encode([p["a"] for p in pairs], show_progress_bar=False)
    vec_b = model.encode([p["b"] for p in pairs], show_progress_bar=False)
    sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))

    auc = roc_auc_score(labels, sims)
    pos_mean = sims[labels == 1].mean()
    print(f"{label} — OVERALL: pos_sim={pos_mean:.4f} AUC={auc:.4f}")

    for kind in ("hard", "easy"):
        idx = [i for i, p in enumerate(pairs) if p.get("kind") == kind]
        if idx:
            print(f"  neg[{kind}] mean_sim={sims[idx].mean():.4f} (n={len(idx)})")

    for obf in set(p.get("obfuscation", "") for p in pairs if p["label"] == 1):
        idx = [i for i, p in enumerate(pairs) if p["label"] == 1 and p.get("obfuscation", "") == obf]
        if idx:
            print(f"  pos[{obf or 'unlabeled'}] mean_sim={sims[idx].mean():.4f} (n={len(idx)})")
    return auc


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)
    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)

    train_data = load_balanced_train()
    print(f"EXPERIMENT 9: balanced domain data (ARPD length-matched hard+easy negatives, "
          f"oversampled real paraphrase positives) — {len(train_data)} training pairs")

    model = SentenceTransformer(BASE_MODEL)

    print("Baseline (before fine-tuning):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    evaluate_balanced(model, "Baseline")

    loss = losses.CosineSimilarityLoss(model=model)
    args = SentenceTransformerTrainingArguments(
        output_dir=OUTPUT_DIR + "-checkpoints",
        num_train_epochs=3,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        warmup_ratio=0.1,
        logging_steps=50,
        eval_strategy="no",
        save_strategy="no",
    )
    trainer = SentenceTransformerTrainer(model=model, args=args, train_dataset=train_data, loss=loss)
    trainer.train()

    print("After fine-tuning:")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))
    evaluate_balanced(model, "After fine-tuning")

    model.save(OUTPUT_DIR)
    print("Saved experiment 9 model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
