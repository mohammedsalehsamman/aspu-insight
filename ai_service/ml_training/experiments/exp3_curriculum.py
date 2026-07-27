import os

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

# يبدأ من نتيجة التجربة 1 (STS فقط) بدل الموديل الأساس — المرحلة الأولى من المنهج
# التدريجي أُنجزت هناك بالفعل؛ هذه المرحلة الثانية فقط تضيف تعرّضاً محدوداً جداً لـ
# Arabic-NLi-Pair (300 خطوة فقط، وليس عصراً كاملاً) بمعدل تعلّم منخفض جداً.
STAGE1_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp1-sts-only"
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp3-curriculum"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
LIMITED_STEPS = 300
ARABIC_PAIR_SAMPLE_SIZE = 10000


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


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)
    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)
    ar_dev = load_scored_csv("arabic_stsb_validation.csv", scale=1.0)

    ar_pairs = load_arabic_nli_pairs()

    print(f"EXPERIMENT 3: curriculum stage 2 — {LIMITED_STEPS} steps of Arabic-NLi-Pair only, "
          f"continuing from stage-1 (STS-only) checkpoint")

    model = SentenceTransformer(STAGE1_MODEL)

    print("Baseline (stage-1 STS-only model, before stage 2):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))

    loss = losses.MultipleNegativesRankingLoss(model=model)

    args = SentenceTransformerTrainingArguments(
        output_dir=OUTPUT_DIR + "-checkpoints",
        max_steps=LIMITED_STEPS,
        learning_rate=1e-5,
        per_device_train_batch_size=16,
        warmup_ratio=0.1,
        logging_steps=50,
        save_strategy="no",
    )

    trainer = SentenceTransformerTrainer(
        model=model,
        args=args,
        train_dataset=ar_pairs,
        loss=loss,
    )
    trainer.train()

    print("After stage 2 (limited Arabic-NLi-Pair exposure):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    print("  ar Spearman (STS17 ar-ar):", build_evaluator(sts17_ar, "sts17-ar-ar-test")(model))

    model.save(OUTPUT_DIR)
    print("Saved experiment 3 model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
