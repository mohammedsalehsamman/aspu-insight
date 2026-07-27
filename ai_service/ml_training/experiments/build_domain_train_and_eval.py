import os
import glob
import random
import xml.etree.ElementTree as ET
import json

ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ExAraCorpusPAN2015-extracted\ExAraCorpusPAN2015"
TRAIN_CORPUS = os.path.join(ROOT, "ExAraPlagDet-10-08-2015-Training")
TEST_CORPUS = os.path.join(ROOT, "ExAraPlagDet-21-09-2015-Test")

_file_cache = {}


def read_file(path):
    if path not in _file_cache:
        with open(path, encoding="utf-8", errors="ignore") as f:
            _file_cache[path] = f.read()
    return _file_cache[path]


def extract_pairs_from_folder(annot_dir, suspicious_dir, source_dir, min_len=20):
    pairs = []
    for xml_path in glob.glob(os.path.join(annot_dir, "*.xml")):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        susp_path = os.path.join(suspicious_dir, root.attrib["reference"])
        if not os.path.exists(susp_path):
            continue
        susp_text = read_file(susp_path)
        for feat in root.findall("feature"):
            source_path = os.path.join(source_dir, feat.attrib["source_reference"])
            if not os.path.exists(source_path):
                continue
            source_text = read_file(source_path)
            this_offset, this_length = int(feat.attrib["this_offset"]), int(feat.attrib["this_length"])
            source_offset, source_length = int(feat.attrib["source_offset"]), int(feat.attrib["source_length"])
            a = susp_text[this_offset:this_offset + this_length].strip()
            b = source_text[source_offset:source_offset + source_length].strip()
            if len(a) > min_len and len(b) > min_len:
                pairs.append({"a": a, "b": b, "obfuscation": feat.attrib.get("obfuscation", "")})
    return pairs


def build_training_data():
    annot = os.path.join(TRAIN_CORPUS, "plagiarism-annotation")
    susp_dir = os.path.join(TRAIN_CORPUS, "suspicious-documents")
    src_dir = os.path.join(TRAIN_CORPUS, "source-documents")

    all_pairs = []
    for folder in ("02-no-obfuscation", "03-artificial-obfuscation", "04-simulated-obfuscation"):
        pairs = extract_pairs_from_folder(os.path.join(annot, folder), susp_dir, src_dir)
        print(f"  {folder}: {len(pairs)} pairs")
        all_pairs.extend(pairs)

    out_path = r"C:\Users\hp\Desktop\plagiarism-training-data\domain_train_pairs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_pairs, f, ensure_ascii=False, indent=1)
    print(f"TOTAL training pairs: {len(all_pairs)} -> saved to {out_path}")


def build_eval_data():
    """Held-out eval set built from the TEST split only (no overlap with training documents)."""
    annot = os.path.join(TEST_CORPUS, "plagiarism-annotation")
    susp_dir = os.path.join(TEST_CORPUS, "suspicious-documents")
    src_dir = os.path.join(TEST_CORPUS, "source-documents")

    positives = []
    no_plag_docs = []
    for xml_path in glob.glob(os.path.join(annot, "*.xml")):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        features = root.findall("feature")
        susp_path = os.path.join(susp_dir, root.attrib["reference"])
        if not os.path.exists(susp_path):
            continue
        if not features:
            text = read_file(susp_path)
            if len(text) > 400:
                no_plag_docs.append(text)
            continue
        susp_text = read_file(susp_path)
        for feat in features:
            obf = feat.attrib.get("obfuscation", "")
            if "synonym" not in obf and "simulated" not in obf and obf != "none":
                continue
            source_path = os.path.join(src_dir, feat.attrib["source_reference"])
            if not os.path.exists(source_path):
                continue
            source_text = read_file(source_path)
            this_offset, this_length = int(feat.attrib["this_offset"]), int(feat.attrib["this_length"])
            source_offset, source_length = int(feat.attrib["source_offset"]), int(feat.attrib["source_length"])
            a = susp_text[this_offset:this_offset + this_length].strip()
            b = source_text[source_offset:source_offset + source_length].strip()
            if len(a) > 20 and len(b) > 20:
                positives.append({"a": a, "b": b, "label": 1})

    random.seed(7)
    negatives = []
    attempts = 0
    while len(negatives) < len(positives) and attempts < len(positives) * 20 and len(no_plag_docs) >= 2:
        attempts += 1
        doc_a, doc_b = random.sample(no_plag_docs, 2)
        length = random.randint(100, 250)
        start_a = random.randint(0, len(doc_a) - length - 1)
        start_b = random.randint(0, len(doc_b) - length - 1)
        snip_a = doc_a[start_a:start_a + length].strip()
        snip_b = doc_b[start_b:start_b + length].strip()
        if len(snip_a) > 20 and len(snip_b) > 20:
            negatives.append({"a": snip_a, "b": snip_b, "label": 0})

    print(f"  TEST split (held-out): {len(positives)} positive, {len(negatives)} negative pairs")
    all_pairs = positives + negatives
    out_path = r"C:\Users\hp\Desktop\plagiarism-training-data\domain_eval_pairs_heldout.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_pairs, f, ensure_ascii=False, indent=1)
    print("Saved held-out eval set to", out_path)


if __name__ == "__main__":
    print("=== Building TRAINING pairs (from Training split only) ===")
    build_training_data()
    print("\n=== Building held-out EVAL pairs (from Test split only, no leakage) ===")
    build_eval_data()
