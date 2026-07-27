import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from sentence_transformers import SentenceTransformer, util

BASE_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "ml_models", "paraphrase-multilingual-MiniLM-L12-v2-base"
)
FINETUNED_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "ml_models", "plagiarism-embedder-finetuned"
)

ORIGINAL = "يعتبر التعلم العميق أحد أهم فروع الذكاء الاصطناعي التي أحدثت تطوراً كبيراً في معالجة اللغة الطبيعية."
PARAPHRASED = "يُعد التعلم العميق واحداً من أبرز مجالات الذكاء الاصطناعي التي أسهمت في تقدم ملحوظ بمعالجة اللغات الطبيعية."
UNRELATED = "ترتفع أسعار النفط عالمياً بسبب التوترات الجيوسياسية في منطقة الشرق الأوسط."


def show(model, name):
    e_orig, e_para, e_unrel = model.encode([ORIGINAL, PARAPHRASED, UNRELATED])
    sim_paraphrase = util.cos_sim(e_orig, e_para).item()
    sim_unrelated = util.cos_sim(e_orig, e_unrel).item()
    print(f"\n=== {name} ===")
    print(f"تشابه (نص أصلي × نص مُعاد صياغته)   : {sim_paraphrase:.4f}")
    print(f"تشابه (نص أصلي × نص غير مرتبط)      : {sim_unrelated:.4f}")
    print(f"الفارق (الفجوة الفاصلة)              : {sim_paraphrase - sim_unrelated:.4f}")
    return sim_paraphrase, sim_unrelated


def main():
    print("النص الأصلي     :", ORIGINAL)
    print("النص المُعاد صياغته:", PARAPHRASED)
    print("نص غير مرتبط     :", UNRELATED)

    base_model = SentenceTransformer(BASE_MODEL_PATH)
    base_p, base_u = show(base_model, "قبل الضبط الدقيق (النموذج الأساس)")

    if os.path.exists(FINETUNED_MODEL_PATH):
        ft_model = SentenceTransformer(FINETUNED_MODEL_PATH)
        ft_p, ft_u = show(ft_model, "بعد الضبط الدقيق (النموذج المُدرَّب)")

        print("\n=== الخلاصة ===")
        print(f"تحسّن تشابه إعادة الصياغة : {ft_p - base_p:+.4f}")
        print(f"تغيّر تشابه النص غير المرتبط: {ft_u - base_u:+.4f}")
        print(f"اتساع الفجوة الفاصلة      : {(ft_p - ft_u) - (base_p - base_u):+.4f}")
    else:
        print("\nالنموذج المُدرَّب غير موجود بعد في:", FINETUNED_MODEL_PATH)
        print("شغّل train_plagiarism_embedder.py أولاً حتى الاكتمال.")


if __name__ == "__main__":
    main()
