import os
import json

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd
import torch
from datasets import Dataset
from sentence_transformers import (
    SentenceTransformer,
    SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
    losses,
)
from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator

BASE_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "paraphrase-multilingual-MiniLM-L12-v2-base"
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp8-domain-specific"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"

# Real academic plagiarism pairs (ExAraCorpusPAN2015 Training split: exact copies +
# artificial/simulated paraphrase obfuscation), instead of generic STS/NLI data.
TRAIN_PAIRS_PATH = os.path.join(DATA_DIR, "domain_train_pairs.json")
EVAL_PAIRS_PATH = os.path.join(DATA_DIR, "domain_eval_pairs_heldout.json")


def load_scored_csv(filename, scale=1.0):
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
        sentences1=dataset["sentence1"],
        sentences2=dataset["sentence2"],
        scores=dataset["label"],
        name=name,
    )


def load_domain_train():
    with open(TRAIN_PAIRS_PATH, encoding="utf-8") as f:
        pairs = json.load(f)
    return Dataset.from_dict({
        "anchor": [p["a"] for p in pairs],
        "positive": [p["b"] for p in pairs],
    })


def evaluate_domain(model, name):
    import numpy as np
    from sklearn.metrics import roc_auc_score

    with open(EVAL_PAIRS_PATH, encoding="utf-8") as f:
        pairs = json.load(f)
    labels = np.array([p["label"] for p in pairs])
    vec_a = model.encode([p["a"] for p in pairs], show_progress_bar=False)
    vec_b = model.encode([p["b"] for p in pairs], show_progress_bar=False)
    sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))
    pos_mean, neg_mean = sims[labels == 1].mean(), sims[labels == 0].mean()
    auc = roc_auc_score(labels, sims)
    print(f"{name} — domain eval (held-out, {len(pairs)} pairs): "
          f"pos_sim={pos_mean:.4f} neg_sim={neg_mean:.4f} margin={pos_mean-neg_mean:.4f} AUC={auc:.4f}")


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)
    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)

    domain_train = load_domain_train()
    print(f"EXPERIMENT 8: domain-specific training on {len(domain_train)} real academic plagiarism pairs "
          f"(ExAraCorpusPAN2015 Training split — exact copies + artificial + simulated obfuscation)")

    model = SentenceTransformer(BASE_MODEL)

    print("Baseline (before fine-tuning):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))
    evaluate_domain(model, "Baseline")

    loss = losses.MultipleNegativesRankingLoss(model=model)
    args = SentenceTransformerTrainingArguments(
        output_dir=OUTPUT_DIR + "-checkpoints",
        num_train_epochs=4,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        warmup_ratio=0.1,
        logging_steps=20,
        eval_strategy="no",
        save_strategy="no",
    )
    trainer = SentenceTransformerTrainer(
        model=model, args=args, train_dataset=domain_train, loss=loss,
    )
    trainer.train()

    print("After domain-specific fine-tuning:")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))
    evaluate_domain(model, "After fine-tuning")

    model.save(OUTPUT_DIR)
    print("Saved experiment 8 model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
