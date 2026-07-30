import os
import glob
import json
import random

DATA_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data"
ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"
MIN_LEN, MAX_LEN = 60, 220


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
            if len(text) >= 3000:
                docs.append(text)
        by_cat[cat] = docs
    return by_cat


def random_snippet(text, rng, min_len=MIN_LEN, max_len=MAX_LEN):
    length = rng.randint(min_len, max_len)
    if len(text) <= length:
        return text
    start = rng.randint(0, len(text) - length - 1)
    return text[start:start + length].strip()


def build_new_negatives(by_cat, n, seed):
    rng = random.Random(seed)
    categories = list(by_cat.keys())
    negatives = []
    attempts = 0
    while len(negatives) < n and attempts < n * 20:
        attempts += 1
        cat_a, cat_b = rng.sample(categories, 2) if rng.random() < 0.5 else (rng.choice(categories),) * 2
        docs_a, docs_b = by_cat[cat_a], by_cat[cat_b]
        if len(docs_a) < 1 or len(docs_b) < 1:
            continue
        doc_a = rng.choice(docs_a)
        doc_b = rng.choice(docs_b)
        if doc_a is doc_b:
            continue
        snip_a, snip_b = random_snippet(doc_a, rng), random_snippet(doc_b, rng)
        if len(snip_a) > 30 and len(snip_b) > 30:
            negatives.append({"a": snip_a, "b": snip_b, "label": 0, "category": f"{cat_a}/{cat_b}", "kind": "backtranslation-balance"})
    return negatives


def main():
    with open(os.path.join(DATA_DIR, "backtranslation_pairs.json"), encoding="utf-8") as f:
        bt_pairs = json.load(f)
    print(f"Loaded {len(bt_pairs)} clean back-translation paraphrase pairs")

    with open(os.path.join(DATA_DIR, "balanced_train_pairs.json"), encoding="utf-8") as f:
        existing_train = json.load(f)
    print(f"Existing training set: {len(existing_train)} pairs "
          f"({sum(1 for p in existing_train if p['label']==1)} pos / {sum(1 for p in existing_train if p['label']==0)} neg)")

    by_cat = load_arpd_by_category()
    new_negatives = build_new_negatives(by_cat, n=len(bt_pairs), seed=555)
    print(f"Generated {len(new_negatives)} new matching negatives to keep exact balance")

    new_positives = [{"a": p["a"], "b": p["b"], "label": 1, "obfuscation": "backtranslation"} for p in bt_pairs]

    extended = existing_train + new_positives + new_negatives
    pos = sum(1 for p in extended if p["label"] == 1)
    neg = sum(1 for p in extended if p["label"] == 0)
    print(f"Extended training set: {len(extended)} pairs ({pos} pos / {neg} neg)")
    assert pos == neg, f"BALANCE BROKEN: {pos} != {neg}"

    out_path = os.path.join(DATA_DIR, "balanced_train_pairs_v2_backtranslation.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(extended, f, ensure_ascii=False, indent=1)
    print("Saved", out_path)


if __name__ == "__main__":
    main()
