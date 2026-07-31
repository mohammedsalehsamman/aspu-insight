import os
import sys
import io
import glob
import random

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"c:\Users\hp\Desktop\aspuinsight\aspu-insight")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aspu_insight.settings")
import django
django.setup()

import numpy as np
from django.conf import settings
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.utils.embeddings import get_embedding_model
from ai_service.ieee_checker.services.citation_extractor import detect_language
from ai_service.plagiarism.services.chunking import chunk_text, is_citation_chunk
from ai_service.plagiarism.services.section_extractor import extract_core_sections
from ai_service.plagiarism.services.internal_similarity import _bootstrap_commonness_reference, _commonness_count

ARPD_ROOT = r"C:\Users\hp\Desktop\plagiarism-training-data\ARPD\extracted\TXT"
N_DOCS_PER_CATEGORY = 15
MIN_CHARS = 3000
SEED = 20260731

THRESHOLD = getattr(settings, 'PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD', 0.75)
SUSPECTED_THRESHOLD = getattr(settings, 'PLAGIARISM_SUSPECTED_INTERNAL_THRESHOLD', 0.25)
CORROBORATION_THRESHOLD = getattr(settings, 'PLAGIARISM_CORROBORATION_THRESHOLD', 0.50)
MIN_CORROBORATING_CHUNKS = getattr(settings, 'PLAGIARISM_MIN_CORROBORATING_CHUNKS', 2)
MIN_CHUNKS_FOR_CORROBORATION = getattr(settings, 'PLAGIARISM_MIN_CHUNKS_FOR_CORROBORATION', 4)
COMMONNESS_THRESHOLD = getattr(settings, 'PLAGIARISM_COMMONNESS_THRESHOLD', 0.97)
COMMONNESS_MAX_COUNT = getattr(settings, 'PLAGIARISM_COMMONNESS_MAX_COUNT', 5)


def load_documents():
    docs = []
    for cat in sorted(os.listdir(ARPD_ROOT)):
        cat_path = os.path.join(ARPD_ROOT, cat)
        if not os.path.isdir(cat_path):
            continue
        files = glob.glob(os.path.join(cat_path, "*.txt"))
        rng = random.Random(hash(cat) % (2**31))
        rng.shuffle(files)
        picked = 0
        for fp in files:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if len(text) >= MIN_CHARS:
                docs.append({"category": cat, "path": fp, "text": text})
                picked += 1
            if picked >= N_DOCS_PER_CATEGORY:
                break
    return docs


def prepare_doc(model_ft, model_base, text):
    core = extract_core_sections(text)
    raw_chunks = chunk_text(core)
    chunks = [c for c in raw_chunks if not is_citation_chunk(c)]
    if not chunks:
        return [], None, None, []
    langs = [detect_language(c) for c in chunks]
    vec_ft = model_ft.encode(chunks, show_progress_bar=False)
    vec_base = model_base.encode(chunks, show_progress_bar=False)
    return chunks, vec_ft, vec_base, langs


def classify_match(own_ft, own_base, own_langs, other_ft, other_base, other_langs,
                    bootstrap_pool, live_ft_pool, live_base_pool):
    own_is_ar = np.array([l == "ar" for l in own_langs])
    other_is_ar = np.array([l == "ar" for l in other_langs])
    scores_ft = cosine_similarity(own_ft, other_ft)
    scores_base = cosine_similarity(own_base, other_base)
    mask = np.outer(own_is_ar, other_is_ar)
    scores = np.where(mask, scores_ft, scores_base)

    best_index = np.unravel_index(np.argmax(scores), scores.shape)
    best_score = float(scores[best_index])
    if best_score < SUSPECTED_THRESHOLD:
        return None

    if len(own_ft) < MIN_CHUNKS_FOR_CORROBORATION:
        is_confirmed = best_score >= THRESHOLD
    else:
        row_best = scores.max(axis=1)
        corroborating = int((row_best >= CORROBORATION_THRESHOLD).sum())
        is_confirmed = best_score >= THRESHOLD and corroborating >= MIN_CORROBORATING_CHUNKS

    if is_confirmed:
        if bool(mask[best_index]):
            pool = (np.concatenate([bootstrap_pool, live_ft_pool])
                    if len(bootstrap_pool) and len(live_ft_pool) else (bootstrap_pool if len(bootstrap_pool) else live_ft_pool))
            best_vector = own_ft[best_index[0]]
        else:
            pool = live_base_pool
            best_vector = own_base[best_index[0]]
        commonness = _commonness_count(best_vector, pool, COMMONNESS_THRESHOLD)
        if commonness > COMMONNESS_MAX_COUNT:
            is_confirmed = False

    return best_score, ("confirmed" if is_confirmed else "suspected")


