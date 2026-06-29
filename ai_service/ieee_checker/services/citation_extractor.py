from __future__ import annotations
import re
from typing import Dict

_SKIP_TITLE_PATTERNS = [
    re.compile(r'arXiv|viXra|preprint', re.IGNORECASE),
    re.compile(r'^[\d\.\:\-\/\s]+$'),
    re.compile(r'\d{4}\.\d{4,}v\d'),
    re.compile(r'@\w+\{'),
    re.compile(r'^https?://'),
    re.compile(r'^\s*Copyright|^All rights reserved', re.IGNORECASE),
]


def detect_language(text: str) -> str:
    arabic_chars = len(re.findall(r'[؀-ۿ]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    total = arabic_chars + latin_chars
    if total == 0:
        return "unknown"
    ar_ratio = arabic_chars / total
    if ar_ratio > 0.6:
        return "ar"
    if ar_ratio < 0.2:
        return "en"
    return "mixed"


def extract_paper_title(full_text: str) -> str:
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    skip_kw = {
        'abstract', 'introduction', 'keywords', 'references',
        'ملخص', 'مقدمة', 'كلمات مفتاحية', 'المراجع',
    }
    for line in lines[:30]:
        if len(line) < 10:
            continue
        if any(kw in line.lower() for kw in skip_kw):
            continue
        if re.match(r'^\d+$', line):
            continue
        if any(p.search(line) for p in _SKIP_TITLE_PATTERNS):
            continue
        if len(line) > 8:
            return line
    return lines[0] if lines else ""


def extract_in_text_citations(full_text: str) -> Dict[int, int]:
    citation_counts: Dict[int, int] = {}

    for match in re.findall(r'\[(\d+(?:\s*,\s*\d+)*)\]', full_text):
        for num_str in re.findall(r'\d+', match):
            num = int(num_str)
            citation_counts[num] = citation_counts.get(num, 0) + 1

    for start_s, end_s in re.findall(r'\[(\d+)\]\s*[-–]\s*\[(\d+)\]', full_text):
        for num in range(int(start_s), int(end_s) + 1):
            citation_counts[num] = citation_counts.get(num, 0) + 1

    return citation_counts
