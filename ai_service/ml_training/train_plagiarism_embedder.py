import os

os.environ.setdefault("HF_HUB_OFFLINE", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aspu_insight.settings")
django.setup()

import torch
from datasets import Dataset, concatenate_datasets, load_dataset
from sentence_transformers import (
    SentenceTransformer,
    SentenceTransformerTrainer,
    SentenceTransformerTrainingArguments,
    losses,
)
from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator

BASE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "ml_models", "plagiarism-embedder-finetuned"
)


def load_stsb_multi(lang):
    ds = load_dataset("PhilipMay/stsb_multi_mt", lang)
    return {
        split: Dataset.from_dict({
            "sentence1": ds[split]["sentence1"],
            "sentence2": ds[split]["sentence2"],
            "label": [s / 5.0 for s in ds[split]["similarity_score"]],
        })
        for split in ("train", "dev", "test")
    }


def load_arabic_stsb():
    ds = load_dataset("Omartificial-Intelligence-Space/Arabic-stsb")
    return {
        "train": Dataset.from_dict({
            "sentence1": ds["train"]["sentence1"],
            "sentence2": ds["train"]["sentence2"],
            "label": [float(s) for s in ds["train"]["score"]],
        }),
        "dev": Dataset.from_dict({
            "sentence1": ds["validation"]["sentence1"],
            "sentence2": ds["validation"]["sentence2"],
            "label": [float(s) for s in ds["validation"]["score"]],
        }),
        "test": Dataset.from_dict({
            "sentence1": ds["test"]["sentence1"],
            "sentence2": ds["test"]["sentence2"],
            "label": [float(s) for s in ds["test"]["score"]],
        }),
    }


def build_evaluator(dataset, name):
    return EmbeddingSimilarityEvaluator(
        sentences1=dataset["sentence1"],
        sentences2=dataset["sentence2"],
        scores=dataset["label"],
        name=name,
    )


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en = load_stsb_multi("en")
    ar = load_arabic_stsb()

    train_dataset = concatenate_datasets([en["train"], ar["train"]]).shuffle(seed=42)
    dev_dataset = concatenate_datasets([en["dev"], ar["dev"]])

    model = SentenceTransformer(BASE_MODEL)

    baseline_en = build_evaluator(en["test"], "stsb-en-test").__call__(model)
    baseline_ar = build_evaluator(ar["test"], "arabic-stsb-test").__call__(model)
    print("Baseline (before fine-tuning):")
    print("  en Spearman:", baseline_en)
    print("  ar Spearman:", baseline_ar)

    loss = losses.CosineSimilarityLoss(model=model)

    args = SentenceTransformerTrainingArguments(
        output_dir=OUTPUT_DIR + "-checkpoints",
        num_train_epochs=3,
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

    final_en = build_evaluator(en["test"], "stsb-en-test").__call__(model)
    final_ar = build_evaluator(ar["test"], "arabic-stsb-test").__call__(model)
    print("After fine-tuning:")
    print("  en Spearman:", final_en)
    print("  ar Spearman:", final_ar)

    model.save(OUTPUT_DIR)
    print("Saved fine-tuned model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
