"""
Domain types for the Claim-to-Evidence Graph feature.

These dataclasses describe the shapes used internally by the
classification, similarity, and graph-building services. They exist purely
for type-clarity/documentation - the public service entrypoint
(`graph_builder.extract_graph`) returns plain dicts (JSON-serializable) so
they can be stored directly in `ClaimEvidenceGraphReport.graph_data`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClassifiedSentence:
    """A single sentence with its classification result.

    Attributes:
        index: Position of the sentence within the segmented sentence list.
        text: The full sentence text.
        label: One of "claim", "evidence", "neutral".
        score: Confidence score in [0, 1] for `label`.
        heuristic_label: The label suggested by the rule-based heuristic
            alone (before combining with the zero-shot model), kept for
            debugging/inspection.
    """
    index: int
    text: str
    label: str
    score: float
    heuristic_label: str


@dataclass
class GraphNode:
    """A node in the Claim-to-Evidence graph (one per classified sentence)."""
    id: str
    type: str
    label: str
    text: str
    score: float


@dataclass
class GraphEdge:
    """A directed "supports" edge from an evidence node to a claim node."""
    source: str
    target: str
    label: str
    weight: float


@dataclass
class GraphResult:
    """The full result of `extract_graph`."""
    nodes: list
    edges: list
    stats: dict
    error: str = ""
