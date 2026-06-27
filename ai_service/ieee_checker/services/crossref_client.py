from __future__ import annotations
import json
import urllib.request
from typing import Tuple


def verify_doi(doi: str) -> Tuple[bool, str]:
    try:
        url = f"https://api.crossref.org/works/{doi}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ASPU-Insight/1.0 (mailto:aspu@aspu.edu.sy)"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get('status') == 'ok':
                titles = data.get('message', {}).get('title', [])
                t = titles[0][:80] if titles else "N/A"
                return True, f"تم التحقق ✓ العنوان في Crossref: {t}"
    except Exception as e:
        return False, f"تعذّر التحقق عبر Crossref: {str(e)[:60]}"
    return False, "لم يُوجد DOI في Crossref"
