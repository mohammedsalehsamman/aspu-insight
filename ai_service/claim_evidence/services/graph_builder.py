"""
Core service for the Claim-to-Evidence Graph feature.

`extract_graph(text, threshold)` is the main entrypoint:
    1. Segments `text` into sentences (NLTK punkt).
    2. Classifies each sentence as claim/evidence/neutral via the hybrid
       heuristic + zero-shot classifier.
    3. Computes sentence embeddings (multilingual) for claim and
       evidence sentences.
    4. Computes a cosine-similarity matrix between claims and evidence.
    5. Builds a `networkx.DiGraph`: nodes for every claim/evidence/neutral
       sentence, directed edges evidence -> claim ("supports") where
       similarity exceeds `threshold`.
    6. Ranks claims by their number of supporting evidence edges (in-degree,
       tie-broken by classification score) and builds a smaller "focus
       graph" containing only the top claims and the evidence that supports
       them - intended for visualization.
    7. Serializes everything to
       `{"nodes": [...], "edges": [...], "stats": {...}, "focus_graph": {...}, "top_claims": [...]}`.

Bilingual (Arabic/English) support: sentence segmentation (`_segment_sentences`)
and the embedding model handle Arabic input directly; sentence
classification for Arabic relies on the cue-phrase heuristics only (see
`classifier.py`'s module docstring for why the zero-shot model is skipped
for Arabic). `extract_graph`'s `language` parameter (typically the output
of `ai_service.ieee_checker.services.citation_extractor.detect_language`)
is threaded down into sentence classification.
"""
from __future__ import annotations

import logging
import re

import networkx as nx
import torch

from ..infrastructure.nlp_models import ensure_nltk_punkt, get_embedding_model
from .classifier import classify_sentences

logger = logging.getLogger(__name__)

# The multilingual embedding model (see CLAIM_EVIDENCE_EMBEDDING_MODEL) produces
# a more compressed cosine-similarity range than the English-only model it
# replaced - empirically, unrelated sentence pairs score ~0.0-0.08 and genuinely
# related claim/evidence pairs score ~0.2-0.4, so 0.5 (tuned for the old model)
# would reject almost every real match.
DEFAULT_SIMILARITY_THRESHOLD = 0.2
DEFAULT_TOP_CLAIMS_COUNT = 10
MIN_SENTENCE_CHARS = 10
EMBEDDING_BATCH_SIZE = 32

# Safety cap on the number of sentences processed per document, to bound
# worst-case CPU time for the zero-shot classifier when running
# synchronously in eager mode.
MAX_SENTENCES = 500

# Extra sentence-boundary split applied after NLTK punkt, to catch the
# Arabic question mark ("؟") which punkt's English model doesn't
# recognize. Deliberately excludes Arabic comma ("،") and semicolon ("؛"),
# which are usually clause separators rather than sentence boundaries.
_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?؟])\s+')


def _segment_sentences(text: str) -> list[str]:
    """Split `text` into sentences using NLTK's punkt tokenizer.

    An extra regex pass catches Arabic sentence-terminal punctuation that
    punkt's English model doesn't recognize (see `_SENTENCE_BOUNDARY_RE`);
    this is a no-op on pure-English text.

    Filters out very short fragments (< MIN_SENTENCE_CHARS) which are
    typically headers, page numbers, or noise from PDF extraction. Caps
    the result at `MAX_SENTENCES`, logging a warning if the document is
    truncated.
    """
    ensure_nltk_punkt()
    from nltk.tokenize import sent_tokenize

    raw_sentences = []
    for chunk in sent_tokenize(text):
        raw_sentences.extend(_SENTENCE_BOUNDARY_RE.split(chunk))

    sentences = [s.strip() for s in raw_sentences if len(s.strip()) >= MIN_SENTENCE_CHARS]

    if len(sentences) > MAX_SENTENCES:
        logger.warning(
            "Document has %d sentences; truncating to MAX_SENTENCES=%d",
            len(sentences), MAX_SENTENCES,
        )
        sentences = sentences[:MAX_SENTENCES]

    return sentences


def _build_focus_graph(graph: nx.DiGraph, top_n: int) -> tuple[dict, list[dict]]:
    """Rank claims by supporting-evidence count and build a focused subgraph.

    Claims are ranked by in-degree (number of "supports" edges from
    evidence nodes), tie-broken by classification `score`. The focus graph
    contains the top `top_n` claims plus every evidence node that supports
    at least one of them, and the edges between them - a much smaller graph
    suitable for direct visualization.

    Args:
        graph: The full claim/evidence/neutral graph built by `extract_graph`.
        top_n: Maximum number of top claims to include.

    Returns:
        A tuple `(focus_graph, top_claims)`:
        - `focus_graph`: `{"nodes": [...], "edges": [...]}` (same shapes as
          the full graph's `nodes`/`edges`).
        - `top_claims`: list of `{"id", "text", "label", "score",
          "supporting_evidence_count"}`, ordered by importance.
    """
    claim_ids = [n for n, data in graph.nodes(data=True) if data["type"] == "claim"]
    ranked = sorted(
        claim_ids,
        key=lambda n: (graph.in_degree(n), graph.nodes[n]["score"]),
        reverse=True,
    )
    top_claim_ids = ranked[:top_n]
    top_claim_id_set = set(top_claim_ids)

    top_claims = [
        {
            "id": node_id,
            "text": graph.nodes[node_id]["text"],
            "label": graph.nodes[node_id]["label"],
            "score": graph.nodes[node_id]["score"],
            "supporting_evidence_count": graph.in_degree(node_id),
        }
        for node_id in top_claim_ids
    ]

    focus_node_ids = set(top_claim_id_set)
    focus_edges = []
    for source, target, data in graph.edges(data=True):
        if target in top_claim_id_set:
            focus_node_ids.add(source)
            focus_edges.append({"source": source, "target": target, "label": data["label"], "weight": data["weight"]})

    focus_nodes = [
        {"id": node_id, "type": data["type"], "label": data["label"], "text": data["text"], "score": data["score"]}
        for node_id, data in graph.nodes(data=True)
        if node_id in focus_node_ids
    ]

    return {"nodes": focus_nodes, "edges": focus_edges}, top_claims


