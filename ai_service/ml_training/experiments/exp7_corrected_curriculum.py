import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd
import torch
from datasets import Dataset, concatenate_datasets
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
STAGE1_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp7-stage1-short"
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp7-curriculum-corrected"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
ARABIC_PAIR_SAMPLE_SIZE = 10000

# Experiment 4 showed English damage starts between step 100-200 on this same data mix.
# Stage 1 here is deliberately capped well before that window, unlike Experiment 3 which
# reused a full 2-epoch (1,438-step) run that had already collapsed English on its own.
STAGE1_MAX_STEPS = 150
STAGE2_MAX_STEPS = 300
STAGE2_LR = 1e-5


def load_scored_csv(filename, scale=1.0):
    df = pd.read_csv(os.path.join(DATA_DIR, filename))
    score_col = next(c for c in ("label", "score", "similarity_score") if c in df.columns)
    labels = [float(s) / scale for s in df[score_col]]
    return Dataset.from_dict({
        "sentence1": df["sentence1"].tolist(),
        "sentence2": df["sentence2"].tolist(),
        "label": labels,
    })


def load_arabic_nli_pairs(sample_size=ARABIC_PAIR_SAMPLE_SIZE):
    path = os.path.join(DATA_DIR, "arabic_nli_pair_train.csv")
    df = pd.read_csv(path)
    if len(df) > sample_size:
        df = df.sample(n=sample_size, random_state=42)
    return Dataset.from_dict({
        "anchor": df["anchor"].tolist(),
        "positive": df["positive"].tolist(),
    })


def build_evaluator(dataset, name):
    return EmbeddingSimilarityEvaluator(
        sentences1=dataset["sentence1"],
        sentences2=dataset["sentence2"],
        scores=dataset["label"],
        name=name,
    )


def report(model, en_test, ar_test, sts17_ar, label):
    print(label)
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_train = load_scored_csv("stsb_en_train.csv", scale=1.0)
    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)
    ar_train = load_scored_csv("arabic_stsb_train.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)
    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)
    ar_pairs = load_arabic_nli_pairs()

    sts_scored_train = concatenate_datasets([ar_train, en_train]).shuffle(seed=42)

    print(f"EXPERIMENT 7: corrected curriculum — stage 1 capped at {STAGE1_MAX_STEPS} steps (STS-only), "
          f"stage 2 up to {STAGE2_MAX_STEPS} steps (Arabic-NLi-Pair only, lr={STAGE2_LR})")

    model = SentenceTransformer(BASE_MODEL)
    report(model, en_test, ar_test, sts17_ar, "Baseline (before any training):")

    # ---- Stage 1: short, genuinely safe STS-only phase ----
    stage1_loss = losses.CosineSimilarityLoss(model=model)
    stage1_args = SentenceTransformerTrainingArguments(
        output_dir=STAGE1_DIR + "-checkpoints",
        max_steps=STAGE1_MAX_STEPS,
        learning_rate=3e-5,
        per_device_train_batch_size=16,
        warmup_ratio=0.1,
        logging_steps=50,
        eval_strategy="no",
        save_strategy="no",
    )
    stage1_trainer = SentenceTransformerTrainer(
        model=model, args=stage1_args, train_dataset=sts_scored_train, loss=stage1_loss,
    )
    stage1_trainer.train()
    model.save(STAGE1_DIR)
    report(model, en_test, ar_test, sts17_ar, f"After stage 1 ({STAGE1_MAX_STEPS} steps, STS-only):")

    # ---- Stage 2: limited Arabic-NLi-Pair exposure, low LR ----
    stage2_loss = losses.MultipleNegativesRankingLoss(model=model)
    stage2_args = SentenceTransformerTrainingArguments(
        output_dir=OUTPUT_DIR + "-checkpoints",
        max_steps=STAGE2_MAX_STEPS,
        learning_rate=STAGE2_LR,
        per_device_train_batch_size=16,
        warmup_ratio=0.1,
        logging_steps=50,
        eval_strategy="no",
        save_strategy="no",
    )
    stage2_trainer = SentenceTransformerTrainer(
        model=model, args=stage2_args, train_dataset=ar_pairs, loss=stage2_loss,
    )
    stage2_trainer.train()

    report(model, en_test, ar_test, sts17_ar, f"After stage 2 ({STAGE2_MAX_STEPS} steps, Arabic-NLi-Pair):")
    model.save(OUTPUT_DIR)
    print("Saved experiment 7 model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
