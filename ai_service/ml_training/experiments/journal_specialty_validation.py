import os
import sys
import io
import glob

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"c:\Users\hp\Desktop\aspuinsight\aspu-insight")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aspu_insight.settings")
import django
django.setup()

import numpy as np
from django.conf import settings
from pypdf import PdfReader
from sklearn.metrics.pairwise import cosine_similarity

from ai_service.utils.embeddings import get_embedding_model
from ai_service.ieee_checker.services.citation_extractor import detect_language
from ai_service.plagiarism.services.chunking import chunk_text, is_citation_chunk
from ai_service.plagiarism.services.section_extractor import extract_core_sections
from ai_service.plagiarism.services.internal_similarity import _bootstrap_commonness_reference, _commonness_count

TESTING_DIR = r"C:\Users\hp\Desktop\plagiarism-training-data\testing"
NEW_DIR = os.path.join(TESTING_DIR, "new_papers")
SPEC_DIR = os.path.join(TESTING_DIR, "journal_specialties")

THRESHOLD = getattr(settings, 'PLAGIARISM_INTERNAL_SIMILARITY_THRESHOLD', 0.75)
SUSPECTED_THRESHOLD = getattr(settings, 'PLAGIARISM_SUSPECTED_INTERNAL_THRESHOLD', 0.25)
CORROBORATION_THRESHOLD = getattr(settings, 'PLAGIARISM_CORROBORATION_THRESHOLD', 0.50)
MIN_CORROBORATING_CHUNKS = getattr(settings, 'PLAGIARISM_MIN_CORROBORATING_CHUNKS', 2)
MIN_CHUNKS_FOR_CORROBORATION = getattr(settings, 'PLAGIARISM_MIN_CHUNKS_FOR_CORROBORATION', 4)
COMMONNESS_THRESHOLD = getattr(settings, 'PLAGIARISM_COMMONNESS_THRESHOLD', 0.97)
COMMONNESS_MAX_COUNT = getattr(settings, 'PLAGIARISM_COMMONNESS_MAX_COUNT', 5)

PAPERS = [
    ("accounting_biskra", os.path.join(TESTING_DIR, "accounting_biskra.pdf"), "accounting"),
    ("accounting_ouargla", os.path.join(TESTING_DIR, "accounting_ouargla.pdf"), "accounting"),
    ("accounting2_ghardaia", os.path.join(NEW_DIR, "accounting2_ghardaia.pdf"), "accounting"),
    ("acc3_ouargla_audit", os.path.join(SPEC_DIR, "acc3_ouargla_audit.pdf"), "accounting"),
    ("acc5_ouargla_statements", os.path.join(SPEC_DIR, "acc5_ouargla_statements.pdf"), "accounting"),
    ("law_ghardaia", os.path.join(TESTING_DIR, "law_ghardaia.pdf"), "law"),
    ("law2_ouargla", os.path.join(NEW_DIR, "law2_ouargla.pdf"), "law"),
    ("law3_batna", os.path.join(SPEC_DIR, "law3_batna.pdf"), "law"),
    ("law4_ouargla", os.path.join(SPEC_DIR, "law4_ouargla.pdf"), "law"),
    ("law5_ouargla_cybercrime", os.path.join(SPEC_DIR, "law5_ouargla_cybercrime.pdf"), "law"),
    ("medical_ouargla", os.path.join(TESTING_DIR, "medical_ouargla.pdf"), "medical"),
    ("medical2_biskra", os.path.join(NEW_DIR, "medical2_biskra.pdf"), "medical"),
    ("medical4_batna", os.path.join(SPEC_DIR, "medical4_batna.pdf"), "medical"),
    ("it_ouargla", os.path.join(NEW_DIR, "it_ouargla.pdf"), "informatics"),
    ("it3_tissemsilt_sis", os.path.join(SPEC_DIR, "it3_tissemsilt_sis.pdf"), "informatics"),
]


def extract_text_from_pdf(path):
    raw_text = ""
    try:
        reader = PdfReader(path)
        for page in reader.pages:
            try:
                t = page.extract_text()
            except Exception:
                continue
            if t:
                raw_text += t + " "
    except Exception as e:
        print(f"  PDF read error for {path}: {e}")
    return raw_text


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
    print(f"Settings: THRESHOLD={THRESHOLD}, SUSPECTED={SUSPECTED_THRESHOLD}, "
          f"CORROB_THRESH={CORROBORATION_THRESHOLD}, MIN_CORROB={MIN_CORROBORATING_CHUNKS}, "
          f"MIN_CHUNKS_FOR_CORROB={MIN_CHUNKS_FOR_CORROBORATION}, "
          f"COMMONNESS={COMMONNESS_THRESHOLD}/{COMMONNESS_MAX_COUNT}")

    model_ft = get_embedding_model(settings.PLAGIARISM_EMBEDDING_MODEL)
    model_base = get_embedding_model(settings.PLAGIARISM_BASE_EMBEDDING_MODEL)
    bootstrap_pool = _bootstrap_commonness_reference()
    print(f"Bootstrap commonness pool: {len(bootstrap_pool)} vectors")

    prepared = {}
    for key, path, spec in PAPERS:
        text = extract_text_from_pdf(path)
        if len(text.strip()) < 200:
            print(f"{key}: SKIPPED - extraction too short/failed")
            continue
        chunks, vec_ft, vec_base, langs = prepare_doc(model_ft, model_base, text)
        prepared[key] = {"chunks": chunks, "ft": vec_ft, "base": vec_base, "langs": langs, "spec": spec}
        print(f"{key} ({spec}): {len(chunks)} chunks after core-extraction + citation-exclusion")

    print(f"\nLoaded {len(prepared)} real papers spanning the journal's actual specializations "
          f"(accounting, law, medical, informatics)")

    n_scans = 0
    n_confirmed = 0
    n_any_flag = 0
    detail_rows = []

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
            if okey == qkey or len(odata["chunks"]) == 0:
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
            detail_rows.append((qkey, qdata["spec"], okey, odata["spec"], score, level))
            if level == "confirmed":
                any_confirmed = True
        n_scans += 1
        if any_confirmed:
            n_confirmed += 1
        if any_flag:
            n_any_flag += 1

    print(f"\n===== JOURNAL-SPECIALTY VALIDATION ({len(prepared)} real papers: accounting/law/medical/informatics) =====")
    print(f"{n_scans} full-document scans, ALL genuinely independent real theses (no shared authorship)")
    print(f"scans with >=1 'confirmed' false match: {n_confirmed}/{n_scans} = {100*n_confirmed/n_scans:.1f}%")
    print(f"scans with >=1 flag at all (confirmed or suspected): {n_any_flag}/{n_scans} = {100*n_any_flag/n_scans:.1f}%")

    print(f"\n--- all flagged pairs (for manual inspection) ---")
    for qkey, qspec, okey, ospec, score, level in sorted(detail_rows, key=lambda r: -r[4]):
        same = "SAME-SPEC" if qspec == ospec else "cross-spec"
        print(f"  {level:>9} | {score:.4f} | {qkey} ({qspec}) <-> {okey} ({ospec})  [{same}]")


if __name__ == "__main__":
    main()