def main():
    print(f"Settings in effect: THRESHOLD={THRESHOLD}, SUSPECTED={SUSPECTED_THRESHOLD}, "
          f"CORROBORATION_THRESHOLD={CORROBORATION_THRESHOLD}, MIN_CORROBORATING_CHUNKS={MIN_CORROBORATING_CHUNKS}, "
          f"MIN_CHUNKS_FOR_CORROBORATION={MIN_CHUNKS_FOR_CORROBORATION}, "
          f"COMMONNESS_THRESHOLD={COMMONNESS_THRESHOLD}, COMMONNESS_MAX_COUNT={COMMONNESS_MAX_COUNT}")

    model_ft = get_embedding_model(settings.PLAGIARISM_EMBEDDING_MODEL)
    model_base = get_embedding_model(settings.PLAGIARISM_BASE_EMBEDDING_MODEL)
    bootstrap_pool = _bootstrap_commonness_reference()
    print(f"Bootstrap commonness pool: {len(bootstrap_pool)} vectors")

    docs = load_documents()
    print(f"Loaded {len(docs)} real ARPD documents across categories: {sorted(set(d['category'] for d in docs))}")

    prepared = {}
    for d in docs:
        chunks, vec_ft, vec_base, langs = prepare_doc(model_ft, model_base, d["text"])
        prepared[d["path"]] = {"chunks": chunks, "ft": vec_ft, "base": vec_base, "langs": langs, "category": d["category"]}
    total_chunks = sum(len(v["chunks"]) for v in prepared.values())
    print(f"Total chunks after core-section-extraction + citation-exclusion: {total_chunks} (avg {total_chunks/len(prepared):.1f}/doc)")

    live_ft_pool_all = np.concatenate([v["ft"] for v in prepared.values() if len(v["chunks"])])
    live_base_pool_all = np.concatenate([v["base"] for v in prepared.values() if len(v["chunks"])])

    n_scans = 0
    n_flagged_confirmed = 0
    n_flagged_any = 0
    confirmed_scores = []

    for qkey, qdata in prepared.items():
        if len(qdata["chunks"]) == 0:
            continue
        other_ft_list = [v["ft"] for k, v in prepared.items() if k != qkey and len(v["chunks"])]
        other_base_list = [v["base"] for k, v in prepared.items() if k != qkey and len(v["chunks"])]
        live_ft_excl_self = np.concatenate(other_ft_list) if other_ft_list else np.zeros((0, qdata["ft"].shape[1]))
        live_base_excl_self = np.concatenate(other_base_list) if other_base_list else np.zeros((0, qdata["base"].shape[1]))

        any_confirmed = False
        any_flag = False
        for okey, odata in prepared.items():
            if okey == qkey or qdata["category"] == odata["category"] or len(odata["chunks"]) == 0:
                continue
            result = classify_match(
                qdata["ft"], qdata["base"], qdata["langs"],
                odata["ft"], odata["base"], odata["langs"],
                bootstrap_pool, live_ft_excl_self, live_base_excl_self,
            )
            if result is None:
                continue
            score, level = result
            any_flag = True
            if level == "confirmed":
                any_confirmed = True
                confirmed_scores.append(score)
        n_scans += 1
        if any_confirmed:
            n_flagged_confirmed += 1
        if any_flag:
            n_flagged_any += 1

    print(f"\n===== FINAL FULL-PIPELINE DOCUMENT-LEVEL VALIDATION =====")
    print(f"{n_scans} full-document scans against genuinely unrelated cross-category real documents")
    print(f"scans with >=1 'confirmed' false match: {n_flagged_confirmed}/{n_scans} = {100*n_flagged_confirmed/n_scans:.1f}%")
    print(f"scans with >=1 'suspected' or 'confirmed' flag at all: {n_flagged_any}/{n_scans} = {100*n_flagged_any/n_scans:.1f}%")
    if confirmed_scores:
        print(f"confirmed-match score distribution: mean={np.mean(confirmed_scores):.4f} "
              f"min={np.min(confirmed_scores):.4f} max={np.max(confirmed_scores):.4f}")


if __name__ == "__main__":
    main()

