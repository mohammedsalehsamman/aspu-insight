from __future__ import annotations
import re
from typing import Dict, List, Tuple

_YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')
_DOI_RE = re.compile(r'(?:doi\.org/|DOI:\s*|doi:\s*)(10\.\d{4,}/[^\s,\]]+)', re.IGNORECASE)
_URL_RE = re.compile(r'https?://[^\s\]]+', re.IGNORECASE)
_PAGES_RE = re.compile(r'pp?\.\s*(\d+[\s\-–]+\d+)', re.IGNORECASE)
_VOL_RE = re.compile(r'vol\.?\s*(\d+)', re.IGNORECASE)
_NO_RE = re.compile(r'no\.?\s*(\d+)', re.IGNORECASE)

_REF_SECTION_PATTERNS = [
    r'\bReferences\b',
    r'\bBibliography\b',
    r'\bWorks Cited\b',
    r'المراجع',
    r'قائمة المصادر',
]

_REF_END_PATTERNS = [
    r'\bAppendix\b',
    r'\bAPPENDIX\b',
    r'\nA\.\s+[A-Z][a-z]',
    r'\n[A-Z]\s+[A-Z]{2,}',
    r'NeurIPS Paper Checklist',
    r'\bAuthor\s+Contributions?\b',
]

_INVALID_REF_STARTS = (
    'Question:', 'Answer:', 'Figure', 'Table', 'Click',
    'Your output', 'Repeat', 'Guidelines:', 'Note that',
    'In Table', 'Detailed', 'Mean and', 'Error', 'Paper',
    'Category', 'Institutional', 'Crowdsourcing', 'Safeguards',
    'Broader', 'Code of', 'Codeofethics',
    'Declaration', 'New assets',
    'Experiment', 'Compute', 'Data splits',
    'Open access', 'Openaccessto', 'Association for',
    'orderivation', 'Licenses', '•', 'ResultsandDiscussion',
)

_INVALID_REF_PATTERNS = [
    re.compile(r'^\[\d+\]\s+\w'),
    re.compile(r'^https?://\S+\s*$'),
]


def _is_valid_reference(text: str) -> bool:
    if len(text) < 30:
        return False
    for s in _INVALID_REF_STARTS:
        if text.startswith(s):
            return False
    for pat in _INVALID_REF_PATTERNS:
        if pat.search(text):
            return False
    return bool(_YEAR_RE.search(text) or _DOI_RE.search(text) or _URL_RE.search(text))


def find_references_section(full_text: str) -> str:
    pattern = '|'.join(_REF_SECTION_PATTERNS)
    matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
    if not matches:
        return ""
    section = full_text[matches[-1].start():]
    for end_pat in _REF_END_PATTERNS:
        end_m = re.search(end_pat, section[50:])
        if end_m:
            section = section[:50 + end_m.start()]
            break
    return section


def split_references_section(ref_section: str) -> List[Tuple[int, str]]:
    results: List[Tuple[int, str]] = []
    ref_pattern = re.compile(
        r'(?:\[(\d+)\]\.?\s*|^([1-9]\d{0,2})\.\s+)'
        r'(.*?)'
        r'(?=\n\s*(?:\[\d+\]\.?\s*|[1-9]\d{0,2}\.\s+)|\Z)',
        re.DOTALL | re.MULTILINE,
    )
    for m in ref_pattern.finditer(ref_section):
        num_str = m.group(1) or m.group(2)
        text = m.group(3).strip()
        if num_str and text:
            ref_num = int(num_str)
            if ref_num > 999:
                continue
            clean_text = re.sub(r'\s+', ' ', text).strip()
            if _is_valid_reference(clean_text):
                results.append((ref_num, clean_text))
    return results


def parse_ieee_reference(ref_text: str) -> Dict[str, str]:
    result = {
        'authors': '', 'title': '', 'source': '',
        'year': '', 'doi': '', 'url': '',
        'volume': '', 'issue': '', 'pages': '',
    }
    text = ref_text.strip()

    doi_m = _DOI_RE.search(text)
    if doi_m:
        result['doi'] = doi_m.group(1).rstrip('.,)')

    url_m = _URL_RE.search(text)
    if url_m:
        result['url'] = url_m.group(0)

    clean_for_year = re.sub(r'arXiv:\d{4}\.\d+', '', text, flags=re.IGNORECASE)
    clean_for_year = re.sub(r'arxiv\.org/(?:abs|pdf|html)/\d{4}\.\d+', '', clean_for_year, flags=re.IGNORECASE)
    years = _YEAR_RE.findall(clean_for_year)
    if years:
        result['year'] = years[-1]

    pages_m = _PAGES_RE.search(text)
    if pages_m:
        result['pages'] = pages_m.group(1)

    vol_m = _VOL_RE.search(text)
    if vol_m:
        result['volume'] = vol_m.group(1)

    no_m = _NO_RE.search(text)
    if no_m:
        result['issue'] = no_m.group(1)

    title_m = re.search(r'["“”"]([^"“”"]+)["“”"]', text)
    if title_m:
        result['title'] = title_m.group(1).strip()

    if result['title']:
        authors_part = text[:text.find(result['title'])].strip().rstrip(',"')
        result['authors'] = re.sub(r'\s+', ' ', authors_part).strip()
    else:
        # Pattern 1: IEEE style — F. Lastname
        auth_m = re.match(
            r'^([A-Z]\.\s+[A-Z][a-zA-Z\-]+(?:(?:,\s*|,?\s+and\s+)[A-Z]\.\s+[A-Z][a-zA-Z\-]+)*'
            r'(?:,?\s*et al\.?)?)',
            text
        )
        if auth_m:
            result['authors'] = auth_m.group(1).strip()
        else:
            # Pattern 2: NeurIPS/arXiv style — Firstname Lastname
            name_m = re.match(
                r'^([A-Z][a-z]+(?:\s[A-Z][a-zA-Z\-]+)+'
                r'(?:(?:,\s*|,?\s+and\s+)[A-Z][a-z]+(?:\s[A-Z][a-zA-Z\-]+)+)*'
                r'(?:,?\s*et al\.?)?)',
                text
            )
            if name_m:
                result['authors'] = name_m.group(1).strip()
            else:
                ar_m = re.match(r'^([؀-ۿ\s،،,]+(?:[،،,]\s*))', text)
                if ar_m and len(ar_m.group(1).strip()) > 3:
                    result['authors'] = ar_m.group(1).strip()

    if result['title'] and result['year']:
        ti = text.find(result['title'])
        yi = text.rfind(result['year'])
        if ti >= 0 and yi > ti:
            after = text[ti + len(result['title']):yi]
            after = re.sub(r',?\s*vol\.\s*\d+.*', '', after, flags=re.IGNORECASE)
            after = re.sub(r'[,."]+', '', after).strip()
            result['source'] = after[:100]

    return result
