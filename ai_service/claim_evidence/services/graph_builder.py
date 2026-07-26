from __future__ import annotations

import logging
import re

import networkx as nx
import torch

from ai_service.utils.nltk_setup import ensure_nltk_punkt
from ..infrastructure.nlp_models import get_embedding_model
from .classifier import classify_sentences

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.2
DEFAULT_TOP_CLAIMS_COUNT = 10
MIN_SENTENCE_CHARS = 10
EMBEDDING_BATCH_SIZE = 32

MAX_SENTENCES = 500

_SENTENCE_BOUNDARY_RE = re.compile(r'(?<=[.!?؟])\s+')

def _segment_sentences(text: str) -> list[str]:
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
