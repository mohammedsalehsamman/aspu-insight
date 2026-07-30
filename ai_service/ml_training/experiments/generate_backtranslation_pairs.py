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
OUT_PATH = r"C:\Users\hp\Desktop\plagiarism-training-data\backtranslation_pairs.json"

N_SENTENCES = 150  # kept modest on purpose - a supplement, not a replacement, of the existing data
MIN_LEN = 60
MAX_LEN = 220


def load_candidate_sentences(n, seed=7):
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
                if MIN_LEN <= len(part) <= MAX_LEN and "\x00" not in part:
                    sentences.append(part + ".")
    rng.shuffle(sentences)
    return sentences[:n]


def main():
    torch.set_num_threads(os.cpu_count() or 4)

    print("Loading translation models...")
    ar_en_tok = MarianTokenizer.from_pretrained(AR_EN_DIR)
    ar_en_model = MarianMTModel.from_pretrained(AR_EN_DIR)
    en_ar_tok = MarianTokenizer.from_pretrained(EN_AR_DIR)
    en_ar_model = MarianMTModel.from_pretrained(EN_AR_DIR)

    sentences = load_candidate_sentences(N_SENTENCES)
    print(f"Selected {len(sentences)} real ARPD sentences for back-translation")

    pairs = []
    for i, sent in enumerate(sentences):
        try:
            en_inputs = ar_en_tok([sent], return_tensors="pt", padding=True, truncation=True)
            en_out = ar_en_model.generate(**en_inputs, max_length=256)
            en_text = ar_en_tok.decode(en_out[0], skip_special_tokens=True)

            ar_inputs = en_ar_tok([en_text], return_tensors="pt", padding=True, truncation=True)
            ar_out = en_ar_model.generate(**ar_inputs, max_length=256)
            back_ar_text = en_ar_tok.decode(ar_out[0], skip_special_tokens=True)

            if back_ar_text.strip() and back_ar_text.strip() != sent.strip():
                pairs.append({"a": sent, "b": back_ar_text.strip(), "label": 1, "source": "backtranslation"})
        except Exception as e:
            print(f"  skip sentence {i}: {e}")

        if (i + 1) % 20 == 0:
            print(f"  processed {i + 1}/{len(sentences)}, generated {len(pairs)} pairs so far")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=1)
    print(f"Saved {len(pairs)} back-translation paraphrase pairs to {OUT_PATH}")


if __name__ == "__main__":
    main()
