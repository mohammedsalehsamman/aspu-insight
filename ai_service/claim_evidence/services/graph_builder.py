"""
Core service for the Claim-to-Evidence Graph feature.

`extract_graph(text, threshold)` is the main entrypoint:
    1. Segments `text` into sentences (NLTK punkt).
    2. Classifies each sentence as claim/evidence/neutral via the hybrid
       heuristic + zero-shot classifier.
    3. Computes sentence embeddings (all-MiniLM-L6-v2) for claim and
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

Scope note: only English-language cue-phrase heuristics are implemented.
Although `ai_service.ieee` supports bilingual (Arabic/English) PDF/DOCX
extraction, the zero-shot model and embedding model used here are
English-centric; Arabic sentence classification is out of scope for v1 and
may be classified as 'neutral'.
"""
from __future__ import annotations

import logging

import networkx as nx

from ..infrastructure.nlp_models import ensure_nltk_punkt, get_embedding_model
from .classifier import classify_sentences

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.5
DEFAULT_TOP_CLAIMS_COUNT = 10
MIN_SENTENCE_CHARS = 10
EMBEDDING_BATCH_SIZE = 32

# Safety cap on the number of sentences processed per document, to bound
# worst-case CPU time for the (slow, one-call-per-sentence) zero-shot
# classifier when running synchronously in eager mode.
MAX_SENTENCES = 500


def _segment_sentences(text: str) -> list[str]:
    """Split `text` into sentences using NLTK's punkt tokenizer.

    Filters out very short fragments (< MIN_SENTENCE_CHARS) which are
    typically headers, page numbers, or noise from PDF extraction. Caps
    the result at `MAX_SENTENCES`, logging a warning if the document is
    truncated.
    """
    ensure_nltk_punkt()
    from nltk.tokenize import sent_tokenize

    raw_sentences = sent_tokenize(text)
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
) -> dict:
    """Build a Claim-to-Evidence graph from raw document text.

    Args:
        text: Full extracted document text (e.g. from
            `ai_service.ieee.extract_text_from_file`).
        threshold: Cosine similarity threshold above which an
            evidence -> claim "supports" edge is created. Default 0.5.
        top_claims_count: Number of top-ranked claims (by supporting
            evidence count) to include in `focus_graph`/`top_claims`.

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

        classifications = classify_sentences(sentences)

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

            for e_pos, e_idx in enumerate(evidence_indices):
                for c_pos, c_idx in enumerate(claim_indices):
                    sim = float(similarity_matrix[e_pos][c_pos])
                    if sim >= threshold:
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
