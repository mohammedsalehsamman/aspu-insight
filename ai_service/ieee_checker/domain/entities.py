from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class ReferenceEntry:
    index: int
    raw_text: str
    authors: str = ""
    title: str = ""
    source: str = ""
    year: str = ""
    doi: str = ""
    url: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    format_errors: List[str] = field(default_factory=list)
    crossref_verified: Optional[bool] = None
    crossref_message: str = ""
    ieee_score: float = 0.0


@dataclass
class IEEECheckResult:
    paper_title: str = ""
    detected_language: str = "unknown"
    total_pages: int = 0
    citations_in_text: List[int] = field(default_factory=list)
    citations_missing_from_references: List[int] = field(default_factory=list)
    unused_references: List[int] = field(default_factory=list)
    references: List[ReferenceEntry] = field(default_factory=list)
    total_references: int = 0
    format_issues_summary: List[str] = field(default_factory=list)
    references_without_year: List[int] = field(default_factory=list)
    references_without_authors: List[int] = field(default_factory=list)
    references_without_title: List[int] = field(default_factory=list)
    crossref_checked: int = 0
    crossref_verified_count: int = 0
    crossref_failed: List[int] = field(default_factory=list)
    citation_matching_score: float = 0.0
    format_score: float = 0.0
    crossref_score: float = 0.0
    overall_score: float = 0.0
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
