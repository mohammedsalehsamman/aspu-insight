from research.models import ResearchPaper
from accounts.tests.helpers import make_user  


def make_paper(author=None, status=ResearchPaper.Status.SUBMITTED, **kwargs):
    author = author or make_user(role='author')
    defaults = {
        'title': 'بحث تجريبي',
        'abstract': 'ملخص تجريبي للبحث.',
        'author': author,
        'status': status,
        'specialization': 'علوم الحاسوب',
    }
    defaults.update(kwargs)
    return ResearchPaper.objects.create(**defaults)
