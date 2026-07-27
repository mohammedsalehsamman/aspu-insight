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
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp1-sts-only"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"


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


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_train = load_scored_csv("stsb_en_train.csv", scale=1.0)
    en_dev = load_scored_csv("stsb_en_dev.csv", scale=1.0)
    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)

    ar_train = load_scored_csv("arabic_stsb_train.csv", scale=1.0)
    ar_dev = load_scored_csv("arabic_stsb_validation.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)

    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)

    train_dataset = concatenate_datasets([ar_train, en_train]).shuffle(seed=42)
    dev_dataset = concatenate_datasets([ar_dev, en_dev])

    print(f"EXPERIMENT 1: STS-only, no Arabic-NLi-Pair. Train rows/epoch: {len(train_dataset)}")

    model = SentenceTransformer(BASE_MODEL)

    print("Baseline (before fine-tuning):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))

    loss = losses.CosineSimilarityLoss(model=model)

    args = SentenceTransformerTrainingArguments(
        output_dir=OUTPUT_DIR + "-checkpoints",
        num_train_epochs=2,
        learning_rate=3e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        warmup_ratio=0.1,
        logging_steps=50,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
    )

    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=dev_dataset,
        loss=loss,
        evaluator=build_evaluator(dev_dataset, "dev"),
    )
    trainer.train()

    print("After fine-tuning:")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))

    model.save(OUTPUT_DIR)
    print("Saved experiment 1 model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