def extract_graph(
    text: str,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    top_claims_count: int = DEFAULT_TOP_CLAIMS_COUNT,
    language: str = "en",
) -> dict:
    """Build a Claim-to-Evidence graph from raw document text.

    Args:
        text: Full extracted document text (e.g. from
            `ai_service.ieee.extract_text_from_file`).
        threshold: Cosine similarity threshold above which an
            evidence -> claim "supports" edge is created. Default 0.5.
        top_claims_count: Number of top-ranked claims (by supporting
            evidence count) to include in `focus_graph`/`top_claims`.
        language: The document's detected language ("ar", "en", "mixed",
            or "unknown" - see
            `ai_service.ieee_checker.services.citation_extractor.detect_language`).
            Only "ar" selects Arabic zero-shot labels/template; all other
            values use the English defaults.

    Returns:
        A dict:
        ```
        {
            "nodes": [{"id": str, "type": "claim"|"evidence"|"neutral", "label": str, "text": str, "score": float}, ...],
            "edges": [{"source": str, "target": str, "label": "supports", "weight": float}, ...],
            "stats": {"claims": int, "evidence": int, "neutral": int, "edges": int},
            "focus_graph": {"nodes": [...], "edges": [...]},
            "top_claims": [{"id": str, "text": str, "label": str, "score": float, "supporting_evidence_count": int}, ...],
        }
        ```
        On internal failure, returns
        `{"nodes": [], "edges": [], "stats": {...all 0...}, "focus_graph": {"nodes": [], "edges": []}, "top_claims": [], "error": "<message>"}`
        - callers (the Celery task) should check for the "error" key.
    """
    empty_result = {
        "nodes": [], "edges": [],
        "stats": {"claims": 0, "evidence": 0, "neutral": 0, "edges": 0},
        "focus_graph": {"nodes": [], "edges": []},
        "top_claims": [],
    }

    try:
        sentences = _segment_sentences(text)
        if not sentences:
            return empty_result

        classifications = classify_sentences(sentences, language=language)

        graph = nx.DiGraph()
        claim_indices: list[int] = []
        evidence_indices: list[int] = []

        for idx, (sentence, cls) in enumerate(zip(sentences, classifications)):
            label = cls["label"]
            node_id = f"n{idx}"
            graph.add_node(
                node_id,
                type=label,
                label=(sentence[:80] + "...") if len(sentence) > 80 else sentence,
                text=sentence,
                score=round(float(cls["score"]), 4),
            )
            if label == "claim":
                claim_indices.append(idx)
            elif label == "evidence":
                evidence_indices.append(idx)

        if claim_indices and evidence_indices:
            embedding_model = get_embedding_model()

            claim_sentences = [sentences[i] for i in claim_indices]
            evidence_sentences = [sentences[i] for i in evidence_indices]

            claim_embeddings = embedding_model.encode(
                claim_sentences, batch_size=EMBEDDING_BATCH_SIZE, convert_to_tensor=True,
            )
            evidence_embeddings = embedding_model.encode(
                evidence_sentences, batch_size=EMBEDDING_BATCH_SIZE, convert_to_tensor=True,
            )

            from sentence_transformers import util
            similarity_matrix = util.cos_sim(evidence_embeddings, claim_embeddings)

            mask = similarity_matrix >= threshold
            for e_pos, c_pos in torch.nonzero(mask, as_tuple=False).tolist():
                sim = float(similarity_matrix[e_pos, c_pos])
                e_idx, c_idx = evidence_indices[e_pos], claim_indices[c_pos]
                graph.add_edge(
                    f"n{e_idx}", f"n{c_idx}",
                    label="supports", weight=round(sim, 4),
                )

        nodes = [
            {"id": node_id, "type": data["type"], "label": data["label"], "text": data["text"], "score": data["score"]}
            for node_id, data in graph.nodes(data=True)
        ]
        edges = [
            {"source": u, "target": v, "label": data["label"], "weight": data["weight"]}
            for u, v, data in graph.edges(data=True)
        ]

        stats = {
            "claims": len(claim_indices),
            "evidence": len(evidence_indices),
            "neutral": len(sentences) - len(claim_indices) - len(evidence_indices),
            "edges": len(edges),
        }

        focus_graph, top_claims = _build_focus_graph(graph, top_claims_count)

        return {
            "nodes": nodes, "edges": edges, "stats": stats,
            "focus_graph": focus_graph, "top_claims": top_claims,
        }

    except Exception as e:
        logger.exception("extract_graph failed: %s", e)
        return {**empty_result, "error": str(e)}
