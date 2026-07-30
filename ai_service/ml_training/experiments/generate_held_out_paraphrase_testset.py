import os
import glob
import json
import random

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
from transformers import MarianMTModel, MarianTokenizer

MODELS_ROOT = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models"
AR_EN_DIR = os.path.join(MODELS_ROOT, "opus-mt-ar-en")
EN_AR_DIR = os.path.join(MODELS_ROOT, "opus-mt-en-ar")

ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
OUT_PATH = os.path.join(DATA_DIR, "held_out_paraphrase_testset.json")

N_SENTENCES = 130
MIN_LEN = 60
MAX_LEN = 220
SEED = 4242


def is_mostly_arabic(text, ratio=0.7):
    if not text:
        return False
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    return arabic_chars / max(len(text), 1) >= ratio


def load_candidate_sentences(n, seed, exclude):
    rng = random.Random(seed)
    sentences = []
    for cat in sorted(os.listdir(ARPD_ROOT)):
        cat_path = os.path.join(ARPD_ROOT, cat)
        if not os.path.isdir(cat_path):
            continue
        files = glob.glob(os.path.join(cat_path, "*.txt"))
        if not files:
            continue
        for fp in rng.sample(files, min(30, len(files))):
            with open(fp, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for part in text.split("."):
                part = part.strip()
                if MIN_LEN <= len(part) <= MAX_LEN and "\x00" not in part and (part + ".") not in exclude:
                    sentences.append(part + ".")
    rng.shuffle(sentences)
    return sentences[:n]


def main():
    with open(os.path.join(DATA_DIR, "backtranslation_pairs.json"), encoding="utf-8") as f:
        already_used = json.load(f)
    exclude = {p["a"] for p in already_used}
    print(f"Excluding {len(exclude)} sentences already used in Experiment 10's training augmentation")

    print("Loading translation models...")
    ar_en_tok = MarianTokenizer.from_pretrained(AR_EN_DIR)
    ar_en_model = MarianMTModel.from_pretrained(AR_EN_DIR)
    en_ar_tok = MarianTokenizer.from_pretrained(EN_AR_DIR)
    en_ar_model = MarianMTModel.from_pretrained(EN_AR_DIR)
    torch.set_num_threads(os.cpu_count() or 4)

    sentences = load_candidate_sentences(N_SENTENCES, SEED, exclude)
    print(f"Selected {len(sentences)} NEW held-out ARPD sentences (disjoint from training augmentation)")

    pairs = []
    for i, sent in enumerate(sentences):
        try:
            en_inputs = ar_en_tok([sent], return_tensors="pt", padding=True, truncation=True)
            en_out = ar_en_model.generate(**en_inputs, max_length=256)
            en_text = ar_en_tok.decode(en_out[0], skip_special_tokens=True)

            ar_inputs = en_ar_tok([en_text], return_tensors="pt", padding=True, truncation=True)
            ar_out = en_ar_model.generate(**ar_inputs, max_length=256)
            back_ar_text = en_ar_tok.decode(ar_out[0], skip_special_tokens=True)

            if (back_ar_text.strip() and back_ar_text.strip() != sent.strip()
                    and is_mostly_arabic(sent) and is_mostly_arabic(back_ar_text)):
                pairs.append({"a": sent, "b": back_ar_text.strip(), "label": 1, "source": "held_out_backtranslation"})
        except Exception as e:
            print(f"  skip sentence {i}: {e}")

        if (i + 1) % 20 == 0:
            print(f"  processed {i + 1}/{len(sentences)}, generated {len(pairs)} clean pairs so far")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=1)
    print(f"Saved {len(pairs)} held-out genuine-paraphrase test pairs to {OUT_PATH}")
    print("NOTE: none of these pairs were used in exp9 or exp10 training - this is an independent test set.")


if __name__ == "__main__":
    main()
