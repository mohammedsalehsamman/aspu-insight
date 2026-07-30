import os
import json

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
from sentence_transformers import SentenceTransformer

MODELS_ROOT = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models\experiments"
MODEL_9 = os.path.join(MODELS_ROOT, "exp9-balanced-domain-APPROVED-BACKUP")
MODEL_10 = os.path.join(MODELS_ROOT, "exp10-backtranslation-augmented")
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"

GENUINE_PARAGRAPHS = [
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
GENUINE_ORIGINALS = [
    "دراسة حول نماذج المحوّلات (Transformers) في تصنيف النصوص وتقييمها على مجموعات بيانات مرجعية.",
    "هذا بحث تجريبي عربي للتحقق من عمل نظام كشف الانتحال بموديلين مختلفين حسب اللغة المكتشفة تلقائياً.",
    "بحث تجريبي للتحقق من حساب المتجه تلقائياً عبر Celery عند الرفع.",
]


def cos(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def evaluate_model(name, path):
    print(f"\n===== {name} =====")
    model = SentenceTransformer(path)

    with open(os.path.join(DATA_DIR, "balanced_eval_pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)

    vec_a = model.encode([p["a"] for p in pairs], show_progress_bar=False)
    vec_b = model.encode([p["b"] for p in pairs], show_progress_bar=False)
    sims = np.sum(vec_a * vec_b, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b, axis=1))
    labels = np.array([p["label"] for p in pairs])

    for kind in ("hard", "easy"):
        idx = [i for i, p in enumerate(pairs) if p.get("kind") == kind]
        if idx:
            arr = sims[idx]
            print(f"  neg[{kind}]  mean={arr.mean():.4f}  p95={np.percentile(arr, 95):.4f}  max={arr.max():.4f}  (n={len(idx)})")

    pos_idx = [i for i in range(len(pairs)) if labels[i] == 1]
    pos_arr = sims[pos_idx]
    print(f"  pos[all obfuscation]  mean={pos_arr.mean():.4f}  p5={np.percentile(pos_arr, 5):.4f}  min={pos_arr.min():.4f}  (n={len(pos_idx)})")

    vec_p = model.encode(GENUINE_PARAGRAPHS, show_progress_bar=False)
    vec_o = model.encode(GENUINE_ORIGINALS, show_progress_bar=False)
    print("  genuine-paraphrase spot check (real, hand-verified pairs):")
    genuine_scores = []
    for i in range(3):
        s = cos(vec_p[i], vec_o[i])
        genuine_scores.append(s)
        print(f"    paragraph {i+1}: {s:.4f}")

    hard_idx = [i for i, p in enumerate(pairs) if p.get("kind") == "hard"]
    hard_p95 = float(np.percentile(sims[hard_idx], 95)) if hard_idx else 0.0
    return {
        "hard_p95": hard_p95,
        "genuine_scores": genuine_scores,
        "genuine_min": min(genuine_scores),
    }


def main():
    r9 = evaluate_model("Experiment 9 (production, APPROVED-BACKUP)", MODEL_9)
    r10 = evaluate_model("Experiment 10 (backtranslation-augmented)", MODEL_10)

    print("\n===== SUGGESTED SUSPECTED-TIER THRESHOLD =====")
    for name, r in (("exp9", r9), ("exp10", r10)):
        margin_floor = r["hard_p95"]
        genuine_floor = r["genuine_min"]
        print(f"{name}: hard-negative p95={margin_floor:.4f}, weakest genuine paraphrase={genuine_floor:.4f}, "
              f"safe suspected-threshold candidate={(margin_floor + genuine_floor) / 2:.4f}")


if __name__ == "__main__":
    main()
