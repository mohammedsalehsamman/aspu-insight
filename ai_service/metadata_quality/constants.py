DIMENSION_WEIGHTS = {
    "title": 10,
    "abstract_basic": 15,
    "abstract_structure": 15,
    "keywords_presence": 10,
    "keywords_relevance": 10,
    "title_abstract_coherence": 10,
    "specialization": 10,
    "language_consistency": 5,
    "author_info": 10,
    "completeness": 5,
} 

DIMENSION_LABELS_AR = {
    "title": "جودة العنوان",
    "abstract_basic": "جودة الملخص الأساسية",
    "abstract_structure": "اكتمال مكوّنات الملخص العلمية",
    "keywords_presence": "وجود الكلمات المفتاحية وعددها",
    "keywords_relevance": "صلة الكلمات المفتاحية بالملخص",
    "title_abstract_coherence": "الاتساق الدلالي بين العنوان والملخص",
    "specialization": "التخصص/المجال العلمي",
    "language_consistency": "اتساق اللغة",
    "author_info": "بيانات المؤلف (المؤسسة وORCID)",
    "completeness": "اكتمال الحقول الأساسية للنظام",
}

TITLE_MIN_LEN = 10
TITLE_MAX_LEN = 150

ABSTRACT_MIN_WORDS = 50
ABSTRACT_IDEAL_MIN_WORDS = 120
ABSTRACT_IDEAL_MAX_WORDS = 350
ABSTRACT_MAX_WORDS = 500

KEYWORDS_IDEAL_MIN = 4
KEYWORDS_IDEAL_MAX = 8

KEYWORD_RELEVANCE_MIN_SIMILARITY = 0.15
TITLE_ABSTRACT_MIN_SIMILARITY = 0.20

ABSTRACT_COMPONENT_LABELS = {
    "objective": "research objective or aim",
    "methodology": "research methodology or method",
    "results": "results or findings",
    "conclusion": "conclusion or implications",
}
ABSTRACT_COMPONENT_THRESHOLD = 0.5

ORCID_PATTERN = r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'

NEUTRAL_FALLBACK_SCORE = 50.0
