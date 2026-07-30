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
    os.path.dirname(__file__), "..", "..", "ml_models", "experiments", "exp10-backtranslation-augmented"
)
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
TRAIN_FILE = "balanced_train_pairs_v2_backtranslation.json"


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


def load_train():
    with open(os.path.join(DATA_DIR, TRAIN_FILE), encoding="utf-8") as f:
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
    print(f"{label} — OVERALL (held-out domain eval): pos_sim={pos_mean:.4f} AUC={auc:.4f}")

    for kind in ("hard", "easy"):
        idx = [i for i, p in enumerate(pairs) if p.get("kind") == kind]
        if idx:
            print(f"  neg[{kind}] mean_sim={sims[idx].mean():.4f} (n={len(idx)})")
    for obf in set(p.get("obfuscation", "") for p in pairs if p["label"] == 1):
        idx = [i for i, p in enumerate(pairs) if p["label"] == 1 and p.get("obfuscation", "") == obf]
        if idx:
            print(f"  pos[{obf or 'unlabeled'}] mean_sim={sims[idx].mean():.4f} (n={len(idx)})")
    return auc


def evaluate_genuine_paraphrase_test(model, label):
    """Same 3 genuinely-paraphrased-paragraph test used earlier this session, re-run against the new model."""
    paragraphs = [
        ("يتناول هذا البحث نماذج المحوّلات وتطبيقها في تصنيف النصوص. تُقيَّم هذه النماذج على مجموعات بيانات مرجعية معروفة. "
         "الهدف هو دراسة أداء المحوّلات في مهام التصنيف النصي. النتائج تُظهِر فعالية هذه النماذج في التصنيف. "
         "تُعَد المحوّلات من أهم التقنيات الحديثة في معالجة اللغة. هذه الدراسة تسهم في فهم أعمق لتصنيف النصوص."),
        ("يستعرض هذا الجزء آلية عمل نظام يعتمد على أكثر من نموذج واحد للتعرف على الانتحال. "
         "يتم الاختيار بين النماذج بناءً على تحديد اللغة تلقائياً بواسطة النظام. "
         "هذا الأسلوب يهدف لتحسين الدقة حسب لغة النص المُدخَل. التبديل بين النماذج يحدث دون تدخّل بشري مباشر. "
         "الفكرة تجريبية وتخضع للتقييم المستمر. يُعتبر هذا النهج جزءاً من تطوير النظام ككل."),
        ("هذا الجزء يشرح كيفية احتساب التمثيل الرقمي للنص فور رفعه. "
         "تتم هذه العملية بشكل تلقائي دون تدخّل المستخدم عبر مهمة مجدولة. "
         "يُستخدَم Celery لتنفيذ هذه المهمة في الخلفية بلا تعطيل الواجهة. هذا يضمن استجابة سريعة للمستخدم أثناء الرفع. "
         "تخزين المتجه يتم فور اكتمال الحساب. هذا الإجراء جزء أساسي من خط أنابيب المعالجة."),
    ]
    originals = [
        "دراسة حول نماذج المحوّلات (Transformers) في تصنيف النصوص وتقييمها على مجموعات بيانات مرجعية.",
        "هذا بحث تجريبي عربي للتحقق من عمل نظام كشف الانتحال بموديلين مختلفين حسب اللغة المكتشفة تلقائياً.",
        "بحث تجريبي للتحقق من حساب المتجه تلقائياً عبر Celery عند الرفع.",
    ]
    vec_p = model.encode(paragraphs, show_progress_bar=False)
    vec_o = model.encode(originals, show_progress_bar=False)
    print(f"{label} — genuine-paraphrase spot check (same 3 paragraphs from this session):")
    for i in range(3):
        sim = float(np.dot(vec_p[i], vec_o[i]) / (np.linalg.norm(vec_p[i]) * np.linalg.norm(vec_o[i])))
        print(f"  paragraph {i+1} vs its true source: {sim:.4f}")


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    en_test = load_scored_csv("stsb_en_test.csv", scale=1.0)
    ar_test = load_scored_csv("arabic_stsb_test.csv", scale=1.0)
    sts17_ar = load_scored_csv("sts17_ar_ar_test.csv", scale=5.0)

    train_data = load_train()
    print(f"EXPERIMENT 10: balanced domain data + 126 back-translation paraphrase pairs "
          f"(+126 matching new negatives) — {len(train_data)} training pairs")

    model = SentenceTransformer(BASE_MODEL)

    print("Baseline (before fine-tuning):")
    print("  en Spearman:", build_evaluator(en_test, "stsb-en-test")(model))
    print("  ar Spearman (Arabic-STSb):", build_evaluator(ar_test, "arabic-stsb-test")(model))
    evaluate_balanced(model, "Baseline")
    evaluate_genuine_paraphrase_test(model, "Baseline")

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
    evaluate_genuine_paraphrase_test(model, "After fine-tuning")

    model.save(OUTPUT_DIR)
    print("Saved experiment 10 model to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
