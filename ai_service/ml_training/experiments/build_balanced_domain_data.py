import os
import glob
import json
import random

ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"
OUT_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"

MIN_LEN = 180
MAX_LEN = 2000
MIN_DOC_LEN = 3000  # skip empty/corrupt/too-short ARPD files


def load_arpd_by_category():
    by_cat = {}
    for cat in sorted(os.listdir(ARPD_ROOT)):
        cat_path = os.path.join(ARPD_ROOT, cat)
        if not os.path.isdir(cat_path):
            continue
        docs = []
        for fp in glob.glob(os.path.join(cat_path, "*.txt")):
            with open(fp, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if len(text) >= MIN_DOC_LEN:
                docs.append(text)
        by_cat[cat] = docs
    return by_cat


def random_snippet(text, rng):
    length = rng.randint(MIN_LEN, MAX_LEN)
    if len(text) <= length:
        return text
    start = rng.randint(0, len(text) - length - 1)
    return text[start:start + length].strip()


def build_negatives(by_cat, n_hard, n_easy, seed):
    rng = random.Random(seed)
    categories = list(by_cat.keys())
    negatives = []

    # Hard negatives: two different documents, SAME specialization
    attempts = 0
    while len([p for p in negatives if p["kind"] == "hard"]) < n_hard and attempts < n_hard * 20:
        attempts += 1
        cat = rng.choice(categories)
        docs = by_cat[cat]
        if len(docs) < 2:
            continue
        doc_a, doc_b = rng.sample(docs, 2)
        snip_a, snip_b = random_snippet(doc_a, rng), random_snippet(doc_b, rng)
        if len(snip_a) > 50 and len(snip_b) > 50:
            negatives.append({"a": snip_a, "b": snip_b, "label": 0, "kind": "hard", "category": cat})

    # Easy negatives: two different documents, DIFFERENT specializations
    attempts = 0
    while len([p for p in negatives if p["kind"] == "easy"]) < n_easy and attempts < n_easy * 20:
        attempts += 1
        cat_a, cat_b = rng.sample(categories, 2)
        if not by_cat[cat_a] or not by_cat[cat_b]:
            continue
        doc_a = rng.choice(by_cat[cat_a])
        doc_b = rng.choice(by_cat[cat_b])
        snip_a, snip_b = random_snippet(doc_a, rng), random_snippet(doc_b, rng)
        if len(snip_a) > 50 and len(snip_b) > 50:
            negatives.append({"a": snip_a, "b": snip_b, "label": 0, "kind": "easy", "category": f"{cat_a}/{cat_b}"})

    return negatives


def main():
    by_cat = load_arpd_by_category()
    for cat, docs in by_cat.items():
        print(f"{cat}: {len(docs)} usable documents (after empty/short filtering)")

    # Split ARPD documents 80/20 per category to keep train/eval negatives from disjoint documents
    rng = random.Random(123)
    train_cat, eval_cat = {}, {}
    for cat, docs in by_cat.items():
        shuffled = docs[:]
        rng.shuffle(shuffled)
        cut = int(len(shuffled) * 0.8)
        train_cat[cat] = shuffled[:cut]
        eval_cat[cat] = shuffled[cut:]

    # Load existing real positive pairs
    with open(os.path.join(OUT_DIR, "domain_train_pairs.json"), encoding="utf-8") as f:
        train_positives = json.load(f)
    with open(os.path.join(OUT_DIR, "domain_eval_pairs_heldout.json"), encoding="utf-8") as f:
        eval_pairs_old = json.load(f)
    eval_positives = [p for p in eval_pairs_old if p["label"] == 1]

    # Oversample the rare "manual paraphrasing" category (real examples repeated, not synthetic)
    paraphrase_pairs = [p for p in train_positives if p.get("obfuscation") == "manual paraphrasing"]
    oversampled = train_positives + paraphrase_pairs * 6
    print(f"Training positives: {len(train_positives)} original + {len(paraphrase_pairs)*6} oversampled "
          f"(manual paraphrasing x6) = {len(oversampled)} total")

    train_hard = len(oversampled) // 2
    train_negatives = build_negatives(train_cat, n_hard=train_hard, n_easy=len(oversampled) - train_hard, seed=42)
    eval_hard = len(eval_positives) // 2
    eval_negatives = build_negatives(eval_cat, n_hard=eval_hard, n_easy=len(eval_positives) - eval_hard, seed=99)

    train_pairs = [{"a": p["a"], "b": p["b"], "label": 1, "obfuscation": p.get("obfuscation", "")} for p in oversampled] + \
                  [{"a": p["a"], "b": p["b"], "label": 0, "kind": p["kind"], "category": p["category"]} for p in train_negatives]
    eval_pairs = [{"a": p["a"], "b": p["b"], "label": 1, "obfuscation": p.get("obfuscation", "")} for p in eval_positives] + \
                 [{"a": p["a"], "b": p["b"], "label": 0, "kind": p["kind"], "category": p["category"]} for p in eval_negatives]

    with open(os.path.join(OUT_DIR, "balanced_train_pairs.json"), "w", encoding="utf-8") as f:
        json.dump(train_pairs, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT_DIR, "balanced_eval_pairs.json"), "w", encoding="utf-8") as f:
        json.dump(eval_pairs, f, ensure_ascii=False, indent=1)

    print(f"\nTRAIN: {len(oversampled)} positives + {len(train_negatives)} negatives "
          f"({sum(1 for n in train_negatives if n['kind']=='hard')} hard, "
          f"{sum(1 for n in train_negatives if n['kind']=='easy')} easy) = {len(train_pairs)} total")
    print(f"EVAL:  {len(eval_positives)} positives + {len(eval_negatives)} negatives "
          f"({sum(1 for n in eval_negatives if n['kind']=='hard')} hard, "
          f"{sum(1 for n in eval_negatives if n['kind']=='easy')} easy) = {len(eval_pairs)} total")

    import numpy as np
    pos_lens = [len(p["a"]) for p in train_pairs if p["label"] == 1]
    neg_lens = [len(p["a"]) for p in train_pairs if p["label"] == 0]
    print(f"\nLength check — positives avg: {np.mean(pos_lens):.0f}, negatives avg: {np.mean(neg_lens):.0f} "
          f"(should now be close, unlike the old 1035 vs 173 imbalance)")


if __name__ == "__main__":
    main()
