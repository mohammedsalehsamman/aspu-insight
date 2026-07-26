from __future__ import annotations

import logging
from typing import List, Tuple

from ..domain.entities import IEEECheckResult
from ..infrastructure.nlp_models import get_extraction_llm
from .format_validator import generate_recommendations, generate_summary

logger = logging.getLogger(__name__)

_PROMPT = """اكتب باللغة العربية الفصحى تقريراً موجزاً (ملخص من جملة واحدة، ثم 3-6 توصيات) \
لتقرير فحص ورقة بحثية وفق معايير IEEE بناءً على البيانات التالية:

عنوان الورقة: {title}
اللغة المكتشفة: {lang}
عدد الصفحات: {pages}
الاستشهادات في النص: {citations}
إجمالي المراجع: {refs}
استشهادات بلا مرجع: {missing}
مراجع غير مُستخدَمة: {unused}
درجة تطابق الاستشهادات: {citation_score}/100
درجة التنسيق: {format_score}/100
درجة هيكل الورقة: {structure_score}/100
أقسام ناقصة: {missing_sections}
ترتيب الأقسام صحيح: {order_valid}
الدرجة الكلية: {overall_score}/100
الحالة: {status}

أرجع فقط نص عربي بالتنسيق التالي بدون أي شرح إضافي:
ملخص: <جملة واحدة>
توصيات:
- <توصية 1>
- <توصية 2>
...
"""

def _status_ar(status: str) -> str:
    return {"pass": "مقبول", "warning": "يحتاج تحسين", "fail": "يحتاج مراجعة جوهرية"}.get(status, "غير محدد")

def _parse_llm_output(text: str) -> Tuple[str, List[str]]:
    summary = ""
    recommendations: List[str] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for line in lines:
        if line.startswith("ملخص:"):
            summary = line.split(":", 1)[1].strip()
        elif line.startswith("- "):
            recommendations.append(line[2:].strip())
    return summary, recommendations

def generate_recommendations_and_summary_ai(result: IEEECheckResult) -> Tuple[str, List[str]]:
    try:
        model, tokenizer = get_extraction_llm()
        import torch

        prompt_text = _PROMPT.format(
            title=(result.paper_title or "غير معروف")[:80],
            lang=result.detected_language,
            pages=result.total_pages,
            citations=len(result.citations_in_text),
            refs=result.total_references,
            missing=len(result.citations_missing_from_references),
            unused=len(result.unused_references),
            citation_score=result.citation_matching_score,
            format_score=result.format_score,
            structure_score=result.structure_score,
            missing_sections=", ".join(result.missing_required_sections) or "لا يوجد",
            order_valid="نعم" if result.section_order_valid else "لا",
            overall_score=result.overall_score,
            status=_status_ar(result.status),
        )
        messages = [{"role": "user", "content": prompt_text}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt")

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=300,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated = output_ids[0][inputs["input_ids"].shape[1]:]
        text = tokenizer.decode(generated, skip_special_tokens=True)

        summary, recommendations = _parse_llm_output(text)
        if not summary or not recommendations:
            raise ValueError(f"Incomplete LLM output: {text[:200]!r}")

        return summary, recommendations

    except Exception as e:
        logger.warning("AI recommendation generation failed, using template fallback: %s", e)
        return generate_summary(result), generate_recommendations(result)
