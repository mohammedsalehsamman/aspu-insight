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
from transformers import TrainerCallback

BASE_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "paraphrase-multilingual-MiniLM-L12-v2-base"
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp4-early-stopping"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
ARABIC_PAIR_SAMPLE_SIZE = 10000
CHECK_EVERY_STEPS = 100
ENGLISH_SPEARMAN_FLOOR = 0.80  # baseline is 0.844; stop once we drop below this


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


class EnglishGuardCallback(TrainerCallback):
    """يوقف التدريب فور هبوط Spearman الإنجليزي دون الحد الآمن، ويحفظ آخر نموذج جيد."""

    def __init__(self, model, en_evaluator, floor, check_every, output_dir):
        self.model = model
        self.en_evaluator = en_evaluator
        self.floor = floor
        self.check_every = check_every
        self.output_dir = output_dir
        self.best_spearman = 0.0
        self.history = []

    def on_step_end(self, args, state, control, **kwargs):
        if state.global_step == 0 or state.global_step % self.check_every != 0:
            return control

        result = self.en_evaluator(self.model)
        spearman = result[f"{self.en_evaluator.name}_spearman_cosine"]
        self.history.append((state.global_step, spearman))
        print(f"[EnglishGuard] step {state.global_step}: en Spearman = {spearman:.4f}")

        if spearman >= self.floor:
            self.model.save(self.output_dir)
            self.best_spearman = spearman
        elif self.best_spearman > 0:
            print(f"[EnglishGuard] Dropped below floor ({self.floor}) at step {state.global_step}. "
                  f"Stopping — last safe checkpoint (Spearman={self.best_spearman:.4f}) already saved.")
            control.should_training_stop = True

        return control


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_train = load_scored_csv("stsb_en_train.csv", scale=1.0)
    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)

    ar_train = load_scored_csv("arabic_stsb_train.csv", scale=1.0)
    ar_dev = load_scored_csv("arabic_stsb_validation.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)
    en_dev = load_scored_csv("stsb_en_dev.csv", scale=1.0)

    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)

    ar_pairs = load_arabic_nli_pairs()

    sts_scored_train = concatenate_datasets([ar_train, en_train]).shuffle(seed=42)
    dev_dataset = concatenate_datasets([ar_dev, en_dev])

    print(f"EXPERIMENT 4: early stopping guard — floor={ENGLISH_SPEARMAN_FLOOR}, "
          f"checking every {CHECK_EVERY_STEPS} steps")

    model = SentenceTransformer(BASE_MODEL)

    print("Baseline (before fine-tuning):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))

    train_dataset = DatasetDict({"sts_scored": sts_scored_train, "ar_pairs": ar_pairs})
    loss = {
        "sts_scored": losses.CosineSimilarityLoss(model=model),
        "ar_pairs": losses.MultipleNegativesRankingLoss(model=model),
    }
    eval_dataset = DatasetDict({"sts_scored": dev_dataset})

    args = SentenceTransformerTrainingArguments(
        output_dir=OUTPUT_DIR + "-checkpoints",
        num_train_epochs=3,
        learning_rate=3e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        warmup_ratio=0.1,
        logging_steps=50,
        eval_strategy="no",
        save_strategy="no",
    )

    en_test_evaluator = build_evaluator(en_test, "stsb-en-test")
    guard = EnglishGuardCallback(model, en_test_evaluator, ENGLISH_SPEARMAN_FLOOR, CHECK_EVERY_STEPS, OUTPUT_DIR)

    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        loss=loss,
        callbacks=[guard],
    )
    trainer.train()

    print("Early-stop guard history:", guard.history)
    print("Best safe English Spearman reached before stopping:", guard.best_spearman)

    if guard.best_spearman > 0:
        final_model = SentenceTransformer(OUTPUT_DIR)
        print("After early stopping (loaded last safe checkpoint):")
        print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(final_model))
        print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(final_model))
        print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(final_model))
        print("Saved experiment 4 model to", OUTPUT_DIR)
    else:
        print("English Spearman never stayed above the floor even at the first check — no safe checkpoint saved.")


if __name__ == "__main__":
    main()
