import os
import json
import random

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import torch
from transformers import MarianMTModel, MarianTokenizer
from sentence_transformers import SentenceTransformer

MODELS_ROOT = r"c:\Users\hp\Desktop\aspuinsight\aspu-insight\ai_service\ml_models"
AR_EN_DIR = os.path.join(MODELS_ROOT, "opus-mt-ar-en")
EN_AR_DIR = os.path.join(MODELS_ROOT, "opus-mt-en-ar")
EXP_ROOT = os.path.join(MODELS_ROOT, "experiments")
MODEL_9 = os.path.join(EXP_ROOT, "exp9-balanced-domain-APPROVED-BACKUP")
MODEL_10 = os.path.join(EXP_ROOT, "exp10-backtranslation-augmented")
DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"

CONFIRMED_THRESHOLD = 0.75
SUSPECTED_THRESHOLD = 0.25
N_SAMPLES = 40
SEED = 777


def double_back_translate(texts, ar_en_tok, ar_en_model, en_ar_tok, en_ar_model):
    results = []
    for text in texts:
        current = text
        for _ in range(2):
            en_inputs = ar_en_tok([current], return_tensors="pt", padding=True, truncation=True)
            en_out = ar_en_model.generate(**en_inputs, max_length=256)
            en_text = ar_en_tok.decode(en_out[0], skip_special_tokens=True)
            ar_inputs = en_ar_tok([en_text], return_tensors="pt", padding=True, truncation=True)
            ar_out = en_ar_model.generate(**ar_inputs, max_length=256)
            current = en_ar_tok.decode(ar_out[0], skip_special_tokens=True).strip()
        results.append(current)
    return results


def main():
    torch.set_num_threads(os.cpu_count() or 4)
    print("Loading translation models for adversarial (double back-translation) obfuscation...")
    ar_en_tok = MarianTokenizer.from_pretrained(AR_EN_DIR)
    ar_en_model = MarianMTModel.from_pretrained(AR_EN_DIR)
    en_ar_tok = MarianTokenizer.from_pretrained(EN_AR_DIR)
    en_ar_model = MarianMTModel.from_pretrained(EN_AR_DIR)

    with open(os.path.join(DATA_DIR, "balanced_eval_pairs.json"), encoding="utf-8") as f:
        eval_pairs = json.load(f)

    positives = [p for p in eval_pairs if p["label"] == 1]
    rng = random.Random(SEED)
    sample = rng.sample(positives, min(N_SAMPLES, len(positives)))
    print(f"Sampled {len(sample)} REAL known-plagiarism pairs from the held-out eval set")

    print("Applying a SECOND round of back-translation obfuscation to the 'b' side "
          "(simulating a student deliberately laundering already-plagiarized text through a translation tool)...")
    obfuscated_b = double_back_translate([p["b"] for p in sample], ar_en_tok, ar_en_model, en_ar_tok, en_ar_model)

    for name, model_path in (("Experiment 9 (production)", MODEL_9), ("Experiment 10", MODEL_10)):
        print(f"\n===== {name} =====")
        model = SentenceTransformer(model_path)

        vec_a = model.encode([p["a"] for p in sample], show_progress_bar=False)
        vec_b_orig = model.encode([p["b"] for p in sample], show_progress_bar=False)
        vec_b_obf = model.encode(obfuscated_b, show_progress_bar=False)

        sims_orig = np.sum(vec_a * vec_b_orig, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b_orig, axis=1))
        sims_obf = np.sum(vec_a * vec_b_obf, axis=1) / (np.linalg.norm(vec_a, axis=1) * np.linalg.norm(vec_b_obf, axis=1))

        confirmed_before = int((sims_orig >= CONFIRMED_THRESHOLD).sum())
        confirmed_after = int((sims_obf >= CONFIRMED_THRESHOLD).sum())
        suspected_after = int(((sims_obf >= SUSPECTED_THRESHOLD) & (sims_obf < CONFIRMED_THRESHOLD)).sum())
        fully_evaded = int((sims_obf < SUSPECTED_THRESHOLD).sum())

        print(f"  mean similarity BEFORE obfuscation: {sims_orig.mean():.4f} (confirmed: {confirmed_before}/{len(sample)})")
        print(f"  mean similarity AFTER obfuscation:  {sims_obf.mean():.4f} (confirmed: {confirmed_after}/{len(sample)}, "
              f"suspected: {suspected_after}/{len(sample)}, FULLY EVADED both tiers: {fully_evaded}/{len(sample)})")
        print(f"  mean score drop from obfuscation: {(sims_orig.mean() - sims_obf.mean()):.4f}")


if __name__ == "__main__":
    main()
