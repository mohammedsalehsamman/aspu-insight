import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import pandas as pd
import torch
from datasets import Dataset, DatasetDict, concatenate_datasets
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
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp5-lighter-freezing"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
ARABIC_PAIR_SAMPLE_SIZE = 10000
NUM_FROZEN_LAYERS = 6  # out of 12 — half frozen, half trainable (lighter than Experiment 2's 9/12)


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


def freeze_lower_layers(model, num_frozen):
    auto_model = model[0].auto_model
    for param in auto_model.embeddings.parameters():
        param.requires_grad = False
    frozen_count = 0
    for i, layer in enumerate(auto_model.encoder.layer):
        if i < num_frozen:
            for param in layer.parameters():
                param.requires_grad = False
            frozen_count += 1
    total = len(auto_model.encoder.layer)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Frozen embeddings + {frozen_count}/{total} encoder layers. "
          f"Trainable params: {trainable:,} / {total_params:,} ({100*trainable/total_params:.1f}%)")


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_train = load_scored_csv("stsb_en_train.csv", scale=1.0)
    en_dev = load_scored_csv("stsb_en_dev.csv", scale=1.0)
    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)

    ar_train = load_scored_csv("arabic_stsb_train.csv", scale=1.0)
    ar_dev = load_scored_csv("arabic_stsb_validation.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)

    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)

    ar_pairs = load_arabic_nli_pairs()

    sts_scored_train = concatenate_datasets([ar_train, en_train]).shuffle(seed=42)
    dev_dataset = concatenate_datasets([ar_dev, en_dev])

    print(f"EXPERIMENT 5: lighter frozen layers ({NUM_FROZEN_LAYERS}/12) + full Arabic-NLi-Pair sample ({len(ar_pairs)})")

    model = SentenceTransformer(BASE_MODEL)
    freeze_lower_layers(model, NUM_FROZEN_LAYERS)

    print("Baseline (before fine-tuning):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))

    train_dataset = DatasetDict({
        "sts_scored": sts_scored_train,
        "ar_pairs": ar_pairs,
    })
    loss = {
        "sts_scored": losses.CosineSimilarityLoss(model=model),
        "ar_pairs": losses.MultipleNegativesRankingLoss(model=model),
    }
    eval_dataset = DatasetDict({"sts_scored": dev_dataset})

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
        eval_dataset=eval_dataset,
        loss=loss,
        evaluator=build_evaluator(dev_dataset, "dev"),
    )
    trainer.train()

    print("After fine-tuning:")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))

    model.save(OUTPUT_DIR)
    print("Saved experiment 5 model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
